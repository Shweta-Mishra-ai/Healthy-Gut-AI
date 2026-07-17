from fastapi.testclient import TestClient

from app.main import app
from app.rate_limit import rate_limiter

client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["mode"] == "mock"


def test_root_serves_html():
    r = client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]


def test_generate_mock_mode():
    payload = {"topic": "IBS diet", "primary_keyword": "IBS symptoms", "geo_target": "USA", "article_type": "supporting"}
    r = client.post("/generate", json=payload)
    assert r.status_code == 200
    body = r.json()
    assert body["provider_used"] == "mock"
    assert "metrics" in body
    assert "optimized_article_markdown" in body


def test_generate_validation_error():
    payload = {"topic": "ab", "primary_keyword": "kw", "geo_target": "USA"}
    r = client.post("/generate", json=payload)
    assert r.status_code == 422
    assert r.json()["error"] == "Validation failed"


def test_generate_missing_fields():
    r = client.post("/generate", json={})
    assert r.status_code == 422


def test_generate_cache_hit_marks_cached():
    payload = {"topic": "GERD relief unique test", "primary_keyword": "acid reflux", "geo_target": "UK", "article_type": "supporting"}
    r1 = client.post("/generate", json=payload)
    assert r1.status_code == 200
    assert r1.json()["cached"] is False
    r2 = client.post("/generate", json=payload)
    assert r2.status_code == 200
    assert r2.json()["cached"] is True


def test_batch_generate():
    payload = {"items": [
        {"topic": "IBS diet", "primary_keyword": "IBS", "geo_target": "USA"},
        {"topic": "GERD symptoms", "primary_keyword": "acid reflux", "geo_target": "UK"},
    ]}
    r = client.post("/generate/batch", json=payload)
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 2
    assert body["succeeded"] == 2


def test_batch_over_limit_rejected():
    item = {"topic": "IBS diet", "primary_keyword": "IBS", "geo_target": "USA"}
    payload = {"items": [item] * 11}
    r = client.post("/generate/batch", json=payload)
    assert r.status_code == 422


def test_rate_limiting():
    rate_limiter._hits.clear()
    rate_limiter._limit = 3
    payload = {"topic": "IBS diet", "primary_keyword": "IBS", "geo_target": "USA"}
    statuses = [client.post("/generate", json=payload).status_code for _ in range(5)]
    assert 429 in statuses
    rate_limiter._limit = 10
    rate_limiter._hits.clear()


def test_export_docx():
    payload = {"topic": "IBS diet test docx", "primary_keyword": "IBS", "geo_target": "USA"}
    r = client.post("/export/docx", json=payload)
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    assert len(r.content) > 0


def test_export_pdf():
    payload = {"topic": "IBS diet test pdf", "primary_keyword": "IBS", "geo_target": "USA"}
    r = client.post("/export/pdf", json=payload)
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert len(r.content) > 0

