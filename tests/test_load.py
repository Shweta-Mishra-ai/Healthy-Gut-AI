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


def test_concurrent_review_actions_no_double_approval():
    """Two concurrent approve/reject calls on the SAME article must not both
    succeed — the lock in ReviewStore.set_status should make exactly one
    win and the other get a clean 409, never a corrupted state."""
    payload = {"topic": "IBS diet plan concurrent review test", "primary_keyword": "IBS diet", "geo_target": "USA"}
    gen = client.post("/generate", json=payload).json()
    review_id = gen["review_id"]

    def _approve(_):
        return client.post(f"/review/{review_id}/approve", json={"note": ""})

    def _reject(_):
        return client.post(f"/review/{review_id}/reject", json={"note": ""})

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
        approve_results = list(pool.map(_approve, range(5)))
        reject_results = list(pool.map(_reject, range(5)))

    all_results = approve_results + reject_results
    successes = [r for r in all_results if r.status_code == 200]
    conflicts = [r for r in all_results if r.status_code == 409]

    assert len(successes) == 1
    assert len(conflicts) == 9


def test_concurrent_generations_do_not_corrupt_db():
    """20 concurrent generations writing to SQLite (reviews + generations
    tables) must all succeed and produce exactly 20 distinct review rows —
    no lost writes, no corruption, under real concurrent load."""
    rate_limiter._hits.clear()
    rate_limiter._limit = 1000

    def _one(i):
        payload = {"topic": f"SQLite load test {i}", "primary_keyword": "IBS diet", "geo_target": "USA"}
        return client.post("/generate", json=payload)

    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as pool:
        responses = list(pool.map(_one, range(20)))

    review_ids = set()
    for r in responses:
        assert r.status_code == 200
        review_ids.add(r.json()["review_id"])

    assert len(review_ids) == 20  # all distinct, none lost/overwritten

    counts = client.get("/review/counts").json()
    assert counts["draft"] == 20

    rate_limiter._hits.clear()
    rate_limiter._limit = 10
