import asyncio
import time
from unittest.mock import patch

import pytest

from app import llm_providers
# Patch attributes on llm_providers.settings specifically, not app.config.settings.
# llm_providers.py did `from app.config import settings`, which binds a direct
# reference at import time — if any other test module reloads app.config (see
# test_config.py), app.config.settings becomes a *new* object, but
# llm_providers.settings still points at the original one. Patching the
# reference llm_generate() actually reads avoids that ordering hazard.
settings = llm_providers.settings


@pytest.mark.asyncio
async def test_overall_budget_caps_total_wait_even_with_high_retries():
    """Regression test: llm_generate used to have no ceiling on the combined
    time across all configured providers and their retries. With even one
    slow/erroring provider, LLM_TIMEOUT_SECONDS * (LLM_MAX_RETRIES + 1)
    could legitimately run past 100+ seconds — comfortably past the request
    timeout most reverse proxies enforce (Render's default is 100s), which
    kills the connection with no useful error surfaced to the browser at
    all. This must fall back to mock content once the overall budget is
    spent, regardless of individual per-call timeout/retry settings."""

    async def never_finishes(*args, **kwargs):
        await asyncio.sleep(1000)

    with patch.object(llm_providers, "_run_pipeline", never_finishes), \
         patch.object(settings, "GROQ_API_KEY", "fake-key-for-test"), \
         patch.object(settings, "LLM_OVERALL_BUDGET_SECONDS", 1.5), \
         patch.object(settings, "LLM_TIMEOUT_SECONDS", 100), \
         patch.object(settings, "LLM_MAX_RETRIES", 10):
        start = time.monotonic()
        result = await llm_providers.llm_generate("IBS diet", "IBS diet", "USA", "supporting")
        elapsed = time.monotonic() - start

    # Must respect the overall budget, not the (much larger) per-provider
    # timeout*retries figure.
    assert elapsed < 5
    assert result["provider_used"] == "mock"
    assert "provider_note" in result


@pytest.mark.asyncio
async def test_fast_provider_returns_normally_within_budget():
    """The budget ceiling must not interfere with a normal, fast response —
    only kick in when providers are actually slow/failing."""

    async def fast_result(*args, **kwargs):
        return {"optimized_article_markdown": "# Test\n\nSome content.", "provider_used": "groq"}

    with patch.object(llm_providers, "_run_pipeline", fast_result), \
         patch.object(settings, "GROQ_API_KEY", "fake-key-for-test"), \
         patch.object(settings, "LLM_OVERALL_BUDGET_SECONDS", 70):
        result = await llm_providers.llm_generate("IBS diet", "IBS diet", "USA", "supporting")

    assert result["provider_used"] == "groq"
    assert "provider_note" not in result


def test_default_reliability_settings_stay_under_proxy_timeout():
    """Sanity check on the shipped defaults themselves: the overall budget
    must be comfortably under the ~100s window most reverse proxies (Render
    included) allow for a single request."""
    assert settings.LLM_OVERALL_BUDGET_SECONDS < 90


# --- Language-aware post-processing ------------------------------------

def test_hindi_article_gets_a_hindi_disclaimer():
    """The disclaimer safety net used to append English text to every
    article, which both broke the Hindi reading experience and dragged the
    article's own script-purity score down."""
    from app.llm_providers import _ensure_disclaimer

    hindi = "# पाचन गाइड\n\nपेट की सेहत के बारे में जानकारी।"
    out = _ensure_disclaimer(hindi, "hi")
    assert "चिकित्सा अस्वीकरण" in out
    assert "Medical Disclaimer" not in out


def test_english_article_gets_an_english_disclaimer():
    from app.llm_providers import _ensure_disclaimer

    out = _ensure_disclaimer("# Guide\n\nSome gut health information.", "en")
    assert "Medical Disclaimer" in out


def test_existing_disclaimer_is_not_duplicated():
    from app.llm_providers import _ensure_disclaimer

    already = "# गाइड\n\nजानकारी।\n\n*चिकित्सा अस्वीकरण: केवल शैक्षिक।*"
    assert _ensure_disclaimer(already, "hi").count("अस्वीकरण") == 1


def test_meta_variant_fallback_stays_in_the_article_language():
    from app.llm_providers import _ensure_meta_variants

    result = _ensure_meta_variants({"meta_description": "पाचन स्वास्थ्य की पूरी जानकारी।"}, "hi")
    assert len(result["meta_description_variants"]) == 2
    assert all("Learn more" not in v for v in result["meta_description_variants"])


def test_meta_variant_fallback_in_english():
    from app.llm_providers import _ensure_meta_variants

    result = _ensure_meta_variants({"meta_description": "A complete guide to gut health."}, "en")
    assert result["meta_description_variants"][1].startswith("Learn more")


def test_openai_clients_are_reused_per_provider():
    """A fresh client per call meant a new TLS handshake on every LLM
    request and a connection pool that was never closed."""
    from app import llm_providers

    llm_providers._CLIENTS.clear()
    first = llm_providers._get_client("https://api.test/v1", "key-1")
    second = llm_providers._get_client("https://api.test/v1", "key-1")
    third = llm_providers._get_client("https://other.test/v1", "key-2")
    assert first is second
    assert third is not first
    llm_providers._CLIENTS.clear()
