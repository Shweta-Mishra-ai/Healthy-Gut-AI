"""Contract test against a real provider — skipped unless explicitly enabled.

Every other test mocks the provider, so nothing checks that the configured
model (GROQ_MODEL) still exists, accepts JSON mode and returns a usable
article. Enable with:
    LIVE_PROVIDER_TESTS=1 LIVE_GROQ_API_KEY=... python -m pytest tests/test_live_provider.py
(LIVE_GROQ_API_KEY, not GROQ_API_KEY: the suite's conftest clears provider keys.)
"""
import os

import pytest

from app import llm_providers
from app.config import settings

LIVE_KEY = os.getenv("LIVE_GROQ_API_KEY", "")

pytestmark = pytest.mark.skipif(
    os.getenv("LIVE_PROVIDER_TESTS") != "1" or not LIVE_KEY,
    reason="live provider test disabled (set LIVE_PROVIDER_TESTS=1 and LIVE_GROQ_API_KEY)",
)


@pytest.mark.asyncio
@pytest.mark.parametrize("language,topic,keyword,geo", [
    ("en", "IBS diet plan", "IBS diet", "India"),
    ("hi", "पेट में गैस", "गैस", "भारत"),
])
async def test_configured_groq_model_returns_a_valid_article(monkeypatch, language, topic, keyword, geo):
    monkeypatch.setattr(settings, "GROQ_API_KEY", LIVE_KEY)
    monkeypatch.setattr(settings, "OPENROUTER_API_KEY", "")
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "")
    result = await llm_providers.llm_generate(topic, keyword, geo, "supporting", language)
    assert result["provider_used"] == "groq", result.get("provider_note")
    assert len(result["optimized_article_markdown"].split()) >= 300
    assert result["language_check"]["ok"], result["language_check"]
    assert result["usage"]["calls"] >= 2 and result["usage"]["completion_tokens"] > 0
