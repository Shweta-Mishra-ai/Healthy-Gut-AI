from unittest.mock import patch
from urllib.parse import unquote

import pytest
from fastapi.testclient import TestClient

from app.llm_providers import _mock_result
from app.main import app

client = TestClient(app)

HINDI_PAYLOAD = {"topic": "पेट में गैस", "primary_keyword": "गैस", "geo_target": "भारत", "language": "hi"}


@pytest.mark.parametrize("fmt,ext", [("markdown", "md"), ("json", "json"), ("docx", "docx"), ("pdf", "pdf")])
def test_export_with_hindi_topic_does_not_500(fmt, ext):
    """Regression: the filename was interpolated raw into Content-Disposition,
    which Starlette encodes as latin-1 — every export for a Devanagari topic
    raised UnicodeEncodeError and came back as a 500."""
    r = client.post(f"/export/{fmt}", json=HINDI_PAYLOAD)
    assert r.status_code == 200, r.text
    disposition = r.headers["content-disposition"]
    assert f'filename="article.{ext}"' in disposition
    encoded = disposition.split("filename*=UTF-8''", 1)[1]
    assert unquote(encoded) == f"पेट-में-गैस.{ext}"


def test_export_filename_cannot_break_out_of_quotes():
    payload = {"topic": 'IBS "diet" guide/x', "primary_keyword": "ibs", "geo_target": "India"}
    r = client.post("/export/markdown", json=payload)
    assert r.status_code == 200
    assert r.headers["content-disposition"].startswith('attachment; filename="ibs-diet-guide-x.md";')


def test_rejected_article_is_not_served_again_from_cache():
    payload = {"topic": "IBS diet plan", "primary_keyword": "IBS diet", "geo_target": "India"}
    first = client.post("/generate", json=payload).json()
    assert client.post(f"/review/{first['review_id']}/reject", json={"note": "inaccurate"}).status_code == 200

    second = client.post("/generate", json=payload).json()
    assert second["cached"] is False
    assert second["review_id"] != first["review_id"]
    assert second["review_status"] == "draft"


def test_cached_article_reports_its_current_review_status():
    payload = {"topic": "Gut microbiome basics", "primary_keyword": "gut microbiome", "geo_target": "India"}
    first = client.post("/generate", json=payload).json()
    client.post(f"/review/{first['review_id']}/approve", json={})

    second = client.post("/generate", json=payload).json()
    assert second["cached"] is True
    assert second["review_id"] == first["review_id"]
    assert second["review_status"] == "approved"


def test_provider_failure_fallback_is_not_cached():
    """When real providers are configured but all fail, the template article
    carries a provider_note. Caching it kept serving the template for the
    whole TTL even after the provider recovered."""
    def failing_fallback(topic, keyword, geo, article_type, language="en", tone="educational"):
        result = _mock_result(topic, keyword, geo, language)
        result["provider_note"] = "All configured providers failed; served template content. groq: 404"
        return result

    payload = {"topic": "Acid reflux triggers", "primary_keyword": "acid reflux", "geo_target": "India"}
    with patch("app.routers.generation.llm_generate", side_effect=failing_fallback):
        first = client.post("/generate", json=payload).json()
        second = client.post("/generate", json=payload).json()
    assert first["cached"] is False
    assert second["cached"] is False
