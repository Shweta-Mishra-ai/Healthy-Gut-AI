import logging
import time

from fastapi import APIRouter
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from app.constants import STATIC_DIR
from app.dashboard import tracker
from app.language import check_language
from app.pipeline import enrich_article
from app.postprocess import ensure_disclaimer
from app.review import (
    InvalidTransitionError,
    ReviewNotFoundError,
    ReviewStatus,
    request_for_review,
    review_store,
)
from app.schemas import ReviewActionRequest, ReviewEditRequest

logger = logging.getLogger("gutfolio.review")
router = APIRouter()


@router.get("/dashboard/stats")
def dashboard_stats(recent: int = 20):
    return tracker.summary(limit_recent=max(1, min(recent, 100)))


@router.get("/review/counts")
def review_counts():
    return review_store.counts()


@router.get("/review/queue")
def review_queue(status: str = "draft", limit: int = 50):
    valid_statuses = {s.value for s in ReviewStatus}
    if status not in valid_statuses:
        return JSONResponse(status_code=422, content={"error": f"status must be one of {sorted(valid_statuses)}"})
    return {"items": review_store.list_queue(status=status, limit=limit)}


@router.get("/review/{article_id}")
def review_get(article_id: str):
    try:
        return review_store.get(article_id)
    except ReviewNotFoundError as e:
        return JSONResponse(status_code=404, content={"error": str(e)})


@router.post("/review/{article_id}/approve")
def review_approve(article_id: str, payload: ReviewActionRequest):
    try:
        item = review_store.set_status(
            article_id, ReviewStatus.approved, payload.note,
            reviewer_name=payload.reviewer_name, reviewer_credential=payload.reviewer_credential,
        )
        logger.info("Article %s approved%s", article_id, f" — {payload.note}" if payload.note else "")
        return {
            "id": item["id"], "status": item["status"], "reviewed_at": item["reviewed_at"],
            "reviewer_note": item["reviewer_note"], "reviewer_name": item["reviewer_name"],
            "reviewer_credential": item["reviewer_credential"], "reviewer_badge": item["reviewer_badge"],
        }
    except ReviewNotFoundError as e:
        return JSONResponse(status_code=404, content={"error": str(e)})
    except InvalidTransitionError as e:
        return JSONResponse(status_code=409, content={"error": str(e)})


@router.post("/review/{article_id}/reject")
def review_reject(article_id: str, payload: ReviewActionRequest):
    try:
        item = review_store.set_status(
            article_id, ReviewStatus.rejected, payload.note,
            reviewer_name=payload.reviewer_name, reviewer_credential=payload.reviewer_credential,
        )
        logger.info("Article %s rejected%s", article_id, f" — {payload.note}" if payload.note else "")
        return {
            "id": item["id"], "status": item["status"], "reviewed_at": item["reviewed_at"],
            "reviewer_note": item["reviewer_note"], "reviewer_name": item["reviewer_name"],
            "reviewer_credential": item["reviewer_credential"],
        }
    except ReviewNotFoundError as e:
        return JSONResponse(status_code=404, content={"error": str(e)})
    except InvalidTransitionError as e:
        return JSONResponse(status_code=409, content={"error": str(e)})


@router.post("/review/{article_id}/edit")
def review_edit(article_id: str, payload: ReviewEditRequest):
    """A reviewer's correction to a draft. Previously the only way to fix a
    compliance blocker or a wrong sentence was to reject the article and
    regenerate, losing everything that was right about it.

    The edited text is scored exactly like a generated article (metrics,
    compliance, quality, SEO pack, duplicate scan). The medical disclaimer
    is re-added if the edit removed it — the same guarantee every generated
    article carries."""
    try:
        item = review_store.get(article_id)
    except ReviewNotFoundError as e:
        return JSONResponse(status_code=404, content={"error": str(e)})
    if item["status"] != ReviewStatus.draft.value:
        return JSONResponse(status_code=409, content={
            "error": f"Article '{article_id}' is already '{item['status']}' — only drafts can be edited."
        })

    req = request_for_review(item)
    language = req.language.value
    article = dict(item["article"])
    markdown = ensure_disclaimer(payload.article_markdown, language)
    article["optimized_article_markdown"] = markdown
    article["language_check"] = check_language(markdown, language)

    if payload.meta_description is not None and payload.meta_description != article.get("meta_description"):
        previous = article.get("meta_description")
        article["meta_description"] = payload.meta_description
        others = [v for v in article.get("meta_description_variants") or [] if v and v != previous]
        article["meta_description_variants"] = [payload.meta_description, *others][:3]

    article = enrich_article(article, req, review_id=article_id)
    article["edits"] = [*(article.get("edits") or []), {
        "at": time.time(),
        "editor": payload.editor_name or None,
        "word_count": article["metrics"]["wordCount"],
    }]

    try:
        updated = review_store.update_article(article_id, article)
    except ReviewNotFoundError as e:
        return JSONResponse(status_code=404, content={"error": str(e)})
    except InvalidTransitionError as e:
        return JSONResponse(status_code=409, content={"error": str(e)})
    logger.info("Article %s edited%s", article_id, f" by {payload.editor_name}" if payload.editor_name else "")
    return updated


@router.get("/review", response_class=HTMLResponse)
def review_page():
    return FileResponse(f"{STATIC_DIR}/review.html")


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard_page():
    return FileResponse(f"{STATIC_DIR}/dashboard.html")
