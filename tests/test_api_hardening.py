"""Regression tests for the middleware, streaming and export bugs found in
the audit. Each test here maps to a specific failure that shipped silently."""

import importlib
import json

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.db import reset_db_for_tests
from app.main import app

client = TestClient(app)

SINGLE = {"topic": "IBS diet", "primary_keyword": "IBS diet tips", "geo_target": "Mumbai, India"}


def setup_function():
    reset_db_for_tests()


# --- API key gating -----------------------------------------------------

@pytest.fixture
def api_key(monkeypatch):
    monkeypatch.setattr(settings, "API_KEY", "secret-key")
    return "secret-key"


def test_api_routes_require_the_key_when_set(api_key):
    assert client.post("/generate", json=SINGLE).status_code == 401
    assert client.get("/review/queue").status_code == 401
    assert client.post("/export/pdf", json=SINGLE).status_code == 401


def test_correct_key_is_accepted(api_key):
    res = client.post("/generate", json=SINGLE, headers={"X-API-Key": api_key})
    assert res.status_code == 200


def test_html_pages_stay_reachable_when_a_key_is_set(api_key):
    """A browser cannot attach a header to a top-level navigation, so
    blocking these documents made the review workflow unreachable. The data
    behind them is still gated (see the queue check above)."""
    for path in ("/review", "/dashboard"):
        res = client.get(path)
        assert res.status_code == 200
        assert "text/html" in res.headers["content-type"]


def test_health_is_never_gated(api_key):
    assert client.get("/health").status_code == 200


def test_no_key_configured_means_no_gate():
    assert client.get("/review/queue").status_code == 200


# --- rate limiting ------------------------------------------------------

def test_export_endpoints_are_rate_limited(monkeypatch):
    """/export/* runs the same generation pipeline as /generate, so leaving
    it unmetered was a free bypass of the limiter and of provider spend."""
    from app.main import RATE_LIMITED_PATHS
    assert "/export/pdf" in RATE_LIMITED_PATHS
    assert "/export/batch/zip" in RATE_LIMITED_PATHS
    assert "/generate/batch/stream" in RATE_LIMITED_PATHS


def test_rate_limit_returns_retry_after(monkeypatch):
    from app.main import rate_limiter
    monkeypatch.setattr(rate_limiter, "_limit", 1)
    rate_limiter._hits.clear()
    first = client.post("/generate", json=SINGLE)
    second = client.post("/generate", json=SINGLE)
    assert first.status_code == 200
    assert second.status_code == 429
    assert int(second.headers["Retry-After"]) >= 1
    rate_limiter._hits.clear()


# --- request identity and headers ---------------------------------------

def test_every_response_carries_a_request_id_and_security_headers():
    res = client.get("/health")
    assert res.headers["X-Request-ID"]
    assert res.headers["X-Content-Type-Options"] == "nosniff"
    assert res.headers["X-Frame-Options"] == "DENY"


def test_supplied_request_id_is_echoed_back():
    res = client.get("/health", headers={"X-Request-ID": "trace-me-123"})
    assert res.headers["X-Request-ID"] == "trace-me-123"


# --- streaming batch ----------------------------------------------------

def test_batch_stream_emits_one_line_per_article():
    payload = {"items": [
        {"topic": "IBS diet", "primary_keyword": "IBS diet tips", "geo_target": "USA"},
        {"topic": "GERD relief", "primary_keyword": "acid reflux relief", "geo_target": "UK"},
    ]}
    with client.stream("POST", "/generate/batch/stream", json=payload) as res:
        assert res.status_code == 200
        assert res.headers["content-type"].startswith("application/x-ndjson")
        events = [json.loads(line) for line in res.iter_lines() if line.strip()]

    assert events[0] == {"type": "start", "total": 2}
    items = [e for e in events if e["type"] == "item"]
    assert len(items) == 2
    assert {e["index"] for e in items} == {0, 1}
    assert all(e["result"]["optimized_article_markdown"] for e in items)
    assert events[-1] == {"type": "summary", "total": 2, "succeeded": 2, "failed": 0}


def test_batch_stream_reports_per_item_failures_without_killing_the_run():
    payload = {"items": [
        {"topic": "IBS diet", "primary_keyword": "IBS diet tips", "geo_target": "USA"},
        {"topic": "quantum computing hardware", "primary_keyword": "qubit design", "geo_target": "USA"},
    ]}
    with client.stream("POST", "/generate/batch/stream", json=payload) as res:
        events = [json.loads(line) for line in res.iter_lines() if line.strip()]

    summary = events[-1]
    assert summary["total"] == 2
    # The off-topic item is returned as a failed item, not a 500 for the batch.
    assert summary["failed"] == 1
    failed = next(e for e in events if e["type"] == "item" and "error" in e["result"])
    assert failed["result"]["out_of_scope"] is True


# --- enrichment on the response -----------------------------------------

def test_generate_returns_the_full_analysis_pack():
    data = client.post("/generate", json=SINGLE).json()
    for key in ("metrics", "quality", "compliance", "seo", "duplication", "schema_json_ld", "language_check"):
        assert key in data, f"missing {key}"
    assert data["schema_json_ld"]["@context"] == "https://schema.org"
    assert data["seo"]["social"]["title_tag_variants"]


def test_cached_result_refreshes_library_relative_fields():
    """Internal links and the duplicate scan describe the rest of the
    library, which changes after the article was cached — serving the
    snapshot meant they were permanently stale."""
    first = client.post("/generate", json=SINGLE).json()
    assert first["cached"] is False
    # Nothing else exists yet, so the first scan compares against an empty
    # library (its own entry is excluded).
    assert first["duplication"]["corpus_size"] == 0

    client.post("/generate", json={
        "topic": "GERD relief", "primary_keyword": "acid reflux relief", "geo_target": "UK",
    })

    second = client.post("/generate", json=SINGLE).json()
    assert second["cached"] is True
    assert "internal_link_suggestions" in second
    # Recomputed against the library as it stands now, not the snapshot taken
    # when this article was first cached.
    assert second["duplication"]["corpus_size"] == 1


# --- analyze ------------------------------------------------------------

def test_analyze_scores_pasted_text_without_generating():
    bad = ("# Miracle fix\n\nThis diet cures IBS permanently. Take 500 mg daily. "
           "There is no need to see a doctor if you follow this plan.")
    res = client.post("/analyze", json={"article_markdown": bad, "primary_keyword": "ibs cure"})
    assert res.status_code == 200
    data = res.json()
    assert data["compliance"]["risk_level"] == "blocked"
    assert data["quality"]["score"] < 60
    assert "optimized_article_markdown" not in data


def test_analyze_rejects_a_too_short_body():
    assert client.post("/analyze", json={"article_markdown": "too short"}).status_code == 422


def test_analyze_defaults_topic_to_the_first_heading():
    body = "# Living with IBS\n\n" + ("Detailed guidance about digestive health. " * 10)
    data = client.post("/analyze", json={"article_markdown": body}).json()
    assert data["topic"] == "Living with IBS"


# --- publish gating -----------------------------------------------------

def test_publishing_is_blocked_by_compliance_blockers(monkeypatch):
    from app.review import ReviewStatus, review_store
    article = {
        "optimized_article_markdown": "This diet cures IBS permanently.",
        "compliance": {"findings": [
            {"severity": "blocker", "code": "absolute_cure_claim", "message": "Promises a cure.",
             "evidence": "", "matched": "cures ibs"},
        ]},
    }
    review_id = review_store.register(article, "IBS", "ibs cure")
    review_store.set_status(review_id, ReviewStatus.approved)

    res = client.post(f"/publish/wordpress/{review_id}?dry_run=true")
    assert res.status_code == 409
    assert res.json()["compliance_blockers"]

    override = client.post(f"/publish/wordpress/{review_id}?dry_run=true&override_compliance=true")
    assert override.status_code == 200


def test_review_queue_surfaces_compliance_and_duplication_status():
    client.post("/generate", json=SINGLE)
    items = client.get("/review/queue").json()["items"]
    assert items
    assert items[0]["compliance_risk"] in ("clear", "review", "blocked")
    assert "duplication_status" in items[0]


def test_debug_route_lists_the_new_endpoints():
    routes = client.get("/debug").json()["routes"]
    assert "/generate/batch/stream" in routes
    assert "/analyze" in routes


def test_api_module_imports_cleanly():
    """The serverless entrypoint imports app.main — a broken import here is
    invisible until a cold start in production."""
    assert importlib.import_module("api.index").handler
