from fastapi.testclient import TestClient

from app.llm_providers import _ensure_meta_variants, _mock_result
from app.main import app
from app.quality import assess_quality

client = TestClient(app)


def test_mock_result_has_3_variants():
    result = _mock_result("IBS diet plan", "IBS diet", "USA")
    variants = result["meta_description_variants"]
    assert len(variants) == 3
    assert all(isinstance(v, str) and v for v in variants)


def test_generate_endpoint_returns_variants():
    payload = {"topic": "GERD relief variants test", "primary_keyword": "acid reflux", "geo_target": "UK"}
    r = client.post("/generate", json=payload)
    assert r.status_code == 200
    body = r.json()
    assert "meta_description_variants" in body
    assert len(body["meta_description_variants"]) >= 2


def test_safety_net_fills_missing_variants_from_primary():
    result = {"meta_description": "A short meta description about gut health topics."}
    fixed = _ensure_meta_variants(result)
    assert len(fixed["meta_description_variants"]) >= 1
    assert fixed["meta_description_variants"][0] == result["meta_description"]


def test_safety_net_preserves_good_variants():
    result = {
        "meta_description": "Primary description here for testing purposes only today.",
        "meta_description_variants": [
            "Variant one about gut health for testing purposes here today.",
            "Variant two, a different angle on gut health for testing purposes.",
            "Variant three, question-led: struggling with gut health issues today?",
        ],
    }
    fixed = _ensure_meta_variants(dict(result))
    assert fixed["meta_description_variants"] == result["meta_description_variants"]


def test_safety_net_handles_completely_empty_result():
    result = {}
    fixed = _ensure_meta_variants(result)
    assert isinstance(fixed["meta_description_variants"], list)
    assert len(fixed["meta_description_variants"]) >= 1


def test_safety_net_filters_out_non_string_junk():
    result = {"meta_description": "Fallback description text for testing purposes only today.", "meta_description_variants": [123, None, "", "  "]}
    fixed = _ensure_meta_variants(result)
    assert all(isinstance(v, str) and v.strip() for v in fixed["meta_description_variants"])


def test_quality_flags_too_few_variants():
    result = {
        "optimized_article_markdown": "# T\n\n" + ("word " * 1200) + "*Medical Disclaimer: consult a doctor.*",
        "meta_description": "A" * 140,
        "meta_description_variants": ["A" * 140],
        "url_slug": "test-slug",
        "faqs": [{"question": "q1", "answer": "a1"}, {"question": "q2", "answer": "a2"}],
        "metrics": {"readability": {"fleschReadingEase": 60.0}},
    }
    q = assess_quality(result, "topic", "keyword", "supporting")
    assert any("variant" in f.lower() for f in q["flags"])


def test_quality_does_not_flag_when_3_good_variants():
    result = {
        "optimized_article_markdown": "# T\n\ntopic keyword " + ("word " * 1200) + "*Medical Disclaimer: consult a doctor.*",
        "meta_description": "A complete description about topic keyword that covers symptoms diet and management for readers today.",
        "meta_description_variants": [
            "A complete description about topic keyword that covers symptoms diet and management for readers today.",
            "Struggling with topic keyword? Here is a full description of causes diet and management options for you.",
            "Topic keyword explained in detail: symptoms, causes, diet tips, and when to see a doctor, right here now.",
        ],
        "url_slug": "test-slug",
        "faqs": [{"question": "q1", "answer": "a1"}, {"question": "q2", "answer": "a2"}],
        "metrics": {"readability": {"fleschReadingEase": 60.0}},
    }
    q = assess_quality(result, "topic", "keyword", "supporting")
    assert not any("variant" in f.lower() for f in q["flags"])
