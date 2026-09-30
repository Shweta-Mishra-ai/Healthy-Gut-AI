import threading
from collections import defaultdict

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.cms_wordpress import is_configured as wp_is_configured
from app.cms_wordpress import publish_post as wp_publish_post
from app.cms_wordpress import test_connection as wp_test_connection
from app.config import settings
from app.review import ReviewNotFoundError, ReviewStatus, markdown_with_reviewer_badge, review_store

router = APIRouter()

# One lock per article: a double-click on "Publish" sends two requests that
# would both see "no post yet" and create two WordPress posts.
_publish_locks: dict[str, threading.Lock] = defaultdict(threading.Lock)
_publish_locks_guard = threading.Lock()


def _lock_for(article_id: str) -> threading.Lock:
    with _publish_locks_guard:
        return _publish_locks[article_id]


@router.get("/publish/wordpress/status")
def wordpress_status():
    return {"configured": wp_is_configured(), "site_url": settings.WORDPRESS_URL or None}


@router.post("/publish/wordpress/test-connection")
def wordpress_test_connection():
    result = wp_test_connection()
    if not result["connected"]:
        return JSONResponse(status_code=502, content=result)
    return result


@router.post("/publish/wordpress/{article_id}")
def wordpress_publish(article_id: str, status: str = "draft", dry_run: bool = False,
                      override_compliance: bool = False):
    if status not in ("draft", "publish"):
        return JSONResponse(status_code=422, content={"error": "status must be 'draft' or 'publish'"})

    try:
        item = review_store.get(article_id)
    except ReviewNotFoundError as e:
        return JSONResponse(status_code=404, content={"error": str(e)})

    if item["status"] != ReviewStatus.approved.value:
        return JSONResponse(status_code=409, content={
            "error": f"Article '{article_id}' is '{item['status']}', not 'approved' — "
                     "only approved articles can be published."
        })

    article = item["article"]

    # Human approval and compliance are separate gates on purpose. A reviewer
    # approving the medical framing does not mean the copy is free of a
    # guaranteed-cure claim or a dosing instruction — those are the findings
    # that get a health page demoted or an ad account suspended, and they are
    # easy to miss when reading for accuracy. Publishing past them has to be a
    # deliberate, recorded act rather than the default.
    compliance = article.get("compliance") or {}
    blockers = [f for f in compliance.get("findings", []) if f.get("severity") == "blocker"]
    if blockers and not override_compliance:
        return JSONResponse(status_code=409, content={
            "error": f"Article '{article_id}' has {len(blockers)} unresolved compliance blocker(s). "
                     f"Fix them, or re-send with override_compliance=true to publish anyway.",
            "compliance_blockers": blockers,
        })

    # Trust signal at the point of publishing — a real named reviewer stood
    # behind this content, not just an anonymous "AI-generated" tag.
    article_markdown = markdown_with_reviewer_badge(item)

    with _lock_for(article_id):
        # Re-read inside the lock so a concurrent publish that just finished
        # is seen, and this one updates its post rather than making another.
        existing_post_id = review_store.get(article_id).get("wp_post_id")
        result = wp_publish_post(
            title=item["topic"],
            article_markdown=article_markdown,
            excerpt=article.get("meta_description", ""),
            slug=article.get("url_slug", ""),
            status=status,
            dry_run=dry_run,
            post_id=existing_post_id,
        )
        if not result["success"]:
            return JSONResponse(status_code=502, content=result)
        if not dry_run and result.get("post_id") is not None:
            review_store.record_wordpress_post(article_id, result["post_id"], result.get("post_url"))
    return result
