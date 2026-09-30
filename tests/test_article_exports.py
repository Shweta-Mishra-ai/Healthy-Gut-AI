import io
import json
import zipfile
from unittest.mock import patch
from urllib.parse import unquote

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _generate(topic="IBS diet plan", keyword="IBS diet", geo="India", language="en"):
    r = client.post("/generate", json={"topic": topic, "primary_keyword": keyword, "geo_target": geo, "language": language})
    assert r.status_code == 200, r.text
    return r.json()


@pytest.mark.parametrize("fmt", ["markdown", "json", "docx", "pdf"])
def test_export_by_id_returns_the_stored_article(fmt):
    article = _generate()
    r = client.get(f"/articles/{article['review_id']}/export/{fmt}")
    assert r.status_code == 200, r.text
    assert len(r.content) > 200
    if fmt == "markdown":
        assert r.text == article["optimized_article_markdown"]
    if fmt == "json":
        body = json.loads(r.text)
        assert body["review_id"] == article["review_id"]
        assert body["review_status"] == "draft"
        assert body["request"]["geo_target"] == "India"


def test_export_by_id_never_calls_the_generator():
    """The old UI flow re-POSTed the generation request, so once the cache
    expired a download produced a brand-new article."""
    article = _generate()
    with patch("app.routers.generation.llm_generate") as generator:
        r = client.get(f"/articles/{article['review_id']}/export/markdown")
    assert r.status_code == 200
    generator.assert_not_called()


def test_export_by_id_does_not_count_as_a_generation_on_the_dashboard():
    article = _generate()
    before = client.get("/dashboard/stats").json()["total_requests"]
    for fmt in ("markdown", "json", "docx", "pdf"):
        client.get(f"/articles/{article['review_id']}/export/{fmt}")
    assert client.get("/dashboard/stats").json()["total_requests"] == before


def test_export_by_id_includes_the_reviewer_badge_once_approved():
    article = _generate()
    client.post(f"/review/{article['review_id']}/approve",
                json={"reviewer_name": "Dr. Rao", "reviewer_credential": "MD"})
    md = client.get(f"/articles/{article['review_id']}/export/markdown").text
    assert md.rstrip().endswith("*Reviewed by Dr. Rao, MD*")


def test_export_by_id_unknown_article_and_format():
    assert client.get("/articles/doesnotexist/export/pdf").status_code == 404
    article = _generate()
    assert client.get(f"/articles/{article['review_id']}/export/exe").status_code == 422


def test_export_by_id_hindi_filename():
    article = _generate(topic="पेट में गैस", keyword="गैस", geo="भारत", language="hi")
    r = client.get(f"/articles/{article['review_id']}/export/pdf")
    assert r.status_code == 200
    assert unquote(r.headers["content-disposition"].split("filename*=UTF-8''", 1)[1]) == "पेट-में-गैस.pdf"


def test_zip_by_ids_bundles_stored_articles_and_reports_missing_ones():
    a = _generate()
    b = _generate(topic="पेट में गैस", keyword="गैस", geo="भारत", language="hi")
    r = client.post("/articles/export/zip", json={"ids": [a["review_id"], b["review_id"], "missing123"]})
    assert r.status_code == 200
    names = zipfile.ZipFile(io.BytesIO(r.content)).namelist()
    assert "ibs-diet-plan.docx" in names
    assert "पेट-में-गैस.docx" in names
    summary = zipfile.ZipFile(io.BytesIO(r.content)).read("batch_summary.csv").decode()
    assert "missing123" in summary and "FAILED" in summary


def test_zip_by_ids_validates_size():
    assert client.post("/articles/export/zip", json={"ids": []}).status_code == 422
    assert client.post("/articles/export/zip", json={"ids": ["x"] * 11}).status_code == 422


def test_articles_routes_require_the_api_key_when_set():
    article = _generate()
    with patch("app.main.settings") as s:
        s.API_KEY = "k"
        s.CLIENT_IP_MODE = "first"
        assert client.get(f"/articles/{article['review_id']}/export/markdown").status_code == 401
        assert client.get(f"/articles/{article['review_id']}/export/markdown",
                          headers={"X-API-Key": "k"}).status_code == 200
