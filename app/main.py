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
from app.rate_limit import rate_limiter
from app.review import review_store
from app.routers import discovery, generation, publish, review as review_router

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("gutfolio")

app = FastAPI(title="Gutfolio", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",") if o.strip()],
    allow_methods=["GET", "POST", "HEAD", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID", "X-Response-Time", "Retry-After"],
)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def client_key(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


PROTECTED_PATH_PREFIXES = (
    "/generate", "/export", "/debug", "/review", "/dashboard", "/publish",
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
)

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
}


def _requires_api_key(request: Request) -> bool:
    if not settings.API_KEY:
        return False
    path = request.url.path.rstrip("/") or "/"
    if request.method in ("GET", "HEAD") and path in PUBLIC_PAGE_PATHS:
        return False
    return path.startswith(PROTECTED_PATH_PREFIXES)


@app.middleware("http")
async def rate_limit_and_logging_middleware(request: Request, call_next):
    start = time.time()
    request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]

    if _requires_api_key(request):
        provided = request.headers.get("x-api-key", "")
        # Constant-time comparison: a plain != leaks the key one byte at a
        # time to anyone who can measure response latency.
        if not secrets.compare_digest(provided, settings.API_KEY):
            logger.warning("[%s] Rejected request to %s: missing/invalid API key", request_id, request.url.path)
            return JSONResponse(
                status_code=401,
                content={"error": "Missing or invalid API key. Set the X-API-Key header."},
                headers={"X-Request-ID": request_id},
            )

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
    logger.info("[%s] %s %s -> %s (%sms)", request_id, request.method, request.url.path, response.status_code, duration_ms)
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


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(status_code=422, content={"error": "Validation failed", "details": _serializable_errors(exc.errors())})


@app.exception_handler(ValidationError)
async def pydantic_validation_handler(request: Request, exc: ValidationError):
    return JSONResponse(status_code=422, content={"error": "Validation failed", "details": _serializable_errors(exc.errors())})


@app.api_route("/health", methods=["GET", "HEAD"])
@app.api_route("/api/v1/health", methods=["GET", "HEAD"])
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
        "cache": article_cache.stats(),
        "database": {"path": settings.DATABASE_PATH, "reviews": review_store.counts()["total"]},
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


@app.get("/", response_class=HTMLResponse)
def root():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


app.include_router(generation.router)
app.include_router(discovery.router)
app.include_router(review_router.router)
app.include_router(publish.router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
