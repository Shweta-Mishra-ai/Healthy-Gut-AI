import json
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app import llm_providers
from app.config import settings
from app.main import app
from app.mock_content import mock_result
from app.prompts import build_prompts

client = TestClient(app)

PAYLOAD = {"topic": "IBS diet plan", "primary_keyword": "IBS diet", "geo_target": "India"}
NOTE = "Remove the claim that fibre cures IBS"


def test_prompt_carries_the_feedback_in_english_and_hindi():
    en, _ = build_prompts("IBS diet", "IBS", "India", "supporting", "en", feedback=NOTE)
    hi, _ = build_prompts("पेट में गैस", "गैस", "भारत", "supporting", "hi", feedback=NOTE)
    plain, _ = build_prompts("IBS diet", "IBS", "India", "supporting", "en")
    assert "REVIEWER FEEDBACK" in en and NOTE in en
    assert "समीक्षक की प्रतिक्रिया" in hi and NOTE in hi
    assert "REVIEWER FEEDBACK" not in plain


def _reject(review_id, note=NOTE):
    assert client.post(f"/review/{review_id}/reject", json={"note": note}).status_code == 200


def test_regeneration_after_rejection_passes_the_note_to_the_generator():
    first = client.post("/generate", json=PAYLOAD).json()
    _reject(first["review_id"])

    fake = AsyncMock(side_effect=lambda *a, **kw: mock_result(PAYLOAD["topic"], PAYLOAD["primary_keyword"], "India"))
    with patch("app.routers.generation.llm_generate", fake):
        client.post("/generate", json=PAYLOAD)
    assert fake.call_args.kwargs["feedback"] == NOTE


def test_note_is_used_once_a_newer_draft_exists_it_is_not_repeated():
    first = client.post("/generate", json=PAYLOAD).json()
    _reject(first["review_id"])
    client.post("/generate", json=PAYLOAD)  # consumes the note -> new draft

    from app.cache import article_cache
    article_cache.clear()
    fake = AsyncMock(side_effect=lambda *a, **kw: mock_result(PAYLOAD["topic"], PAYLOAD["primary_keyword"], "India"))
    with patch("app.routers.generation.llm_generate", fake):
        client.post("/generate", json=PAYLOAD)
    assert fake.call_args.kwargs["feedback"] == ""


def test_rejection_without_a_note_sends_no_feedback():
    first = client.post("/generate", json=PAYLOAD).json()
    _reject(first["review_id"], note="")
    fake = AsyncMock(side_effect=lambda *a, **kw: mock_result(PAYLOAD["topic"], PAYLOAD["primary_keyword"], "India"))
    with patch("app.routers.generation.llm_generate", fake):
        client.post("/generate", json=PAYLOAD)
    assert fake.call_args.kwargs["feedback"] == ""


def test_template_mode_reports_that_feedback_was_not_applied():
    first = client.post("/generate", json=PAYLOAD).json()
    _reject(first["review_id"])
    second = client.post("/generate", json=PAYLOAD).json()
    assert second["reviewer_feedback"] == {"note": NOTE, "applied": False}


@pytest.mark.asyncio
async def test_live_provider_receives_the_feedback_in_its_drafting_prompt(monkeypatch):
    monkeypatch.setattr(settings, "GROQ_API_KEY", "test-key")
    monkeypatch.setattr(settings, "OPENROUTER_API_KEY", "")
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "")
    prompts_seen = []
    body = "# IBS Diet\n\n" + "A balanced IBS diet plan may help some people manage symptoms. " * 30

    async def fake_call(base_url, api_key, model, prompt, json_mode=False, timeout=None):
        prompts_seen.append(prompt)
        if not json_mode:
            return body
        return json.dumps({"optimized_article_markdown": body, "meta_description": "IBS diet guide",
                           "faqs": [], "url_slug": "ibs-diet"})

    monkeypatch.setattr(llm_providers, "_call_openai_compatible", fake_call)
    result = await llm_providers.llm_generate("IBS diet plan", "IBS diet", "India", "supporting", feedback=NOTE)
    assert NOTE in prompts_seen[0]
    assert result["reviewer_feedback"] == {"note": NOTE, "applied": True}


def test_queue_summary_carries_the_request_for_regeneration():
    first = client.post("/generate", json=PAYLOAD).json()
    _reject(first["review_id"])
    items = client.get("/review/queue?status=rejected").json()["items"]
    assert items[0]["request"]["geo_target"] == "India"
