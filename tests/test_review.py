from fastapi.testclient import TestClient

from app.main import app
from app.review import ReviewStore, ReviewNotFoundError, InvalidTransitionError, ReviewStatus

client = TestClient(app)


def test_generate_registers_draft_with_review_id():
    payload = {"topic": "IBS diet plan review test", "primary_keyword": "IBS diet", "geo_target": "USA"}
    r = client.post("/generate", json=payload)
    assert r.status_code == 200
    body = r.json()
    assert "review_id" in body
    assert body["review_status"] == "draft"


def test_review_queue_lists_drafts():
    payload = {"topic": "IBS diet plan queue test", "primary_keyword": "IBS diet", "geo_target": "USA"}
    client.post("/generate", json=payload)
    r = client.get("/review/queue?status=draft")
    assert r.status_code == 200
    items = r.json()["items"]
    assert any(i["topic"] == "IBS diet plan queue test" for i in items)


def test_review_queue_exposes_quality_flags():
    # Regression test: the queue list used to drop quality.flags entirely,
    # so a low score showed up with zero explanation of *why* it was low
    # (e.g. mixed-language output, missing disclaimer, weak keyword
    # placement). The summary row must now carry them through.
    payload = {"topic": "IBS diet plan flags test", "primary_keyword": "IBS diet", "geo_target": "USA"}
    gen = client.post("/generate", json=payload)
    assert gen.status_code == 200
    expected_flags = gen.json()["quality"]["flags"]

    r = client.get("/review/queue?status=draft")
    assert r.status_code == 200
    items = r.json()["items"]
    match = next(i for i in items if i["topic"] == "IBS diet plan flags test")
    assert "quality_flags" in match
    assert match["quality_flags"] == expected_flags
    # And the field must never leak the full article body.
    assert "article_json" not in match


def test_review_queue_invalid_status_rejected():
    r = client.get("/review/queue?status=not_a_status")
    assert r.status_code == 422


def test_review_get_nonexistent_returns_404():
    r = client.get("/review/doesnotexist123")
    assert r.status_code == 404


def test_review_approve_nonexistent_returns_404():
    r = client.post("/review/doesnotexist123/approve", json={"note": "looks good"})
    assert r.status_code == 404


def test_review_approve_flow():
    payload = {"topic": "IBS diet plan approve test", "primary_keyword": "IBS diet", "geo_target": "USA"}
    gen = client.post("/generate", json=payload).json()
    review_id = gen["review_id"]

    r = client.post(f"/review/{review_id}/approve", json={"note": "reviewed, looks accurate"})
    assert r.status_code == 200
    assert r.json()["status"] == "approved"

    fetched = client.get(f"/review/{review_id}").json()
    assert fetched["status"] == "approved"
    assert fetched["reviewer_note"] == "reviewed, looks accurate"


def test_review_reject_flow():
    payload = {"topic": "IBS diet plan reject test", "primary_keyword": "IBS diet", "geo_target": "USA"}
    gen = client.post("/generate", json=payload).json()
    review_id = gen["review_id"]

    r = client.post(f"/review/{review_id}/reject", json={"note": "needs more detail"})
    assert r.status_code == 200
    assert r.json()["status"] == "rejected"


def test_double_review_action_returns_conflict():
    payload = {"topic": "IBS diet plan double review test", "primary_keyword": "IBS diet", "geo_target": "USA"}
    gen = client.post("/generate", json=payload).json()
    review_id = gen["review_id"]

    r1 = client.post(f"/review/{review_id}/approve", json={"note": ""})
    assert r1.status_code == 200
    r2 = client.post(f"/review/{review_id}/reject", json={"note": ""})
    assert r2.status_code == 409


def test_review_note_length_validated():
    payload = {"topic": "IBS diet plan note test", "primary_keyword": "IBS diet", "geo_target": "USA"}
    gen = client.post("/generate", json=payload).json()
    review_id = gen["review_id"]

    r = client.post(f"/review/{review_id}/approve", json={"note": "x" * 501})
    assert r.status_code == 422


def test_review_note_unsafe_chars_rejected():
    payload = {"topic": "IBS diet plan unsafe note test", "primary_keyword": "IBS diet", "geo_target": "USA"}
    gen = client.post("/generate", json=payload).json()
    review_id = gen["review_id"]

    r = client.post(f"/review/{review_id}/approve", json={"note": "<script>alert(1)</script>"})
    assert r.status_code == 422


def test_review_counts_endpoint():
    r = client.get("/review/counts")
    assert r.status_code == 200
    body = r.json()
    assert set(body.keys()) == {"draft", "approved", "rejected", "total"}


def test_review_page_serves_html():
    r = client.get("/review")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]


def test_cached_hit_reuses_same_review_id():
    payload = {"topic": "IBS diet plan cache review test unique", "primary_keyword": "IBS diet", "geo_target": "USA"}
    r1 = client.post("/generate", json=payload).json()
    r2 = client.post("/generate", json=payload).json()
    assert r1["review_id"] == r2["review_id"]


# --- Unit tests on the store directly (isolated, no FastAPI) ---

def test_store_register_and_get():
    store = ReviewStore()
    aid = store.register({"quality": {"score": 80}, "metrics": {"wordCount": 1000}}, "Topic A", "keyword a")
    item = store.get(aid)
    assert item["topic"] == "Topic A"
    assert item["status"] == "draft"


def test_store_get_missing_raises():
    store = ReviewStore()
    try:
        store.get("nope")
        assert False, "should have raised"
    except ReviewNotFoundError:
        pass


def test_store_set_status_twice_raises():
    store = ReviewStore()
    aid = store.register({}, "Topic B", "kw")
    store.set_status(aid, ReviewStatus.approved)
    try:
        store.set_status(aid, ReviewStatus.rejected)
        assert False, "should have raised"
    except InvalidTransitionError:
        pass


def test_store_eviction_respects_max_entries():
    store = ReviewStore(max_entries=3)
    ids = [store.register({}, f"Topic {i}", "kw") for i in range(5)]
    assert store.counts()["total"] == 3
    # oldest two should be gone
    try:
        store.get(ids[0])
        assert False
    except ReviewNotFoundError:
        pass
    assert store.get(ids[-1])["topic"] == "Topic 4"
