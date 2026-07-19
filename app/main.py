import asyncio
import logging
import os
import time

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from app.cache import article_cache
from app.config import settings
from app.export import markdown_to_docx_bytes, markdown_to_pdf_bytes, build_batch_zip
from app.llm_providers import llm_generate
from app.metrics import keyword_density, readability
from app.quality import assess_quality
from app.rag.retriever import is_in_domain
from app.rate_limit import rate_limiter
from app.schemas import BatchGenerateRequest, GenerateRequest

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("healthy_gut_ai")

STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static")

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


PROTECTED_PATHS = ("/generate", "/generate/batch", "/export/docx", "/export/pdf", "/debug")


@app.middleware("http")
async def rate_limit_and_logging_middleware(request: Request, call_next):
    start = time.time()

    if settings.API_KEY and request.url.path in PROTECTED_PATHS:
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


@app.get("/health")
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
    }


@app.get("/debug")
def debug():
    return {"routes": [r.path for r in app.routes]}


@app.get("/rag/preview")
def rag_preview(topic: str, keyword: str = "", top_k: int = 3):
    """Shows which knowledge-base chunks would be retrieved for a given
    topic/keyword, with similarity scores — useful for demonstrating that
    retrieval is real (ranked by relevance) rather than a hardcoded lookup."""
    from app.rag.retriever import retriever

    top_k = max(1, min(top_k, 10))
    chunks = retriever.retrieve(f"{topic} {keyword}".strip(), top_k=top_k)
    return {
        "query": f"{topic} {keyword}".strip(),
        "corpus_size": retriever.size(),
        "matches": [
            {"title": c["title"], "topic": c["topic"], "relevance_score": c["relevance_score"], "excerpt": c["content"][:160] + "..."}
            for c in chunks
        ],
    }


@app.get("/", response_class=HTMLResponse)
def root():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


OUT_OF_SCOPE_MESSAGE = (
    "Healthy Gut AI specializes in gut/digestive health topics (IBS, IBD, GERD, "
    "Celiac, SIBO, microbiome, diet, and related conditions). This topic looks "
    "outside that scope, so we're not generating it rather than producing an "
    "unfocused, low-trust article. Try a gut-health-related angle instead."
)


async def _generate_one(req: GenerateRequest) -> dict:
    if not is_in_domain(req.topic, req.primary_keyword):
        return {"error": OUT_OF_SCOPE_MESSAGE, "out_of_scope": True}

    cache_key = article_cache.make_key(req.topic, req.primary_keyword, req.geo_target, req.article_type.value, req.language.value)
    cached = article_cache.get(cache_key)
    if cached:
        result = dict(cached)
        result["cached"] = True
        return result

    result = await llm_generate(req.topic, req.primary_keyword, req.geo_target, req.article_type.value, req.language.value)
    if "error" in result:
        return result

    article_md = result.get("optimized_article_markdown", "")
    result["metrics"] = {
        "wordCount": len(article_md.split()),
        "readability": readability(article_md),
        "keywordDensity": keyword_density(article_md, req.primary_keyword),
    }
    result["quality"] = assess_quality(result, req.topic, req.primary_keyword, req.article_type.value)
    result["cached"] = False
    article_cache.set(cache_key, result)
    return result


@app.post("/generate")
async def generate(payload: GenerateRequest):
    try:
        result = await _generate_one(payload)
        if result.get("out_of_scope"):
            return JSONResponse(status_code=422, content=result)
        if "error" in result:
            return JSONResponse(status_code=502, content=result)
        return JSONResponse(content=result)
    except Exception as e:
        logger.exception("generate() failed: %s", e)
        return JSONResponse(status_code=500, content={"error": "Article generation failed", "detail": str(e)})


@app.post("/generate/batch")
async def generate_batch(payload: BatchGenerateRequest):
    semaphore = asyncio.Semaphore(settings.BATCH_CONCURRENCY)

    async def _bounded(req: GenerateRequest):
        async with semaphore:
            try:
                return await _generate_one(req)
            except Exception as e:
                logger.exception("batch item failed: %s", e)
                return {"error": str(e), "topic": req.topic}

    results = await asyncio.gather(*(_bounded(item) for item in payload.items))
    ok_count = sum(1 for r in results if "error" not in r)
    return JSONResponse(content={
        "results": results,
        "total": len(results),
        "succeeded": ok_count,
        "failed": len(results) - ok_count,
    })


@app.post("/export/batch/zip")
async def export_batch_zip(payload: BatchGenerateRequest):
    """Regenerates (or reuses cache for) every item in the batch and returns
    a ZIP: one .docx per successful article plus batch_summary.csv covering
    every item, including failures."""
    semaphore = asyncio.Semaphore(settings.BATCH_CONCURRENCY)

    async def _bounded(req: GenerateRequest):
        async with semaphore:
            try:
                result = await _generate_one(req)
            except Exception as e:
                logger.exception("batch zip item failed: %s", e)
                result = {"error": str(e)}
            return {"request": req.model_dump(mode="json"), "result": result}

    items = await asyncio.gather(*(_bounded(item) for item in payload.items))
    zip_bytes = build_batch_zip(items)
    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="healthy-gut-ai-batch.zip"'},
    )


@app.post("/export/docx")
async def export_docx(payload: GenerateRequest):
    result = await _generate_one(payload)
    if "error" in result:
        return JSONResponse(status_code=502, content=result)
    data = markdown_to_docx_bytes(payload.topic, result.get("optimized_article_markdown", ""))
    filename = f"{payload.topic.lower().replace(' ', '-')}.docx"
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.post("/export/pdf")
async def export_pdf(payload: GenerateRequest):
    result = await _generate_one(payload)
    if "error" in result:
        return JSONResponse(status_code=502, content=result)
    data = markdown_to_pdf_bytes(payload.topic, result.get("optimized_article_markdown", ""))
    filename = f"{payload.topic.lower().replace(' ', '-')}.pdf"
    return Response(
        content=data,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
