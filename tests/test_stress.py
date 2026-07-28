import concurrent.futures
from fastapi.testclient import TestClient

from app.llm_providers import _extract_json
from app.main import app
from app.rate_limit import rate_limiter

client = TestClient(app)


def test_high_concurrency_multi_endpoint_stress():
    """Concurrently hits multiple API endpoints under multi-threaded pool load."""
    rate_limiter._hits.clear()
    rate_limiter._limit = 1000

    def _worker(i):
        if i % 4 == 0:
            return client.post("/generate", json={"topic": f"GERD management {i}", "primary_keyword": "GERD", "geo_target": "USA"})
        elif i % 4 == 1:
            return client.get(f"/outline?topic=IBS%20diet%20{i}&keyword=IBS")
        elif i % 4 == 2:
            return client.get(f"/rag/preview?topic=SIBO%20treatment%20{i}")
        else:
            return client.get("/dashboard/stats")

    with concurrent.futures.ThreadPoolExecutor(max_workers=30) as pool:
        responses = list(pool.map(_worker, range(60)))

    for r in responses:
        assert r.status_code in (200, 422, 429)

    rate_limiter._hits.clear()
    rate_limiter._limit = 10


def test_mixed_batch_payload_stress():
    """Generates a batch with a mixture of valid, out-of-scope, and edge-case inputs."""
    items = [
        {"topic": "IBS diet plan", "primary_keyword": "IBS diet", "geo_target": "USA"},
        {"topic": "Quantum physics computing", "primary_keyword": "Quantum", "geo_target": "USA"},
        {"topic": "SIBO diet guide", "primary_keyword": "SIBO diet", "geo_target": "India"},
        {"topic": "Cryptocurrency trading strategies", "primary_keyword": "Crypto", "geo_target": "UK"},
    ]
    res = client.post("/generate/batch", json={"items": items})
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 4
    assert data["failed"] == 2
    assert data["succeeded"] == 2


def test_sqlite_concurrent_read_write_stress():
    """Simulates high-volume concurrent review workflow operations on SQLite."""
    # Register 10 articles
    review_ids = []
    for i in range(10):
        r = client.post("/generate", json={"topic": f"Gut health topic {i}", "primary_keyword": "gut health", "geo_target": "USA"})
        assert r.status_code == 200
        review_ids.append(r.json()["review_id"])

    def _approve(rid):
        return client.post(f"/review/{rid}/approve", json={"note": "Looks good", "reviewer_name": "Dr. Smith", "reviewer_credential": "MD"})

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
        results = list(pool.map(_approve, review_ids))

    for r in results:
        assert r.status_code in (200, 409)

    counts = client.get("/review/counts").json()
    assert counts["total"] >= 10


def test_discovery_endpoints_whitespace_validation():
    """Ensures discovery endpoints reject empty/whitespace-only topics with 422."""
    for path in ("/outline?topic=%20%20", "/rag/preview?topic=", "/internal-links?topic=%20"):
        r = client.get(path)
        assert r.status_code == 422
        assert "error" in r.json()


def test_extract_json_handles_markdown_code_fences():
    """Tests _extract_json helper with various markdown code block formats."""
    fenced_json = "```json\n{\"optimized_article_markdown\": \"# Test\", \"provider_used\": \"mock\"}\n```"
    result = _extract_json(fenced_json)
    assert result["provider_used"] == "mock"

    raw_fenced = "```\n{\"key\": \"value\"}\n```"
    assert _extract_json(raw_fenced)["key"] == "value"
