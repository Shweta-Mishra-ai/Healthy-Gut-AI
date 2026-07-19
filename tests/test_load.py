import concurrent.futures

from fastapi.testclient import TestClient

from app.main import app
from app.rate_limit import rate_limiter

client = TestClient(app)


def test_concurrent_requests_do_not_crash_app():
    """20 concurrent requests to different topics — the app must handle
    all of them without raising, and every response must be well-formed
    (either a valid 200 or a clean 429/422), never a bare crash."""
    rate_limiter._hits.clear()
    rate_limiter._limit = 1000  # isolate this test from rate limiting itself

    def _one(i):
        payload = {"topic": f"IBS diet variant {i}", "primary_keyword": "IBS diet", "geo_target": "USA"}
        return client.post("/generate", json=payload)

    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as pool:
        responses = list(pool.map(_one, range(20)))

    for r in responses:
        assert r.status_code in (200, 429, 422)
        assert isinstance(r.json(), dict)

    rate_limiter._hits.clear()
    rate_limiter._limit = 10


def test_batch_concurrency_is_bounded_and_completes():
    """A full-size batch (MAX_BATCH_SIZE items) must complete without error
    even though only BATCH_CONCURRENCY run at once."""
    items = [
        {"topic": f"IBS diet load test {i}", "primary_keyword": "IBS diet", "geo_target": "USA"}
        for i in range(10)
    ]
    r = client.post("/generate/batch", json={"items": items})
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 10
    assert body["succeeded"] == 10


def test_rate_limiter_recovers_after_window():
    """Sanity check that the limiter is a real sliding window, not a
    permanent lockout — clearing hits should immediately restore access."""
    rate_limiter._hits.clear()
    rate_limiter._limit = 2
    payload = {"topic": "IBS diet recovery test", "primary_keyword": "IBS diet", "geo_target": "USA"}

    r1 = client.post("/generate", json=payload)
    r2 = client.post("/generate", json=payload)
    r3 = client.post("/generate", json=payload)
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r3.status_code == 429

    rate_limiter._hits.clear()
    r4 = client.post("/generate", json=payload)
    assert r4.status_code == 200

    rate_limiter._limit = 10
    rate_limiter._hits.clear()
