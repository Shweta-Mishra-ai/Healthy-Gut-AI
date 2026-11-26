"""Reviewer sign-off. The public badge printed on articles comes only from
the configured reviewer registry; a typed name is a self-attested internal
record that is never printed."""
import pytest
from fastapi.testclient import TestClient

from app import reviewers
from app.main import app
from app.review import ReviewStatus, ReviewStore
from app.reviewers import ReviewerRegistryError, parse_registry

client = TestClient(app)

REGISTRY = (
    '[{"id": "sharma", "name": "Dr. Priya Sharma", "credential": "MBBS, MD", "registration": "DMC-12345"},'
    ' {"id": "rao", "name": "Dr. Anita Rao", "credential": "MD (Gastroenterology)"}]'
)


@pytest.fixture
def registry(monkeypatch):
    monkeypatch.setattr(reviewers, "REVIEWERS", parse_registry(REGISTRY))


def _generate():
    return client.post("/generate", json={"topic": "Badge test topic", "primary_keyword": "IBS diet", "geo_target": "USA"}).json()


# --- without a registry: typed names are recorded, never published ---

def test_typed_reviewer_is_recorded_as_self_attested_without_a_public_badge():
    review_id = _generate()["review_id"]
    r = client.post(f"/review/{review_id}/approve", json={
        "note": "Looks accurate", "reviewer_name": "Dr. Priya Sharma", "reviewer_credential": "MBBS, RMP"
    })
    assert r.status_code == 200
    body = r.json()
    assert body["reviewer_name"] == "Dr. Priya Sharma"
    assert body["reviewer_verified"] is False
    assert body["reviewer_badge"] is None
    assert "self-attested" in body["reviewer_attestation"]


def test_approve_without_reviewer_info_has_no_badge():
    review_id = _generate()["review_id"]
    r = client.post(f"/review/{review_id}/approve", json={"note": ""})
    assert r.status_code == 200
    assert r.json()["reviewer_badge"] is None
    assert r.json()["reviewer_attestation"] is None


def test_unverified_name_is_not_printed_on_published_content():
    review_id = _generate()["review_id"]
    client.post(f"/review/{review_id}/approve", json={"reviewer_name": "Dr. Anyone", "reviewer_credential": "MD"})
    r = client.post(f"/publish/wordpress/{review_id}?dry_run=true")
    assert r.status_code == 200
    assert "Reviewed by" not in r.json()["would_send"]["content"]
    assert "Dr. Anyone" not in r.json()["would_send"]["content"]


def test_reviewer_name_length_validated():
    review_id = _generate()["review_id"]
    r = client.post(f"/review/{review_id}/approve", json={"reviewer_name": "x" * 101})
    assert r.status_code == 422


def test_reviewer_credential_unsafe_chars_rejected():
    review_id = _generate()["review_id"]
    r = client.post(f"/review/{review_id}/approve", json={"reviewer_name": "Dr. X", "reviewer_credential": "<script>alert(1)</script>"})
    assert r.status_code == 422


# --- with a registry: only registered reviewers can approve, and their badge is printed ---

def test_registered_reviewer_badge_includes_registration(registry):
    review_id = _generate()["review_id"]
    r = client.post(f"/review/{review_id}/approve", json={"reviewer_id": "sharma"})
    assert r.status_code == 200
    body = r.json()
    assert body["reviewer_verified"] is True
    assert body["reviewer_badge"] == "Reviewed for medical accuracy by Dr. Priya Sharma, MBBS, MD (Reg. No. DMC-12345)"


def test_registry_ignores_typed_identity_and_requires_a_known_reviewer(registry):
    review_id = _generate()["review_id"]
    missing = client.post(f"/review/{review_id}/approve", json={"reviewer_name": "Dr. Fake", "reviewer_credential": "MD"})
    unknown = client.post(f"/review/{review_id}/approve", json={"reviewer_id": "nobody"})
    assert missing.status_code == 422 and unknown.status_code == 422
    assert client.get(f"/review/{review_id}").json()["status"] == "draft"


def test_queue_and_publish_carry_the_registered_badge(registry):
    review_id = _generate()["review_id"]
    client.post(f"/review/{review_id}/approve", json={"reviewer_id": "rao"})
    items = client.get("/review/queue?status=approved").json()["items"]
    assert next(i for i in items if i["id"] == review_id)["reviewer_badge"] == "Reviewed for medical accuracy by Dr. Anita Rao, MD (Gastroenterology)"
    content = client.post(f"/publish/wordpress/{review_id}?dry_run=true").json()["would_send"]["content"]
    assert "Reviewed for medical accuracy by Dr. Anita Rao" in content


def test_reviewers_endpoint_lists_the_registry(registry):
    body = client.get("/reviewers").json()
    assert body["registry_enabled"] is True
    assert {r["id"] for r in body["reviewers"]} == {"sharma", "rao"}


def test_reviewers_endpoint_without_registry():
    assert client.get("/reviewers").json() == {"registry_enabled": False, "reviewers": []}


@pytest.mark.parametrize("raw,message", [
    ("not json", "valid JSON"),
    ('{"id": "x"}', "list"),
    ('[{"name": "Dr. X"}]', "'id' and a 'name'"),
    ('[{"id": "a", "name": "A"}, {"id": "a", "name": "B"}]', "duplicate"),
    ('[{"id": "a", "name": "<b>A</b>"}]', "disallowed"),
])
def test_registry_validation(raw, message):
    with pytest.raises(ReviewerRegistryError, match=message):
        parse_registry(raw)


def test_store_badge_requires_verified_flag():
    store = ReviewStore()
    a = store.register({}, "Direct topic A", "kw")
    b = store.register({}, "Direct topic B", "kw")
    typed = store.set_status(a, ReviewStatus.approved, reviewer_name="Dr. Test", reviewer_credential="MD")
    verified = store.set_status(b, ReviewStatus.approved, reviewer_name="Dr. Test", reviewer_credential="MD",
                                reviewer_registration="R-1", reviewer_verified=True)
    assert typed["reviewer_badge"] is None
    assert verified["reviewer_badge"] == "Reviewed for medical accuracy by Dr. Test, MD (Reg. No. R-1)"


def test_approved_articles_are_never_pruned():
    store = ReviewStore(max_entries=3)
    keep = store.register({}, "Published pillar", "kw")
    store.set_status(keep, ReviewStatus.approved)
    store.record_wordpress_post(keep, 9, "https://site/?p=9")
    for i in range(5):
        store.register({}, f"draft {i}", "kw")
    assert store.get(keep)["wp_post_id"] == 9
    # The 3 newest rows (all drafts) are kept, older drafts pruned, and the
    # approved article survives although it is outside the newest 3.
    assert store.counts() == {"draft": 3, "approved": 1, "rejected": 0, "total": 4}


def test_queue_pagination_and_search():
    for i in range(5):
        client.post("/generate", json={"topic": f"Bloating guide {i}", "primary_keyword": "bloating", "geo_target": "India"})
    client.post("/generate", json={"topic": "Constipation relief", "primary_keyword": "constipation", "geo_target": "India"})
    page1 = client.get("/review/queue?status=draft&limit=2").json()
    page2 = client.get("/review/queue?status=draft&limit=2&offset=2").json()
    assert len(page1["items"]) == 2 and page1["has_more"] is True
    assert {i["id"] for i in page1["items"]}.isdisjoint({i["id"] for i in page2["items"]})
    found = client.get("/review/queue?status=draft&q=constipation").json()["items"]
    assert [i["topic"] for i in found] == ["Constipation relief"]
    assert client.get("/review/queue?status=draft&q=100%25_").json()["items"] == []


def test_registered_approval_adds_reviewed_by_to_structured_data(registry):
    review_id = _generate()["review_id"]
    client.post(f"/review/{review_id}/approve", json={"reviewer_id": "sharma"})
    article = client.get(f"/review/{review_id}").json()["article"]
    node = article["schema_json_ld"]["@graph"][0]
    assert node["reviewedBy"]["name"] == "Dr. Priya Sharma"
    assert node["reviewedBy"]["identifier"] == "DMC-12345"


def test_unverified_approval_adds_no_reviewed_by():
    review_id = _generate()["review_id"]
    client.post(f"/review/{review_id}/approve", json={"reviewer_name": "Dr. Anyone"})
    article = client.get(f"/review/{review_id}").json()["article"]
    assert "reviewedBy" not in article["schema_json_ld"]["@graph"][0]
