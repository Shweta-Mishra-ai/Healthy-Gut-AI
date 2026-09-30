from fastapi.testclient import TestClient

from app.main import app
from app.review import review_store

client = TestClient(app)

PAYLOAD = {"topic": "IBS diet plan", "primary_keyword": "IBS diet", "geo_target": "India"}

EDITED = """# IBS Diet Plan

An IBS diet plan focuses on identifying personal trigger foods. Many people find relief with a
low-FODMAP approach introduced under the guidance of a dietitian, followed by careful
reintroduction of foods one group at a time.

## Foods that often help

- Oats and other soluble fibre
- Lactose-free yoghurt

Always discuss major diet changes with a qualified clinician before starting them.
"""


def _draft():
    return client.post("/generate", json=PAYLOAD).json()


def test_edit_replaces_the_body_and_rescores_it():
    article = _draft()
    r = client.post(f"/review/{article['review_id']}/edit", json={"article_markdown": EDITED, "editor_name": "Dr. Rao"})
    assert r.status_code == 200, r.text
    stored = r.json()["article"]
    assert stored["optimized_article_markdown"].startswith("# IBS Diet Plan")
    assert stored["metrics"]["wordCount"] == len(stored["optimized_article_markdown"].split())
    assert stored["metrics"]["wordCount"] != article["metrics"]["wordCount"]
    assert "score" in stored["quality"] and "risk_level" in stored["compliance"]
    assert stored["edits"][-1]["editor"] == "Dr. Rao"
    # the review row's summary columns follow the edit
    assert r.json()["word_count"] == stored["metrics"]["wordCount"]


def test_edit_that_removes_the_disclaimer_gets_it_back():
    article = _draft()
    r = client.post(f"/review/{article['review_id']}/edit", json={"article_markdown": EDITED})
    assert "Medical Disclaimer" in r.json()["article"]["optimized_article_markdown"]


def test_edit_that_adds_a_cure_claim_is_flagged_by_compliance():
    article = _draft()
    risky = EDITED + "\nThis diet will cure IBS permanently and is guaranteed to work for everyone.\n"
    stored = client.post(f"/review/{article['review_id']}/edit", json={"article_markdown": risky}).json()["article"]
    assert stored["compliance"]["counts"].get("blocker", 0) >= 1


def test_only_drafts_can_be_edited():
    article = _draft()
    client.post(f"/review/{article['review_id']}/approve", json={})
    r = client.post(f"/review/{article['review_id']}/edit", json={"article_markdown": EDITED})
    assert r.status_code == 409
    assert client.post("/review/nope123/edit", json={"article_markdown": EDITED}).status_code == 404


def test_edit_validation():
    article = _draft()
    assert client.post(f"/review/{article['review_id']}/edit", json={"article_markdown": "too short"}).status_code == 422
    assert client.post(f"/review/{article['review_id']}/edit",
                       json={"article_markdown": EDITED, "editor_name": "<b>x</b>"}).status_code == 422


def test_edit_updates_the_meta_description_and_variants():
    article = _draft()
    meta = "A practical IBS diet plan: trigger foods, low-FODMAP basics and when to see a doctor in India today."
    stored = client.post(f"/review/{article['review_id']}/edit",
                         json={"article_markdown": EDITED, "meta_description": meta}).json()["article"]
    assert stored["meta_description"] == meta
    assert stored["meta_description_variants"][0] == meta
    assert len(stored["meta_description_variants"]) <= 3


def test_cache_hit_serves_the_edited_article():
    article = _draft()
    client.post(f"/review/{article['review_id']}/edit", json={"article_markdown": EDITED})
    again = client.post("/generate", json=PAYLOAD).json()
    assert again["cached"] is True
    assert again["review_id"] == article["review_id"]
    assert again["optimized_article_markdown"].startswith("# IBS Diet Plan")


def test_export_by_id_uses_the_edited_article():
    article = _draft()
    client.post(f"/review/{article['review_id']}/edit", json={"article_markdown": EDITED})
    md = client.get(f"/articles/{article['review_id']}/export/markdown").text
    assert md.startswith("# IBS Diet Plan")


def test_edit_keeps_hindi_scoring_for_rows_without_a_stored_request():
    """Rows written before the request was saved with the article fall back
    to reading the language off the text."""
    article = client.post("/generate", json={"topic": "पेट में गैस", "primary_keyword": "गैस",
                                             "geo_target": "भारत", "language": "hi"}).json()
    item = review_store.get(article["review_id"])
    legacy = dict(item["article"])
    legacy.pop("request", None)
    review_store.update_article(article["review_id"], legacy)

    hindi = "# पेट में गैस\n\n" + "पेट में गैस बनना एक आम समस्या है और सही आहार से इसमें राहत मिल सकती है। " * 8
    stored = client.post(f"/review/{article['review_id']}/edit", json={"article_markdown": hindi}).json()["article"]
    assert stored["language_check"]["ok"] is True
    assert "चिकित्सा अस्वीकरण" in stored["optimized_article_markdown"]
