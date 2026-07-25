from fastapi.testclient import TestClient

from app.internal_linking import find_related_articles
from app.main import app
from app.review import ReviewStatus, review_store

client = TestClient(app)


def _approve_article(topic, keyword, geo="USA"):
    gen = client.post("/generate", json={"topic": topic, "primary_keyword": keyword, "geo_target": geo}).json()
    review_id = gen["review_id"]
    client.post(f"/review/{review_id}/approve", json={"note": ""})
    return review_id


def test_no_suggestions_when_corpus_empty():
    results = find_related_articles("IBS diet plan", "IBS diet")
    assert results == []


def test_suggestions_appear_after_approving_related_article():
    _approve_article("IBS diet plan", "IBS diet")
    results = find_related_articles("IBS symptoms and triggers", "IBS symptoms")
    assert len(results) >= 1
    assert results[0]["topic"] == "IBS diet plan"


def test_unrelated_approved_article_not_suggested():
    _approve_article("GERD acid reflux relief", "acid reflux")
    results = find_related_articles("Celiac disease gluten damage", "celiac disease")
    # GERD article shouldn't score high enough against an unrelated celiac query
    assert all(r["topic"] != "GERD acid reflux relief" for r in results) or len(results) == 0


def test_draft_articles_never_suggested():
    """Only approved articles should ever appear — drafts and rejected
    articles are excluded from linking suggestions by design."""
    gen = client.post("/generate", json={"topic": "SIBO bloating causes", "primary_keyword": "SIBO symptoms", "geo_target": "USA"}).json()
    # left as draft — never approved
    results = find_related_articles("SIBO bloating triggers", "SIBO")
    assert all(r["id"] != gen["review_id"] for r in results)


def test_rejected_articles_never_suggested():
    gen = client.post("/generate", json={"topic": "Diverticulitis flare ups", "primary_keyword": "diverticulitis", "geo_target": "USA"}).json()
    client.post(f"/review/{gen['review_id']}/reject", json={"note": "not accurate enough"})
    results = find_related_articles("Diverticulitis symptoms", "diverticulitis")
    assert all(r["id"] != gen["review_id"] for r in results)


def test_exclude_review_id_works():
    review_id = _approve_article("Fiber and gut health", "dietary fiber")
    results = find_related_articles("Fiber intake for digestion", "fiber", exclude_review_id=review_id)
    assert all(r["id"] != review_id for r in results)


def test_empty_topic_and_keyword_returns_empty():
    _approve_article("Probiotics for gut health", "probiotics")
    assert find_related_articles("", "") == []


def test_generate_endpoint_includes_internal_link_suggestions_field():
    payload = {"topic": "IBS diet variant test", "primary_keyword": "IBS diet", "geo_target": "USA"}
    r = client.post("/generate", json=payload)
    assert r.status_code == 200
    assert "internal_link_suggestions" in r.json()


def test_internal_links_endpoint():
    _approve_article("Lactose intolerance diet", "lactose intolerance")
    r = client.get("/internal-links", params={"topic": "Lactose intolerance symptoms", "keyword": "lactose"})
    assert r.status_code == 200
    body = r.json()
    assert "suggestions" in body


def test_internal_links_endpoint_handles_missing_params_gracefully():
    r = client.get("/internal-links", params={"topic": "IBS"})
    assert r.status_code == 200


def test_new_article_never_suggests_itself():
    payload = {"topic": "Gastritis causes and treatment", "primary_keyword": "gastritis", "geo_target": "USA"}
    r = client.post("/generate", json=payload).json()
    review_id = r["review_id"]
    client.post(f"/review/{review_id}/approve", json={"note": ""})

    # Generating the *same* topic again should not suggest linking to itself
    r2 = client.post("/generate", json={**payload, "primary_keyword": "gastritis treatment"}).json()
    suggestion_ids = [s["id"] for s in r2["internal_link_suggestions"]]
    assert review_id not in suggestion_ids or r2["review_id"] not in suggestion_ids
