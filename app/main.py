import logging
import os
import secrets
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from app.cache import article_cache
from app.config import settings
from app.constants import STATIC_DIR
from app.llm_providers import provider_status
from app.rate_limit import rate_limiter
from app.review import review_store
from app.routers import articles, discovery, generation, publish
from app.routers import review as review_router

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("gutfolio")

if settings.CLIENT_IP_MODE not in ("first", "last", "peer"):
    raise ValueError(f"CLIENT_IP_MODE must be 'first', 'last' or 'peer', got {settings.CLIENT_IP_MODE!r}")

app = FastAPI(title="Healthy Gut", version="2.0.0")

if not settings.API_KEY:
    if settings.ALLOW_UNAUTHENTICATED:
        logger.warning("API_KEY is not set and ALLOW_UNAUTHENTICATED is on: every route is open. Local use only.")
    else:
        logger.warning("API_KEY is not set: generation, review and publishing routes are disabled until it is.")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",") if o.strip()],
    allow_methods=["GET", "POST", "HEAD", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID", "X-Response-Time", "Retry-After"],
)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def client_key(request: Request) -> str:
    peer = request.client.host if request.client else "unknown"
    mode = settings.CLIENT_IP_MODE
    if mode == "peer":
        return peer
    hops = [h.strip() for h in request.headers.get("x-forwarded-for", "").split(",") if h.strip()]
    if not hops:
        return peer
    return hops[-1] if mode == "last" else hops[0]


PROTECTED_PATH_PREFIXES = (
    "/generate", "/export", "/debug", "/review", "/dashboard", "/publish", "/articles", "/reviewers",
    # Both return ids, topics and keywords of the article library (/analyze
    # through its duplicate scan), so they were a read path around the key.
    "/analyze", "/internal-links",
)

# The review queue and dashboard are HTML pages loaded directly by a browser,
# which cannot attach an X-API-Key header to a top-level navigation. They sit
# under protected prefixes, so with API_KEY set both pages used to return a
# raw 401 JSON body in the browser window and the whole review workflow was
# unreachable. The pages themselves expose no data — every number on them is
# fetched by JS from the API routes below, which stay protected — so the
# documents are served and the data behind them is what's guarded.
PUBLIC_PAGE_PATHS = ("/review", "/dashboard")

# Endpoints that can trigger a full generation, and therefore real provider
# spend. /export/* was previously unmetered: an unauthenticated caller could
# skip the rate limiter entirely by POSTing to /export/pdf instead of
# /generate and get the identical pipeline run for free.
RATE_LIMITED_PATHS = (
    "/generate", "/generate/batch", "/generate/batch/stream",
    "/export/markdown", "/export/json", "/export/docx", "/export/pdf", "/export/batch/zip",
    # No provider cost, but up to 200k characters of TF-IDF and regex work per call.
    "/analyze",
)

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
}

# The app's own pages load only same-origin scripts (no inline <script>, no
# on*= handlers, no style="" attributes), so they can run under a strict
# policy: an injected tag in model output or a reviewer note would not
# execute even if an escaping bug let it into the DOM. Scoped to these pages
# because FastAPI's /docs and /redoc load their UI from a CDN with inline
# scripts, and would break under it.
APP_PAGES = ("/", "/review", "/dashboard")
APP_PAGE_CSP = "; ".join((
    "default-src 'self'",
    "script-src 'self'",
    "style-src 'self' https://fonts.googleapis.com",
    "font-src 'self' https://fonts.gstatic.com",
    "img-src 'self' data:",
    "connect-src 'self'",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
))


def _is_protected(request: Request) -> bool:
    path = request.url.path.rstrip("/") or "/"
    if request.method in ("GET", "HEAD") and path in PUBLIC_PAGE_PATHS:
        return False
    return path.startswith(PROTECTED_PATH_PREFIXES)


def _is_live_publish(request: Request) -> bool:
    path = request.url.path.rstrip("/")
    if request.method != "POST" or not path.startswith("/publish/wordpress/"):
        return False
    if path in ("/publish/wordpress/status", "/publish/wordpress/test-connection"):
        return False
    return request.query_params.get("dry_run", "false").strip().lower() not in ("1", "true", "yes")


def _auth_failure(request: Request, request_id: str) -> JSONResponse | None:
    """None when the request may proceed, else the response to send."""
    if not _is_protected(request):
        return None
    headers = {"X-Request-ID": request_id}
    if settings.API_KEY:
        provided = request.headers.get("x-api-key", "")
        # Constant-time comparison: a plain != leaks the key one byte at a
        # time to anyone who can measure response latency.
        if secrets.compare_digest(provided, settings.API_KEY):
            return None
        logger.warning("[%s] Rejected request to %s: missing/invalid API key", request_id, request.url.path)
        return JSONResponse(
            status_code=401,
            content={"error": "Missing or invalid API key. Set the X-API-Key header."},
            headers=headers,
        )
    if not settings.ALLOW_UNAUTHENTICATED:
        return JSONResponse(status_code=503, content={
            "error": "This deployment has no API_KEY configured, so generation, review and publishing are "
                     "disabled. Set API_KEY on the server (ALLOW_UNAUTHENTICATED=true is for local development only).",
        }, headers=headers)
    if _is_live_publish(request):
        # Open mode is for trying the app locally. Writing to a real external
        # site is never allowed without a key, whatever the mode.
        return JSONResponse(status_code=403, content={
            "error": "Publishing to WordPress requires API_KEY to be set on the server. Dry runs still work.",
        }, headers=headers)
    return None


@app.middleware("http")
async def rate_limit_and_logging_middleware(request: Request, call_next):
    start = time.time()
    request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]

    denied = _auth_failure(request, request_id)
    if denied is not None:
        return denied

    if request.method == "POST" and request.url.path.rstrip("/") in RATE_LIMITED_PATHS:
        key = client_key(request)
        allowed, retry_after = rate_limiter.allow(key)
        if not allowed:
            logger.warning("[%s] Rate limit hit for %s on %s", request_id, key, request.url.path)
            return JSONResponse(
                status_code=429,
                content={"error": "Rate limit exceeded. Please slow down.", "retry_after_seconds": retry_after},
                headers={"Retry-After": str(retry_after), "X-Request-ID": request_id},
            )
    try:
        response = await call_next(request)
    except Exception as e:
        logger.exception("[%s] Unhandled error on %s: %s", request_id, request.url.path, e)
        return JSONResponse(
            status_code=500,
            content={"error": "Internal server error", "request_id": request_id},
            headers={"X-Request-ID": request_id},
        )
    duration_ms = round((time.time() - start) * 1000, 1)
    response.headers["X-Response-Time"] = f"{duration_ms}ms"
    response.headers["X-Request-ID"] = request_id
    for header, value in SECURITY_HEADERS.items():
        response.headers.setdefault(header, value)
    if request.method in ("GET", "HEAD") and (request.url.path.rstrip("/") or "/") in APP_PAGES:
        response.headers.setdefault("Content-Security-Policy", APP_PAGE_CSP)
    logger.info(
        "[%s] %s %s -> %s (%sms)",
        request_id, request.method, request.url.path, response.status_code, duration_ms,
    )
    return response


def _serializable_errors(errors) -> list:
    """pydantic v2 error dicts can contain a 'ctx' with a raw exception
    object (e.g. the ValueError from a field_validator), which is not
    JSON serializable. Strip/stringify anything non-primitive."""
    clean = []
    for err in errors:
        e = dict(err)
        if "ctx" in e and isinstance(e["ctx"], dict):
            e["ctx"] = {k: str(v) for k, v in e["ctx"].items()}
        clean.append(e)
    return clean


def _validation_failed(errors) -> JSONResponse:
    return JSONResponse(
        status_code=422, content={"error": "Validation failed", "details": _serializable_errors(errors)}
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return _validation_failed(exc.errors())


@app.exception_handler(ValidationError)
async def pydantic_validation_handler(request: Request, exc: ValidationError):
    return _validation_failed(exc.errors())


@app.get("/health")
@app.head("/health", include_in_schema=False)
@app.get("/api/v1/health", include_in_schema=False)
@app.head("/api/v1/health", include_in_schema=False)
def health():
    providers_configured = {
        "groq": bool(settings.GROQ_API_KEY),
        "openrouter": bool(settings.OPENROUTER_API_KEY),
        "openai": bool(settings.OPENAI_API_KEY),
    }
    return {
        "status": "ok",
        "mode": "live" if any(providers_configured.values()) else "mock",
        "providers_configured": providers_configured,
        "api_key_protected": bool(settings.API_KEY),
        "auth": "api_key" if settings.API_KEY else ("open" if settings.ALLOW_UNAUTHENTICATED else "disabled"),
        "provider_status": provider_status(),
        "cache": article_cache.stats(),
        # The database file path used to be returned here — server layout
        # is nobody's business on a public endpoint.
        "database": {"reviews": review_store.counts()["total"]},
    }


def _all_route_paths(routes) -> set:
    """Recursively collects route paths, expanding FastAPI's lazy
    _IncludedRouter wrappers (used internally by include_router() in newer
    FastAPI versions) which don't expose .path directly on the top-level
    app.routes list the way plain APIRoute entries do."""
    paths = set()
    for r in routes:
        path = getattr(r, "path", None)
        if path:
            paths.add(path)
            continue
        nested_router = getattr(r, "original_router", None)
        if nested_router is not None:
            paths |= _all_route_paths(getattr(nested_router, "routes", []))
    return paths


@app.get("/debug")
def debug():
    return {"routes": sorted(_all_route_paths(app.routes))}


@app.get("/debug/client-ip")
def debug_client_ip(request: Request):
    """Shows what the rate limiter keys this request on. Send a fake
    X-Forwarded-For through the real deployment: if rate_limit_key echoes the
    fake value back, clients can dodge the limit, and CLIENT_IP_MODE needs
    changing."""
    return {
        "client_ip_mode": settings.CLIENT_IP_MODE,
        "x_forwarded_for": request.headers.get("x-forwarded-for"),
        "peer": request.client.host if request.client else None,
        "rate_limit_key": client_key(request),
    }


@app.get("/", response_class=HTMLResponse)
def root():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


app.include_router(generation.router)
app.include_router(discovery.router)
app.include_router(review_router.router)
app.include_router(publish.router)
app.include_router(articles.router)


if __name__ == "__main__":
    import uvicorn
    # host="0.0.0.0" is required for container platforms (Render/Docker) to
    # route external traffic in — 127.0.0.1 would make the app unreachable
    # from outside the container. Explicit entrypoint, not a hidden default.
    uvicorn.run("app.main:app", host="0.0.0.0", port=int(os.getenv("PORT", "8000")))  # nosec B104
