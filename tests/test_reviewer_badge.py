from fastapi.testclient import TestClient

from app.main import app
from app.review import ReviewStore

client = TestClient(app)


def _generate():
    return client.post("/generate", json={"topic": "Badge test topic", "primary_keyword": "IBS diet", "geo_target": "USA"}).json()


def test_approve_with_reviewer_name_and_credential():
    gen = _generate()
    review_id = gen["review_id"]
    r = client.post(f"/review/{review_id}/approve", json={
        "note": "Looks accurate", "reviewer_name": "Dr. Priya Sharma", "reviewer_credential": "MBBS, RMP"
    })
    assert r.status_code == 200
    body = r.json()
    assert body["reviewer_name"] == "Dr. Priya Sharma"
    assert body["reviewer_credential"] == "MBBS, RMP"
    assert body["reviewer_badge"] == "Reviewed by Dr. Priya Sharma, MBBS, RMP"


def test_approve_without_reviewer_info_has_no_badge():
    gen = _generate()
    review_id = gen["review_id"]
    r = client.post(f"/review/{review_id}/approve", json={"note": ""})
    assert r.status_code == 200
    assert r.json()["reviewer_badge"] is None


def test_approve_with_name_only_no_credential():
    gen = _generate()
    review_id = gen["review_id"]
    r = client.post(f"/review/{review_id}/approve", json={"reviewer_name": "Dr. Rao"})
    assert r.status_code == 200
    assert r.json()["reviewer_badge"] == "Reviewed by Dr. Rao"


def test_reviewer_name_length_validated():
    gen = _generate()
    review_id = gen["review_id"]
    r = client.post(f"/review/{review_id}/approve", json={"reviewer_name": "x" * 101})
    assert r.status_code == 422


def test_reviewer_credential_unsafe_chars_rejected():
    gen = _generate()
    review_id = gen["review_id"]
    r = client.post(f"/review/{review_id}/approve", json={"reviewer_name": "Dr. X", "reviewer_credential": "<script>alert(1)</script>"})
    assert r.status_code == 422


def test_review_queue_includes_badge_for_approved_items():
    gen = _generate()
    review_id = gen["review_id"]
    client.post(f"/review/{review_id}/approve", json={"reviewer_name": "Dr. Singh", "reviewer_credential": "MD"})
    items = client.get("/review/queue?status=approved").json()["items"]
    match = next(i for i in items if i["id"] == review_id)
    assert match["reviewer_badge"] == "Reviewed by Dr. Singh, MD"


def test_wordpress_dry_run_publish_includes_reviewer_badge_in_content():
    gen = _generate()
    review_id = gen["review_id"]
    client.post(f"/review/{review_id}/approve", json={"reviewer_name": "Dr. Mehta", "reviewer_credential": "MBBS"})
    r = client.post(f"/publish/wordpress/{review_id}?dry_run=true")
    assert r.status_code == 200
    sent_content = r.json()["would_send"]["content"]
    assert "Dr. Mehta" in sent_content
    assert "MBBS" in sent_content


def test_wordpress_dry_run_publish_without_reviewer_has_no_badge_text():
    gen = _generate()
    review_id = gen["review_id"]
    client.post(f"/review/{review_id}/approve", json={})
    r = client.post(f"/publish/wordpress/{review_id}?dry_run=true")
    assert r.status_code == 200
    assert "Reviewed by" not in r.json()["would_send"]["content"]


def test_store_reviewer_badge_computation_directly():
    from app.review import ReviewStatus
    store = ReviewStore()
    aid = store.register({}, "Direct topic", "kw")
    item = store.set_status(aid, ReviewStatus.approved, note="", reviewer_name="Dr. Test", reviewer_credential="MD")
    assert item["reviewer_badge"] == "Reviewed by Dr. Test, MD"
