import logging

from fastapi import APIRouter
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from app.constants import STATIC_DIR
from app.dashboard import tracker
from app.review import InvalidTransitionError, ReviewNotFoundError, ReviewStatus, review_store
from app.schemas import ReviewActionRequest

logger = logging.getLogger("healthy_gut_ai.review")
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


@router.get("/review", response_class=HTMLResponse)
def review_page():
    return FileResponse(f"{STATIC_DIR}/review.html")


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard_page():
    return FileResponse(f"{STATIC_DIR}/dashboard.html")
