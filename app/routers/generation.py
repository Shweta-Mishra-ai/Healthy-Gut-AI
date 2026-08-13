import asyncio
import json
import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

from app.cache import article_cache
from app.compliance import scan_article
from app.config import settings
from app.constants import OUT_OF_SCOPE_MESSAGE
from app.dashboard import tracker
from app.export import FontUnavailableError, build_batch_zip, markdown_to_docx_bytes, markdown_to_pdf_bytes
from app.internal_linking import find_related_articles
from app.llm_providers import llm_generate
from app.metrics import keyword_density, readability
from app.quality import assess_quality
from app.rag.retriever import is_in_domain
from app.review import ReviewNotFoundError, ReviewStatus, review_store
from app.schemas import BatchGenerateRequest, GenerateRequest
from app.seo import build_seo_pack
from app.similarity import check_duplication, duplication_summary

logger = logging.getLogger("gutfolio.generation")
router = APIRouter()


def _enrich(result: dict, req: GenerateRequest, review_id: str = None) -> dict:
    """Everything computed from the finished article, in the order the later
    steps depend on: metrics -> compliance -> quality (which folds the
    compliance penalty in) -> SEO pack -> duplicate scan."""
    article_md = result.get("optimized_article_markdown", "")
    result["metrics"] = {
        "wordCount": len(article_md.split()),
        "readability": readability(article_md, req.language.value),
        "keywordDensity": keyword_density(article_md, req.primary_keyword),
    }
    result["compliance"] = scan_article(article_md, req.language.value)
    result["quality"] = assess_quality(
        result, req.topic, req.primary_keyword, req.article_type.value, req.language.value
    )
    result["seo"] = build_seo_pack(
        result, req.topic, req.primary_keyword, req.geo_target, req.language.value,
        site_url=settings.PUBLIC_SITE_URL,
    )
    # The generated schema_json_ld from the model is a stub at best and
    # invalid at worst; replace it with the graph built from the real article.
    result["schema_json_ld"] = result["seo"]["structured_data"]

    duplication = check_duplication(article_md, req.primary_keyword, exclude_id=review_id)
    duplication["summary"] = duplication_summary(duplication)
    result["duplication"] = duplication
    return result


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
            review_id = new_review_id
            result["review_status"] = ReviewStatus.draft.value
            article_cache.set(cache_key, result)

        # Internal links and the duplicate scan are both relative to the rest
        # of the library, which keeps changing as articles are approved. Served
        # from cache they went stale immediately: an article generated before
        # anything was approved showed "no links available" forever.
        result["internal_link_suggestions"] = find_related_articles(
            req.topic, req.primary_keyword, exclude_review_id=review_id
        )
        duplication = check_duplication(
            result.get("optimized_article_markdown", ""), req.primary_keyword, exclude_id=review_id
        )
        duplication["summary"] = duplication_summary(duplication)
        result["duplication"] = duplication

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

    result = _enrich(result, req)
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


@router.post("/generate/batch/stream")
async def generate_batch_stream(payload: BatchGenerateRequest, request: Request):
    """Newline-delimited JSON stream, one line per finished article.

    A 10-item batch is 10 sequential LLM pipelines behind a concurrency
    limit; buffered into a single response that regularly runs past the ~100s
    request ceiling most reverse proxies enforce (Render's default included),
    and the browser then sees a bare connection drop with every finished
    article thrown away. Streaming each result as it lands means the
    connection keeps producing bytes, the user watches real progress, and a
    late failure costs one item instead of the whole run.

    Line protocol: {"type":"start"|"item"|"summary", ...}
    """
    async def event_stream():
        semaphore = asyncio.Semaphore(settings.BATCH_CONCURRENCY)
        queue: asyncio.Queue = asyncio.Queue()

        async def worker(index: int, req: GenerateRequest):
            # Every path must put exactly one item on the queue: the reader
            # below waits for one result per request, so a worker that failed
            # without reporting would hang the response open until the proxy
            # killed it.
            result = {"error": "generation did not complete", "topic": req.topic}
            try:
                async with semaphore:
                    result = await _generate_one(req)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.exception("streamed batch item %d failed: %s", index, e)
                result = {"error": str(e), "topic": req.topic}
            finally:
                queue.put_nowait((index, result))

        tasks = [asyncio.create_task(worker(i, item)) for i, item in enumerate(payload.items)]
        total = len(tasks)
        succeeded = 0

        try:
            yield json.dumps({"type": "start", "total": total}) + "\n"
            for completed in range(total):
                index, result = await queue.get()
                if "error" not in result:
                    succeeded += 1
                yield json.dumps({
                    "type": "item",
                    "index": index,
                    "completed": completed + 1,
                    "total": total,
                    "topic": payload.items[index].topic,
                    "result": result,
                }, ensure_ascii=False) + "\n"
                if await request.is_disconnected():
                    logger.info("Client disconnected after %d/%d streamed items", completed + 1, total)
                    break
            yield json.dumps({
                "type": "summary", "total": total, "succeeded": succeeded, "failed": total - succeeded,
            }) + "\n"
        finally:
            # Without this, abandoning the stream leaves generations running
            # against paid providers with nowhere to deliver the result.
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    return StreamingResponse(
        event_stream(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


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
        headers={"Content-Disposition": 'attachment; filename="gutfolio-batch.zip"'},
    )


def _export_guard(result: dict):
    """Shared precondition check for every single-article export route."""
    if result.get("out_of_scope"):
        return JSONResponse(status_code=422, content=result)
    if "error" in result:
        return JSONResponse(status_code=502, content=result)
    return None


@router.post("/export/markdown")
async def export_markdown(payload: GenerateRequest):
    result = await _generate_one(payload)
    blocked = _export_guard(result)
    if blocked:
        return blocked
    filename = f"{payload.topic.lower().replace(' ', '-')}.md"
    return Response(
        content=result.get("optimized_article_markdown", ""),
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/export/json")
async def export_json(payload: GenerateRequest):
    result = await _generate_one(payload)
    blocked = _export_guard(result)
    if blocked:
        return blocked
    filename = f"{payload.topic.lower().replace(' ', '-')}.json"
    return Response(
        content=json.dumps(result, indent=2, ensure_ascii=False),
        media_type="application/json; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/export/docx")
async def export_docx(payload: GenerateRequest):
    result = await _generate_one(payload)
    blocked = _export_guard(result)
    if blocked:
        return blocked
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
    blocked = _export_guard(result)
    if blocked:
        return blocked
    try:
        data = markdown_to_pdf_bytes(payload.topic, result.get("optimized_article_markdown", ""))
    except FontUnavailableError as e:
        # Surfaced as a real error rather than a 200 with a blank PDF.
        return JSONResponse(status_code=503, content={"error": str(e), "export_format": "pdf"})
    filename = f"{payload.topic.lower().replace(' ', '-')}.pdf"
    return Response(
        content=data,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
