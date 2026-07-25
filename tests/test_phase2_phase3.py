from fastapi.testclient import TestClient

from app.main import app
from app.dashboard import GenerationTracker

client = TestClient(app)


def test_outline_preview_in_scope():
    r = client.get("/outline", params={"topic": "IBS diet plan", "keyword": "IBS diet", "article_type": "pillar"})
    assert r.status_code == 200
    body = r.json()
    assert body["in_scope"] is True
    assert body["target_word_count"] == "2500-3000"
    assert len(body["planned_sections"]) >= 5
    assert len(body["grounding_sources"]) >= 1


def test_outline_preview_out_of_scope():
    r = client.get("/outline", params={"topic": "infectious disease epidemiology", "keyword": "epidemiology"})
    assert r.status_code == 200
    body = r.json()
    assert body["in_scope"] is False
    assert body["scope_note"] is not None
    assert body["grounding_sources"] == []


def test_generate_accepts_tone_field():
    payload = {"topic": "IBS diet plan tone test", "primary_keyword": "IBS diet", "geo_target": "USA", "tone": "patient_friendly"}
    r = client.post("/generate", json=payload)
    assert r.status_code == 200


def test_invalid_tone_rejected():
    payload = {"topic": "IBS diet plan", "primary_keyword": "IBS diet", "geo_target": "USA", "tone": "not_a_real_tone"}
    r = client.post("/generate", json=payload)
    assert r.status_code == 422


def test_export_markdown():
    payload = {"topic": "GERD relief md test", "primary_keyword": "acid reflux", "geo_target": "UK"}
    r = client.post("/export/markdown", json=payload)
    assert r.status_code == 200
    assert "markdown" in r.headers["content-type"]
    assert len(r.content) > 0


def test_export_json():
    payload = {"topic": "GERD relief json test", "primary_keyword": "acid reflux", "geo_target": "UK"}
    r = client.post("/export/json", json=payload)
    assert r.status_code == 200
    body = r.json()
    assert "optimized_article_markdown" in body
    assert "quality" in body
    assert "metrics" in body


def test_article_includes_references_section():
    payload = {"topic": "SIBO bloating references test", "primary_keyword": "SIBO symptoms", "geo_target": "USA"}
    r = client.post("/generate", json=payload)
    assert r.status_code == 200
    md = r.json()["optimized_article_markdown"]
    assert "Sources Referenced" in md


def test_readability_has_extended_metrics():
    from app.metrics import readability
    r = readability("This is a simple sentence. It has two sentences total for testing purposes here.")
    assert "gunningFogIndex" in r
    assert "avgSentenceLength" in r
    assert "gradeLevel" in r


def test_dashboard_stats_endpoint():
    r = client.get("/dashboard/stats")
    assert r.status_code == 200
    body = r.json()
    assert "total_requests" in body
    assert "avg_quality_score" in body
    assert "recent" in body


def test_dashboard_page_serves_html():
    r = client.get("/dashboard")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]


def test_tracker_summary_math():
    t = GenerationTracker(max_entries=10)
    t.record(topic="a", provider="groq", success=True, word_count=1000, quality_score=80)
    t.record(topic="b", provider="mock", success=True, word_count=500, quality_score=60, cached=True)
    t.record(topic="c", provider="", success=False, out_of_scope=True)
    summary = t.summary()
    assert summary["total_requests"] == 3
    assert summary["succeeded"] == 2
    assert summary["out_of_scope"] == 1
    assert summary["avg_quality_score"] == 70.0
    assert summary["cache_hit_rate_percent"] == 50.0
