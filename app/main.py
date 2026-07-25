import asyncio
import json
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
from app.cms_wordpress import is_configured as wp_is_configured, publish_post as wp_publish_post, test_connection as wp_test_connection
from app.config import settings
from app.dashboard import tracker
from app.export import markdown_to_docx_bytes, markdown_to_pdf_bytes, build_batch_zip
from app.internal_linking import find_related_articles
from app.llm_providers import llm_generate
from app.metrics import keyword_density, readability
from app.quality import assess_quality
from app.rag.retriever import is_in_domain
from app.rate_limit import rate_limiter
from app.review import InvalidTransitionError, ReviewNotFoundError, ReviewStatus, review_store
from app.schemas import BatchGenerateRequest, GenerateRequest, ReviewActionRequest

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
        "database": {"path": settings.DATABASE_PATH, "reviews": review_store.counts()["total"]},
    }


@app.get("/debug")
def debug():
    return {"routes": [r.path for r in app.routes]}


@app.get("/internal-links")
def internal_links(topic: str, keyword: str = "", exclude_id: str = "", top_k: int = 5):
    top_k = max(1, min(top_k, 20))
    results = find_related_articles(topic, keyword, exclude_review_id=exclude_id or None, top_k=top_k)
    return {"topic": topic, "keyword": keyword, "suggestions": results}


@app.get("/rag/preview")
def rag_preview(topic: str, keyword: str = "", top_k: int = 3):
    """Shows which knowledge-base chunks would be retrieved for a query, with
    similarity scores — useful for demonstrating that retrieval is real
    (ranked by relevance) rather than a hardcoded lookup."""
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


PILLAR_SECTIONS = [
    ("Overview", 400), ("Causes/Triggers", 450), ("Symptoms", 450),
    ("Diet & Management", 650), ("When to See a Doctor", 300), ("FAQs/Closing", 250),
]
SUPPORTING_SECTIONS = [
    ("Overview", 175), ("Causes/Triggers", 225), ("Symptoms", 225),
    ("Diet & Management", 350), ("When to See a Doctor", 175),
]


@app.get("/outline")
def outline_preview(topic: str, keyword: str = "", geo: str = "", article_type: str = "supporting"):
    """Deterministic outline preview — no LLM call, instant and free. Shows
    the section structure, word budget per section, and which knowledge-base
    topics will ground the article, so the user can sanity-check before
    spending a generation on a topic that's out of scope or misconfigured."""
    from app.rag.retriever import retriever

    in_scope = is_in_domain(topic, keyword)
    sections = PILLAR_SECTIONS if article_type == "pillar" else SUPPORTING_SECTIONS
    target_min, target_max = (2500, 3000) if article_type == "pillar" else (1000, 1500)
    matches = retriever.retrieve(f"{topic} {keyword}".strip(), top_k=3) if in_scope else []

    return {
        "topic": topic,
        "keyword": keyword,
        "geo_target": geo,
        "article_type": article_type,
        "in_scope": in_scope,
        "scope_note": None if in_scope else OUT_OF_SCOPE_MESSAGE,
        "target_word_count": f"{target_min}-{target_max}",
        "planned_sections": [{"heading": h, "target_words": w} for h, w in sections],
        "grounding_sources": [{"title": c["title"], "topic": c["topic"], "relevance_score": c["relevance_score"]} for c in matches],
    }


@app.get("/dashboard/stats")
def dashboard_stats(recent: int = 20):
    return tracker.summary(limit_recent=max(1, min(recent, 100)))


@app.get("/review/counts")
def review_counts():
    return review_store.counts()


@app.get("/review/queue")
def review_queue(status: str = "draft", limit: int = 50):
    valid_statuses = {s.value for s in ReviewStatus}
    if status not in valid_statuses:
        return JSONResponse(status_code=422, content={"error": f"status must be one of {sorted(valid_statuses)}"})
    return {"items": review_store.list_queue(status=status, limit=limit)}


@app.get("/review/{article_id}")
def review_get(article_id: str):
    try:
        return review_store.get(article_id)
    except ReviewNotFoundError as e:
        return JSONResponse(status_code=404, content={"error": str(e)})


@app.post("/review/{article_id}/approve")
def review_approve(article_id: str, payload: ReviewActionRequest):
    try:
        item = review_store.set_status(article_id, ReviewStatus.approved, payload.note)
        logger.info("Article %s approved%s", article_id, f" — {payload.note}" if payload.note else "")
        return {"id": item["id"], "status": item["status"], "reviewed_at": item["reviewed_at"], "reviewer_note": item["reviewer_note"]}
    except ReviewNotFoundError as e:
        return JSONResponse(status_code=404, content={"error": str(e)})
    except InvalidTransitionError as e:
        return JSONResponse(status_code=409, content={"error": str(e)})


@app.post("/review/{article_id}/reject")
def review_reject(article_id: str, payload: ReviewActionRequest):
    try:
        item = review_store.set_status(article_id, ReviewStatus.rejected, payload.note)
        logger.info("Article %s rejected%s", article_id, f" — {payload.note}" if payload.note else "")
        return {"id": item["id"], "status": item["status"], "reviewed_at": item["reviewed_at"], "reviewer_note": item["reviewer_note"]}
    except ReviewNotFoundError as e:
        return JSONResponse(status_code=404, content={"error": str(e)})
    except InvalidTransitionError as e:
        return JSONResponse(status_code=409, content={"error": str(e)})


@app.get("/publish/wordpress/status")
def wordpress_status():
    return {"configured": wp_is_configured(), "site_url": settings.WORDPRESS_URL or None}


@app.post("/publish/wordpress/test-connection")
def wordpress_test_connection():
    result = wp_test_connection()
    if not result["connected"]:
        return JSONResponse(status_code=502, content=result)
    return result


@app.post("/publish/wordpress/{article_id}")
def wordpress_publish(article_id: str, status: str = "draft", dry_run: bool = False):
    if status not in ("draft", "publish"):
        return JSONResponse(status_code=422, content={"error": "status must be 'draft' or 'publish'"})

    try:
        item = review_store.get(article_id)
    except ReviewNotFoundError as e:
        return JSONResponse(status_code=404, content={"error": str(e)})

    if item["status"] != ReviewStatus.approved.value:
        return JSONResponse(status_code=409, content={
            "error": f"Article '{article_id}' is '{item['status']}', not 'approved' — only approved articles can be published."
        })

    article = item["article"]
    result = wp_publish_post(
        title=item["topic"],
        article_markdown=article.get("optimized_article_markdown", ""),
        excerpt=article.get("meta_description", ""),
        slug=article.get("url_slug", ""),
        status=status,
        dry_run=dry_run,
    )
    if not result["success"]:
        return JSONResponse(status_code=502, content=result)
    return result


@app.get("/review", response_class=HTMLResponse)
def review_page():
    return FileResponse(os.path.join(STATIC_DIR, "review.html"))


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard_page():
    return FileResponse(os.path.join(STATIC_DIR, "dashboard.html"))


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
        tracker.record(topic=req.topic, provider="", success=False, out_of_scope=True)
        return {"error": OUT_OF_SCOPE_MESSAGE, "out_of_scope": True}

    cache_key = article_cache.make_key(req.topic, req.primary_keyword, req.geo_target, req.article_type.value, req.language.value, req.tone.value)
    cached = article_cache.get(cache_key)
    if cached:
        result = dict(cached)
        result["cached"] = True

        review_id = result.get("review_id")
        review_still_exists = False
        if review_id:
            try:
                review_store.get(review_id)
                review_still_exists = True
            except ReviewNotFoundError:
                pass
        if not review_still_exists:
            # The cached content is still valid, but its review-workflow entry
            # is gone (evicted from the review store, or storage was reset) —
            # re-register it as a fresh draft rather than handing back a
            # review_id that would 404 on every approve/reject/publish call.
            new_review_id = review_store.register(result, req.topic, req.primary_keyword)
            result["review_id"] = new_review_id
            result["review_status"] = ReviewStatus.draft.value
            article_cache.set(cache_key, result)

        tracker.record(
            topic=req.topic, provider=result.get("provider_used", ""), success=True, cached=True,
            word_count=result.get("metrics", {}).get("wordCount", 0),
            quality_score=result.get("quality", {}).get("score", 0),
        )
        return result

    result = await llm_generate(req.topic, req.primary_keyword, req.geo_target, req.article_type.value, req.language.value, req.tone.value)
    if "error" in result:
        tracker.record(topic=req.topic, provider="", success=False)
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
    review_id = review_store.register(result, req.topic, req.primary_keyword)
    result["review_id"] = review_id
    result["review_status"] = ReviewStatus.draft.value
    result["internal_link_suggestions"] = find_related_articles(req.topic, req.primary_keyword, exclude_review_id=review_id)
    tracker.record(
        topic=req.topic, provider=result.get("provider_used", ""), success=True, cached=False,
        word_count=result["metrics"]["wordCount"], quality_score=result["quality"]["score"],
    )
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


@app.post("/export/markdown")
async def export_markdown(payload: GenerateRequest):
    result = await _generate_one(payload)
    if result.get("out_of_scope"):
        return JSONResponse(status_code=422, content=result)
    if "error" in result:
        return JSONResponse(status_code=502, content=result)
    filename = f"{payload.topic.lower().replace(' ', '-')}.md"
    return Response(
        content=result.get("optimized_article_markdown", ""),
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.post("/export/json")
async def export_json(payload: GenerateRequest):
    result = await _generate_one(payload)
    if result.get("out_of_scope"):
        return JSONResponse(status_code=422, content=result)
    if "error" in result:
        return JSONResponse(status_code=502, content=result)
    filename = f"{payload.topic.lower().replace(' ', '-')}.json"
    return Response(
        content=json.dumps(result, indent=2, ensure_ascii=False),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
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
