import asyncio
import json
import logging
import re

from app.config import settings
from app.rag.retriever import build_rag_context

logger = logging.getLogger("healthy_gut_ai.llm")


def rag_context(topic: str, keyword: str = "") -> str:
    context_text, _ = build_rag_context(topic, keyword)
    return context_text


def _extract_json(raw: str) -> dict:
    """LLMs (esp. free-tier models) don't always respect strict JSON mode.
    This pulls the first {...} block out and parses it, raising a clear
    error if nothing parseable is found, instead of crashing on json.loads."""
    raw = raw.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError as e:
            raise ValueError(f"Model returned unparseable JSON: {e}")
    raise ValueError("Model response contained no JSON object")


def _mock_result(topic: str, keyword: str, geo: str) -> dict:
    ctx = rag_context(topic, keyword)
    article = f"""# {topic.title()}: Your Complete Guide

**{keyword}** is one of the most searched topics in gut health today.

{ctx}

## What is {topic}?
{topic.title()} is a condition affecting the gastrointestinal tract, impacting millions worldwide in locations like **{geo}**.

## Common Symptoms
- Abdominal discomfort or pain
- Bloating and gas
- Changes in bowel habits

## Diet Recommendations
| Foods to Eat | Foods to Avoid |
|---|---|
| Fermented yogurt | Fried foods |
| High-fiber vegetables | Processed snacks |
| Ginger tea | Carbonated drinks |

## When to See a Doctor
If symptoms persist for more than 3 weeks, consult a gastroenterologist in **{geo}**.

---
*Medical Disclaimer: This article is educational and not a substitute for professional medical advice.*"""
    return {
        "optimized_article_markdown": article,
        "meta_description": f"Learn about {keyword} with our expert guide targeting {geo}. Find symptoms, diet tips, and when to seek help.",
        "url_slug": topic.lower().replace(" ", "-") + "-guide",
        "faqs": [
            {"question": f"What is {topic}?", "answer": ctx},
            {"question": f"Is {topic} common in {geo}?", "answer": f"Yes, {topic} affects many people in {geo}."},
        ],
        "schema_json_ld": {"@context": "https://schema.org", "@type": "Article", "headline": f"{topic} Guide"},
        "cta_soft": "Explore more free gut health resources on our blog.",
        "cta_direct": f"Try Healthy Gut AI FREE today — personalized plans for {geo}!",
        "provider_used": "mock",
    }


def _build_prompts(topic, keyword, geo, article_type, language):
    ctx = rag_context(topic, keyword)
    lang_instr = "Write the article in Hindi (Devanagari script)." if language == "hi" else "Write the article in English."

    if article_type == "pillar":
        word_count = "2500-3000"
        section_budget = (
            "- Overview: ~350-450 words\n"
            "- Causes/Triggers: ~400-500 words\n"
            "- Symptoms: ~400-500 words\n"
            "- Diet & Management: ~600-700 words (include the comparison table here)\n"
            "- When to See a Doctor: ~250-350 words\n"
            "- FAQs/closing: ~200-300 words"
        )
    else:
        word_count = "1000-1500"
        section_budget = (
            "- Overview: ~150-200 words\n"
            "- Causes/Triggers: ~200-250 words\n"
            "- Symptoms: ~200-250 words\n"
            "- Diet & Management: ~300-400 words (include the comparison table here)\n"
            "- When to See a Doctor: ~150-200 words"
        )

    prompt1 = f"""You are a senior medical content writer for Healthy Gut AI, writing for an educated general
audience, not clinicians. Write a medically accurate, SEO-optimized {article_type} article about: {topic}
Primary keyword: {keyword}

VERIFIED MEDICAL CONTEXT (ground your claims in this, do not contradict it):
{ctx}

STRICT RULES:
- Do NOT invent specific statistics, percentages, study names, or citations that are not in the
  VERIFIED MEDICAL CONTEXT above. If you don't have a specific number, describe the pattern qualitatively
  instead (e.g. "commonly affects" rather than inventing "affects 23% of people").
- Do NOT claim any food, supplement, or remedy "cures" or "eliminates" a condition. Use careful language:
  "may help manage", "is commonly recommended", "some people find relief with".
- Always include a clear medical disclaimer recommending professional consultation.
- Stay strictly on the stated topic — do not drift into unrelated conditions not implied by the topic
  or keyword, even if they appear in the VERIFIED MEDICAL CONTEXT.

REQUIRED LENGTH: {word_count} words TOTAL. This is a hard requirement, not a suggestion — write each
section to roughly its target length below, in full paragraphs (not brief summaries), so the total lands
in range:
{section_budget}

Structure with H2 sections matching the budget above. {lang_instr}
Include: H1 with keyword, a comparison table (foods to eat vs. avoid, or similar) in the Diet & Management
section, and the medical disclaimer at the end.
Output: Markdown only, no commentary before or after."""

    prompt2 = f"""Optimize the following article for SEO and geo-target "{geo}".
Keyword: {keyword}
Preserve all factual content AND the full length of the article body — do not shorten, summarize, or drop
sections while optimizing; only add SEO metadata around it.
Return ONLY a valid JSON object (no markdown fences, no commentary) with exactly these keys:
optimized_article_markdown (string), meta_description (string), url_slug (string),
faqs (array of {{question, answer}}), schema_json_ld (object), cta_soft (string), cta_direct (string).

Article:
{{DRAFT}}"""
    return prompt1, prompt2


_DISCLAIMER_MARKERS = ("disclaimer", "not a substitute for professional", "consult a", "consult your doctor")


def _ensure_disclaimer(article_markdown: str) -> str:
    """Programmatic safety net, not just an LLM instruction: verifiably ensures
    every article carries a medical disclaimer, regardless of provider or
    whether the model followed the prompt instruction."""
    lower = article_markdown.lower()
    if any(marker in lower for marker in _DISCLAIMER_MARKERS):
        return article_markdown
    return (
        article_markdown.rstrip()
        + "\n\n---\n*Medical Disclaimer: This article is for educational purposes only and is not a "
          "substitute for professional medical advice, diagnosis, or treatment. Always consult a "
          "qualified healthcare provider with questions about a medical condition.*"
    )


async def _call_openai_compatible(base_url, api_key, model, prompt, json_mode=False, timeout=None):
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=api_key, base_url=base_url, timeout=timeout or settings.LLM_TIMEOUT_SECONDS)
    kwargs = {"model": model, "messages": [{"role": "user", "content": prompt}]}
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    resp = await client.chat.completions.create(**kwargs)
    return resp.choices[0].message.content


async def _run_pipeline(base_url, api_key, model, provider_name, topic, keyword, geo, article_type, language):
    prompt1, prompt2_template = _build_prompts(topic, keyword, geo, article_type, language)

    last_err = None
    for attempt in range(settings.LLM_MAX_RETRIES + 1):
        try:
            draft = await _call_openai_compatible(base_url, api_key, model, prompt1)
            prompt2 = prompt2_template.replace("{DRAFT}", draft)
            try:
                raw_json = await _call_openai_compatible(base_url, api_key, model, prompt2, json_mode=True)
            except Exception:
                # some free-tier models reject response_format=json_object; retry without it
                raw_json = await _call_openai_compatible(base_url, api_key, model, prompt2, json_mode=False)
            result = _extract_json(raw_json)
            result["provider_used"] = provider_name
            return result
        except asyncio.TimeoutError as e:
            last_err = f"{provider_name} timed out: {e}"
        except Exception as e:
            last_err = f"{provider_name} error: {e}"
        if attempt < settings.LLM_MAX_RETRIES:
            backoff = settings.LLM_RETRY_BACKOFF_BASE ** attempt
            logger.warning("Retrying %s after failure (attempt %d): %s", provider_name, attempt + 1, last_err)
            await asyncio.sleep(backoff)
    raise RuntimeError(last_err or f"{provider_name} failed with no error captured")


async def llm_generate(topic: str, keyword: str, geo: str, article_type: str, language: str = "en") -> dict:
    """Tries providers in order: Groq (free) -> OpenRouter (free) -> OpenAI (paid, optional)
    -> Mock template. Each failure is logged and the next provider is tried,
    so a single provider outage never takes the whole app down."""
    providers = []
    if settings.GROQ_API_KEY:
        providers.append(("groq", settings.GROQ_BASE_URL, settings.GROQ_API_KEY, settings.GROQ_MODEL))
    if settings.OPENROUTER_API_KEY:
        providers.append(("openrouter", settings.OPENROUTER_BASE_URL, settings.OPENROUTER_API_KEY, settings.OPENROUTER_MODEL))
    if settings.OPENAI_API_KEY:
        providers.append(("openai", None, settings.OPENAI_API_KEY, settings.OPENAI_MODEL))

    result = None
    errors = []
    for name, base_url, api_key, model in providers:
        try:
            result = await asyncio.wait_for(
                _run_pipeline(base_url, api_key, model, name, topic, keyword, geo, article_type, language),
                timeout=settings.LLM_TIMEOUT_SECONDS * (settings.LLM_MAX_RETRIES + 1) + 5,
            )
            break
        except Exception as e:
            logger.error("Provider %s failed entirely: %s", name, e)
            errors.append(f"{name}: {e}")
            continue

    if result is None:
        if providers:
            logger.error("All LLM providers failed, falling back to mock. Errors: %s", errors)
        result = _mock_result(topic, keyword, geo)
        if errors:
            result["provider_note"] = "All configured providers failed; served mock content. " + " | ".join(errors)

    _, matched_chunks = build_rag_context(topic, keyword)
    result["rag_sources"] = [
        {"title": c["title"], "topic": c["topic"], "relevance_score": c["relevance_score"]}
        for c in matched_chunks
    ]
    if "optimized_article_markdown" in result:
        result["optimized_article_markdown"] = _ensure_disclaimer(result["optimized_article_markdown"])
    return result
