import asyncio
import json
import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse, Response

from app.cache import article_cache
from app.config import settings
from app.constants import OUT_OF_SCOPE_MESSAGE
from app.dashboard import tracker
from app.export import build_batch_zip, markdown_to_docx_bytes, markdown_to_pdf_bytes
from app.internal_linking import find_related_articles
from app.llm_providers import llm_generate
from app.metrics import keyword_density, readability
from app.quality import assess_quality
from app.rag.retriever import is_in_domain
from app.review import ReviewNotFoundError, ReviewStatus, review_store
from app.schemas import BatchGenerateRequest, GenerateRequest

logger = logging.getLogger("healthy_gut_ai.generation")
router = APIRouter()


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
    result["quality"] = assess_quality(result, req.topic, req.primary_keyword, req.article_type.value, req.language.value)
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


@router.post("/generate")
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


@router.post("/generate/batch")
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


@router.post("/export/batch/zip")
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


@router.post("/export/markdown")
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


@router.post("/export/json")
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


@router.post("/export/docx")
async def export_docx(payload: GenerateRequest):
    result = await _generate_one(payload)
    if result.get("out_of_scope"):
        return JSONResponse(status_code=422, content=result)
    if "error" in result:
        return JSONResponse(status_code=502, content=result)
    data = markdown_to_docx_bytes(payload.topic, result.get("optimized_article_markdown", ""))
    filename = f"{payload.topic.lower().replace(' ', '-')}.docx"
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/export/pdf")
async def export_pdf(payload: GenerateRequest):
    result = await _generate_one(payload)
    if result.get("out_of_scope"):
        return JSONResponse(status_code=422, content=result)
    if "error" in result:
        return JSONResponse(status_code=502, content=result)
    data = markdown_to_pdf_bytes(payload.topic, result.get("optimized_article_markdown", ""))
    filename = f"{payload.topic.lower().replace(' ', '-')}.pdf"
    return Response(
        content=data,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
