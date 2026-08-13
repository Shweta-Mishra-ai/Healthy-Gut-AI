"""The Hindi-output guard: contaminated generations must be rejected, not
flagged after the fact and served anyway."""

import asyncio

import pytest

from app import llm_providers
from app.config import settings
from app.language import (
    MIN_SCRIPT_PURITY,
    check_language,
    find_foreign_script_chars,
    script_purity,
    strip_foreign_script,
)
from app.llm_providers import ProviderOutputError, validate_provider_result

HINDI_BODY = (
    "पेट की समस्याएँ आज बहुत आम हैं। फाइबर युक्त आहार और पर्याप्त पानी पाचन तंत्र को "
    "स्वस्थ रखने में मदद करते हैं। दही जैसे फर्मेंटेड खाद्य पदार्थ आंतों के अच्छे बैक्टीरिया "
    "को बढ़ावा देते हैं। यदि लक्षण तीन सप्ताह से अधिक बने रहें तो डॉक्टर से परामर्श लें। "
) * 6


def test_clean_hindi_passes():
    verdict = check_language(HINDI_BODY, "hi")
    assert verdict["ok"] is True
    assert verdict["purity"] > MIN_SCRIPT_PURITY
    assert verdict["foreign_scripts"] == {}


def test_cjk_contamination_is_rejected():
    contaminated = HINDI_BODY + " 消化系统健康 और पाचन।"
    verdict = check_language(contaminated, "hi")
    assert verdict["ok"] is False
    assert "Han" in verdict["foreign_scripts"]
    assert "different writing system" in verdict["reason"]


def test_cyrillic_contamination_is_rejected():
    verdict = check_language(HINDI_BODY + " Пищеварение здоровье", "hi")
    assert verdict["ok"] is False
    assert "Cyrillic" in verdict["foreign_scripts"]


def test_wrong_language_entirely_is_rejected():
    verdict = check_language("This article came back in English despite the Hindi request.", "hi")
    assert verdict["ok"] is False
    assert "wrong language" in verdict["reason"]


def test_english_with_latin_keyword_in_hindi_article_is_allowed():
    """Technical terms and the SEO keyword are legitimately left in Latin
    script inside Hindi copy — that must not trip the guard."""
    mixed = HINDI_BODY + " IBS और FODMAP डाइट के बारे में जानकारी।"
    assert check_language(mixed, "hi")["ok"] is True


def test_one_or_two_stray_characters_tolerated():
    """A single quoted character from a source name is not a script break."""
    assert check_language(HINDI_BODY + " 健", "hi")["ok"] is True


def test_english_articles_are_not_script_checked_for_purity():
    assert check_language("A perfectly ordinary English article about gut health.", "en")["ok"] is True


def test_english_article_still_rejects_foreign_script():
    verdict = check_language("Gut health guide 消化系统健康 continues here.", "en")
    assert verdict["ok"] is False


def test_script_purity_on_empty_and_letterless_text():
    assert script_purity("", "hi") == 1.0
    assert script_purity("123 456 !!", "hi") == 1.0


def test_find_foreign_script_chars_counts_by_script():
    found = find_foreign_script_chars("hello 世界 мир")
    assert found["Han"] == 2
    assert found["Cyrillic"] == 3


def test_strip_foreign_script_removes_only_foreign_characters():
    cleaned = strip_foreign_script("पाचन 消化 स्वास्थ्य")
    assert "消" not in cleaned
    assert "पाचन" in cleaned and "स्वास्थ्य" in cleaned


def test_validate_provider_result_rejects_contaminated_hindi():
    with pytest.raises(ProviderOutputError, match="language check failed"):
        validate_provider_result({"optimized_article_markdown": HINDI_BODY + " 消化系统健康 खराब"}, "hi")


def test_validate_provider_result_rejects_empty_article():
    with pytest.raises(ProviderOutputError, match="no article body"):
        validate_provider_result({"optimized_article_markdown": "   "}, "en")


def test_validate_provider_result_rejects_refusal_length_response():
    with pytest.raises(ProviderOutputError, match="below the"):
        validate_provider_result(
            {"optimized_article_markdown": "I'm sorry, I can't help with medical content."}, "en"
        )


def test_validate_provider_result_normalizes_loose_types():
    result = validate_provider_result({
        "optimized_article_markdown": " ".join(["gut health advice"] * 100),
        "faqs": {"question": "What is IBS?", "answer": "A functional bowel disorder."},
        "meta_description_variants": "only one string",
        "schema_json_ld": '{"@type": "Article"}',
        "url_slug": None,
    }, "en")
    assert isinstance(result["faqs"], list) and len(result["faqs"]) == 1
    assert result["meta_description_variants"] == ["only one string"]
    assert result["schema_json_ld"] == {"@type": "Article"}
    assert result["url_slug"] == ""
    assert result["language_check"]["ok"] is True


def test_validate_provider_result_drops_malformed_faqs():
    result = validate_provider_result({
        "optimized_article_markdown": " ".join(["gut health advice"] * 100),
        "faqs": [{"question": "Q?", "answer": "A."}, {"question": "", "answer": "orphan"}, "not a dict"],
    }, "en")
    assert result["faqs"] == [{"question": "Q?", "answer": "A."}]


# --- Pipeline behaviour on a contaminated response ----------------------

GOOD_JSON = (
    '{"optimized_article_markdown": "' + HINDI_BODY.replace('"', '') + '",'
    '"meta_description": "पाचन स्वास्थ्य की पूरी जानकारी और सुझाव।",'
    '"url_slug": "pachan-guide", "faqs": [], "cta_soft": "", "cta_direct": ""}'
)
CONTAMINATED_JSON = (
    '{"optimized_article_markdown": "' + HINDI_BODY.replace('"', '') + ' 消化系统健康 और पाचन।",'
    '"meta_description": "पाचन स्वास्थ्य की जानकारी।", "url_slug": "x", "faqs": []}'
)


@pytest.mark.asyncio
async def test_pipeline_retries_with_a_correction_after_a_script_failure(monkeypatch):
    """A response with Han characters must be thrown away and re-requested
    with an explicit correction, not scored and served."""
    monkeypatch.setattr(settings, "LLM_MAX_RETRIES", 1)
    prompts_seen = []
    calls = {"n": 0}

    async def fake_call(base_url, api_key, model, prompt, json_mode=False, timeout=None):
        prompts_seen.append(prompt)
        if not json_mode:
            return "draft text"
        calls["n"] += 1
        return CONTAMINATED_JSON if calls["n"] == 1 else GOOD_JSON

    monkeypatch.setattr(llm_providers, "_call_openai_compatible", fake_call)
    result = await llm_providers._run_pipeline(
        "https://api.test/v1", "k", "m", "groq", "पाचन", "pachan", "Delhi", "supporting", "hi"
    )

    assert result["provider_used"] == "groq"
    assert "消" not in result["optimized_article_markdown"]
    # The second drafting prompt carries the corrective instruction.
    assert any("अत्यावश्यक सुधार" in p for p in prompts_seen)


@pytest.mark.asyncio
async def test_pipeline_gives_up_after_retries_and_reports_the_reason(monkeypatch):
    monkeypatch.setattr(settings, "LLM_MAX_RETRIES", 1)
    monkeypatch.setattr(settings, "LLM_RETRY_BACKOFF_BASE", 1.0)

    async def always_contaminated(base_url, api_key, model, prompt, json_mode=False, timeout=None):
        return CONTAMINATED_JSON if json_mode else "draft"

    monkeypatch.setattr(llm_providers, "_call_openai_compatible", always_contaminated)
    with pytest.raises(RuntimeError, match="language check failed"):
        await llm_providers._run_pipeline(
            "https://api.test/v1", "k", "m", "groq", "पाचन", "pachan", "Delhi", "supporting", "hi"
        )


@pytest.mark.asyncio
async def test_llm_generate_falls_back_to_clean_template_content(monkeypatch):
    """When every provider keeps returning contaminated Hindi, the served
    article is the clean template — never the contaminated text."""
    monkeypatch.setattr(settings, "GROQ_API_KEY", "test-key")
    monkeypatch.setattr(settings, "LLM_MAX_RETRIES", 0)

    async def always_contaminated(base_url, api_key, model, prompt, json_mode=False, timeout=None):
        return CONTAMINATED_JSON if json_mode else "draft"

    monkeypatch.setattr(llm_providers, "_call_openai_compatible", always_contaminated)
    result = await llm_providers.llm_generate("पाचन", "pachan", "Delhi", "supporting", "hi")

    assert result["provider_used"] == "mock"
    assert "消" not in result["optimized_article_markdown"]
    assert result["language_check"]["ok"] is True
    assert "provider_note" in result


@pytest.mark.asyncio
async def test_served_article_is_repaired_if_context_leaks_foreign_script(monkeypatch):
    """The knowledge-base context is interpolated into the template article,
    so anything that slips in from the corpus is stripped before serving."""
    def dirty_mock(topic, keyword, geo, language="en"):
        return {
            "optimized_article_markdown": HINDI_BODY + " 消化系统健康 और पाचन।",
            "meta_description": "पाचन स्वास्थ्य।",
            "meta_description_variants": ["पाचन स्वास्थ्य की जानकारी।", "पाचन के सुझाव।"],
            "url_slug": "x", "faqs": [], "provider_used": "mock",
        }

    monkeypatch.setattr(llm_providers, "_mock_result", dirty_mock)
    result = await llm_providers.llm_generate("पाचन", "pachan", "Delhi", "supporting", "hi")

    assert "消" not in result["optimized_article_markdown"]
    assert result["language_repaired"] is True
    assert result["language_check"]["ok"] is True


def test_hindi_generation_end_to_end_stays_in_devanagari():
    from fastapi.testclient import TestClient

    from app.main import app

    data = TestClient(app).post("/generate", json={
        "topic": "पाचन स्वास्थ्य", "primary_keyword": "pachan tantra", "geo_target": "Delhi, India",
        "language": "hi",
    }).json()

    article = data["optimized_article_markdown"]
    assert data["language_check"]["ok"] is True
    assert find_foreign_script_chars(article) == {}
    assert "चिकित्सा अस्वीकरण" in article
    assert asyncio.iscoroutinefunction(llm_providers.llm_generate)
