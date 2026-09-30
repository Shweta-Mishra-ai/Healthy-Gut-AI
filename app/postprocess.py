"""Everything done to a provider's reply before it can be trusted: JSON
extraction, shape coercion, validation, and the programmatic safety nets
(meta variants, sources section, medical disclaimer)."""
import json
import re

from app.language import check_language
from app.quality import DISCLAIMER_MARKERS

# Below this, whatever came back is not an article — it's a refusal, an
# apology, a truncated stream, or an empty string. Accepting it silently is
# how a "successful" generation ends up rendering a blank page with a
# quality score of 0 and no error anywhere.
MIN_ARTICLE_WORDS = 120


def extract_json(raw: str) -> dict:
    """LLMs (esp. free-tier models) don't always respect strict JSON mode.
    This pulls the first {...} block out and parses it, raising a clear
    error if nothing parseable is found, instead of crashing on json.loads."""
    raw = raw.strip()
    # Strip markdown code block wrappers if present (e.g. ```json ... ```)
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE)
        raw = re.sub(r"\s*```$", "", raw).strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError as e:
            raise ValueError(f"Model returned unparseable JSON: {e}") from e
    raise ValueError("Model response contained no JSON object")


class ProviderOutputError(RuntimeError):
    """A provider replied, and the reply parsed, but it isn't a usable article.

    Distinct from a transport error on purpose: this is the failure mode that
    used to slip through as a success (empty body, a refusal message, or an
    article written in the wrong script), so it needs to be raised and
    handled exactly like a provider outage — retry, then fall through to the
    next provider.
    """


def coerce_shape(result: dict) -> dict:
    """Normalizes the loosely-typed JSON a model returns into the shapes the
    rest of the app indexes into. Free-tier models routinely return a string
    where a list is specified, or a JSON-encoded string where an object is —
    which then blows up much later, far from the cause."""
    if isinstance(result.get("faqs"), dict):
        result["faqs"] = [result["faqs"]]
    if not isinstance(result.get("faqs"), list):
        result["faqs"] = []
    result["faqs"] = [
        f for f in result["faqs"]
        if isinstance(f, dict) and str(f.get("question", "")).strip() and str(f.get("answer", "")).strip()
    ]

    variants = result.get("meta_description_variants")
    if isinstance(variants, str):
        result["meta_description_variants"] = [variants]
    elif not isinstance(variants, list):
        result["meta_description_variants"] = []

    schema = result.get("schema_json_ld")
    if isinstance(schema, str):
        try:
            result["schema_json_ld"] = json.loads(schema)
        except json.JSONDecodeError:
            result["schema_json_ld"] = {}
    elif not isinstance(schema, dict):
        result["schema_json_ld"] = {}

    for key in ("meta_description", "url_slug", "cta_soft", "cta_direct"):
        value = result.get(key)
        if value is None:
            result[key] = ""
        elif not isinstance(value, str):
            result[key] = str(value)

    return result


def validate_provider_result(result: dict, language: str) -> dict:
    """Gate every provider response before it can be cached, scored, stored
    in the review queue or returned. Raises ProviderOutputError on anything
    that isn't a real article in the requested language."""
    if not isinstance(result, dict):
        raise ProviderOutputError(f"expected a JSON object, got {type(result).__name__}")

    article = result.get("optimized_article_markdown")
    if not isinstance(article, str) or not article.strip():
        raise ProviderOutputError("response contained no article body")

    word_count = len(article.split())
    if word_count < MIN_ARTICLE_WORDS:
        raise ProviderOutputError(
            f"article body is only {word_count} words — below the {MIN_ARTICLE_WORDS}-word "
            f"floor for a real article (likely a refusal or a truncated response)"
        )

    verdict = check_language(article, language)
    if not verdict["ok"]:
        raise ProviderOutputError(f"language check failed — {verdict['reason']}")

    result = coerce_shape(result)
    result["language_check"] = verdict
    return result


def ensure_meta_variants(result: dict, language: str = "en") -> dict:
    """Programmatic safety net: free-tier models don't always follow complex
    JSON schema instructions reliably. Guarantees meta_description_variants
    is always a list of 2-3 non-empty strings, falling back to the primary
    meta_description (and light variations of it) if the provider didn't
    return usable variants."""
    primary = (result.get("meta_description") or "").strip()
    variants = result.get("meta_description_variants")

    if isinstance(variants, list):
        cleaned = [v.strip() for v in variants if isinstance(v, str) and v.strip()]
    else:
        cleaned = []

    if len(cleaned) >= 2:
        result["meta_description_variants"] = cleaned[:3]
        return result

    # Fallback: not enough usable variants from the model — build minimal ones
    # from what we have, in the article's own language. The old fallback
    # hardcoded an English "Learn more:" prefix, which produced a Hindi
    # article whose second meta variant opened in English.
    fallback = [primary] if primary else []
    if primary:
        if language == "hi":
            if not primary.startswith("जानें"):
                fallback.append(f"जानें: {primary}")
        elif not primary.lower().startswith("learn"):
            fallback.append(f"Learn more: {primary}")
    result["meta_description_variants"] = fallback[:3] if fallback else [primary or ""]
    return result


def append_references(article_markdown: str, matched_chunks: list, language: str = "en") -> str:
    """Appends a real 'Sources Referenced' section listing the actual
    knowledge-base chunks used to ground this article — verifiable, not
    fabricated citations. Skips if already present (idempotent)."""
    lower = article_markdown.lower()
    if "## sources referenced" in lower or "## references" in lower or "## संदर्भित स्रोत" in article_markdown:
        return article_markdown
    if not matched_chunks:
        return article_markdown
    heading = "## संदर्भित स्रोत" if language == "hi" else "## Sources Referenced"
    source_label = "आंतरिक मेडिकल नॉलेज बेस" if language == "hi" else "internal medical knowledge base"
    lines = [f"\n\n{heading}", ""]
    for c in matched_chunks:
        lines.append(f"- {c['title']} — {source_label} (topic: {c['topic']})")
    return article_markdown.rstrip() + "\n" + "\n".join(lines)


DISCLAIMER_TEXT = {
    "en": (
        "*Medical Disclaimer: This article is for educational purposes only and is not a "
        "substitute for professional medical advice, diagnosis, or treatment. Always consult a "
        "qualified healthcare provider with questions about a medical condition.*"
    ),
    "hi": (
        "*चिकित्सा अस्वीकरण: यह लेख केवल शैक्षिक उद्देश्यों के लिए है और पेशेवर चिकित्सा सलाह, निदान या "
        "उपचार का विकल्प नहीं है। किसी भी स्वास्थ्य समस्या के बारे में हमेशा योग्य चिकित्सक से परामर्श लें।*"
    ),
}


def ensure_disclaimer(article_markdown: str, language: str = "en") -> str:
    """Programmatic safety net, not just an LLM instruction: verifiably ensures
    every article carries a medical disclaimer, regardless of provider or
    whether the model followed the prompt instruction.

    The disclaimer is written in the article's own language — appending the
    English text to a Hindi article (the previous behaviour) both broke the
    reading experience and dragged the article's script-purity score down.
    """
    lower = article_markdown.lower()
    if any(marker in lower for marker in DISCLAIMER_MARKERS):
        return article_markdown
    disclaimer = DISCLAIMER_TEXT.get(language, DISCLAIMER_TEXT["en"])
    return article_markdown.rstrip() + "\n\n---\n" + disclaimer
