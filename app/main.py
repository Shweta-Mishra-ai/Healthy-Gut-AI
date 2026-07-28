import logging
import os
import time

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
logger = logging.getLogger("healthy_gut_ai")

app = FastAPI(title="Healthy Gut AI", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
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


@app.middleware("http")
async def rate_limit_and_logging_middleware(request: Request, call_next):
    start = time.time()

    if settings.API_KEY and request.url.path.startswith(PROTECTED_PATH_PREFIXES):
        provided = request.headers.get("x-api-key", "")
        if provided != settings.API_KEY:
            logger.warning("Rejected request to %s: missing/invalid API key", request.url.path)
            return JSONResponse(status_code=401, content={"error": "Missing or invalid API key. Set the X-API-Key header."})

    if request.url.path in ("/generate", "/generate/batch"):
        key = client_key(request)
        allowed, retry_after = rate_limiter.allow(key)
        if not allowed:
            logger.warning("Rate limit hit for %s on %s", key, request.url.path)
            return JSONResponse(
                status_code=429,
                content={"error": "Rate limit exceeded. Please slow down.", "retry_after_seconds": retry_after},
                headers={"Retry-After": str(retry_after)},
            )
    try:
        response = await call_next(request)
    except Exception as e:
        logger.exception("Unhandled error on %s: %s", request.url.path, e)
        return JSONResponse(status_code=500, content={"error": "Internal server error"})
    duration_ms = round((time.time() - start) * 1000, 1)
    logger.info("%s %s -> %s (%sms)", request.method, request.url.path, response.status_code, duration_ms)
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
