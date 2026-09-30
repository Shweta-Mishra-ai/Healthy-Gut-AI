"""Exports of articles that already exist in the review store.

The POST /export/* routes take a generation request and run the pipeline
again. From the UI that meant "download what I'm looking at" could produce a
different article: once the cache entry expired, clicking PDF generated a
fresh one (and registered another review draft). These routes export the
stored article by id — exactly what was reviewed, including reviewer edits
and the sign-off badge — and never call a provider.
"""
import json

from fastapi import APIRouter
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field, field_validator

from app.config import settings
from app.export import (
    FontUnavailableError,
    build_batch_zip,
    content_disposition,
    markdown_to_docx_bytes,
    markdown_to_pdf_bytes,
)
from app.review import ReviewNotFoundError, markdown_with_reviewer_badge, request_for_review, review_store

router = APIRouter()

EXPORT_FORMATS = ("markdown", "json", "docx", "pdf")


class ArticleZipRequest(BaseModel):
    ids: list[str] = Field(..., min_length=1)

    @field_validator("ids")
    @classmethod
    def v_ids(cls, v):
        if len(v) > settings.MAX_BATCH_SIZE:
            raise ValueError(f"at most {settings.MAX_BATCH_SIZE} articles per ZIP")
        return v


def _request_fields(item: dict) -> dict:
    req = request_for_review(item)
    return {"topic": req.topic, "primary_keyword": req.primary_keyword, "geo_target": req.geo_target}


@router.get("/articles/{article_id}/export/{fmt}")
def export_article(article_id: str, fmt: str):
    if fmt not in EXPORT_FORMATS:
        return JSONResponse(status_code=422, content={"error": f"format must be one of {list(EXPORT_FORMATS)}"})
    try:
        item = review_store.get(article_id)
    except ReviewNotFoundError as e:
        return JSONResponse(status_code=404, content={"error": str(e)})

    topic = item["topic"]
    markdown = markdown_with_reviewer_badge(item)

    if fmt == "markdown":
        return Response(
            content=markdown,
            media_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition": content_disposition(topic, "md")},
        )
    if fmt == "json":
        body = dict(item["article"])
        body.update({
            "review_id": item["id"],
            "review_status": item["status"],
            "reviewer_badge": item["reviewer_badge"],
        })
        return Response(
            content=json.dumps(body, indent=2, ensure_ascii=False),
            media_type="application/json; charset=utf-8",
            headers={"Content-Disposition": content_disposition(topic, "json")},
        )
    if fmt == "docx":
        return Response(
            content=markdown_to_docx_bytes(topic, markdown),
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": content_disposition(topic, "docx")},
        )
    try:
        data = markdown_to_pdf_bytes(topic, markdown)
    except FontUnavailableError as e:
        return JSONResponse(status_code=503, content={"error": str(e), "export_format": "pdf"})
    return Response(
        content=data,
        media_type="application/pdf",
        headers={"Content-Disposition": content_disposition(topic, "pdf")},
    )


@router.post("/articles/export/zip")
def export_articles_zip(payload: ArticleZipRequest):
    items = []
    for article_id in payload.ids:
        try:
            item = review_store.get(article_id)
        except ReviewNotFoundError:
            items.append({
                "request": {"topic": article_id, "primary_keyword": "", "geo_target": ""},
                "result": {"error": f"No article found with id '{article_id}'"},
            })
            continue
        result = dict(item["article"])
        result["optimized_article_markdown"] = markdown_with_reviewer_badge(item)
        items.append({"request": _request_fields(item), "result": result})

    return Response(
        content=build_batch_zip(items),
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="healthy-gut-batch.zip"'},
    )
