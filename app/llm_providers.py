import asyncio
import json
import logging
import re

from app.config import settings
from app.quality import DISCLAIMER_MARKERS
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
            raise ValueError(f"Model returned unparseable JSON: {e}")
    raise ValueError("Model response contained no JSON object")


def _mock_result(topic: str, keyword: str, geo: str, language: str = "en") -> dict:
    ctx = rag_context(topic, keyword)

    if language == "hi":
        article = f"""# {topic.title()}: आपकी संपूर्ण गाइड

**{keyword}** आज गट हेल्थ (पाचन तंत्र) से जुड़े सबसे ज़्यादा खोजे जाने वाले विषयों में से एक है।

## {topic} क्या है?
{topic.title()} पाचन तंत्र से जुड़ी एक स्थिति है, जो **{geo}** सहित दुनिया भर में लाखों लोगों को प्रभावित करती है। यह सामान्य पाचन विकारों में से एक है जिसके लिए सही जानकारी और समय पर देखभाल ज़रूरी है।

## आम लक्षण
- पेट में असुविधा या दर्द
- सूजन (ब्लोटिंग) और गैस
- मल त्याग की आदतों में बदलाव

## डाइट सुझाव
| खाने योग्य चीज़ें | परहेज़ करने योग्य चीज़ें |
|---|---|
| फर्मेंटेड दही | तली हुई चीज़ें |
| फाइबर युक्त सब्ज़ियाँ | प्रोसेस्ड स्नैक्स |
| अदरक की चाय | कार्बोनेटेड ड्रिंक्स |

## डॉक्टर से कब मिलें
अगर लक्षण 3 हफ्तों से ज़्यादा बने रहें, तो **{geo}** में किसी गैस्ट्रोएंटेरोलॉजिस्ट से सलाह लें।

---
*चिकित्सा अस्वीकरण: यह लेख केवल शैक्षिक उद्देश्यों के लिए है और पेशेवर चिकित्सा सलाह का विकल्प नहीं है।*"""
        meta_variants = [
            f"{keyword} के बारे में हमारी विशेषज्ञ गाइड पढ़ें, {geo} के लिए तैयार। लक्षण, डाइट टिप्स जानें।",
            f"क्या आप {keyword} से जूझ रहे हैं? {geo} के लिए कारण, लक्षण और प्रबंधन के तरीके जानें।",
            f"{topic.title()} पूरी जानकारी: {geo} के पाठकों के लिए लक्षण, डाइट और देखभाल की जानकारी।",
        ]
        faqs = [
            {"question": f"{topic} क्या है?", "answer": f"{topic.title()} एक सामान्य पाचन-तंत्र संबंधी स्थिति है जिसमें जीवनशैली और आहार में बदलाव से राहत मिल सकती है।"},
            {"question": f"क्या {topic} {geo} में आम है?", "answer": f"हाँ, {topic} {geo} में कई लोगों को प्रभावित करता है।"},
        ]
        cta_soft = "गट हेल्थ से जुड़े और मुफ़्त संसाधन हमारे ब्लॉग पर देखें।"
        cta_direct = f"आज ही Healthy Gut AI मुफ़्त में आज़माएँ — {geo} के लिए पर्सनलाइज़्ड प्लान!"
    else:
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
        meta_variants = [
            f"Learn about {keyword} with our expert guide targeting {geo}. Find symptoms, diet tips, and when to seek help.",
            f"Struggling with {keyword}? Discover causes, symptoms, and management options tailored for {geo}.",
            f"{topic.title()} explained: what {geo} readers need to know about symptoms, diet, and care.",
        ]
        faqs = [
            {"question": f"What is {topic}?", "answer": ctx},
            {"question": f"Is {topic} common in {geo}?", "answer": f"Yes, {topic} affects many people in {geo}."},
        ]
        cta_soft = "Explore more free gut health resources on our blog."
        cta_direct = f"Try Healthy Gut AI FREE today — personalized plans for {geo}!"

    return {
        "optimized_article_markdown": article,
        "meta_description": meta_variants[0],
        "meta_description_variants": meta_variants,
        "url_slug": topic.lower().replace(" ", "-") + "-guide",
        "faqs": faqs,
        "schema_json_ld": {"@context": "https://schema.org", "@type": "Article", "headline": f"{topic} Guide"},
        "cta_soft": cta_soft,
        "cta_direct": cta_direct,
        "provider_used": "mock",
    }


TONE_INSTRUCTIONS = {
    "educational": "Write in a clear, educational tone for a general audience — approachable but informative, like a trusted health website.",
    "authoritative": "Write in an authoritative, confident clinical tone — precise terminology, minimal hedging, suited to an expert-reviewed health resource.",
    "patient_friendly": "Write in a warm, reassuring, patient-friendly tone — simple words, short sentences, empathetic framing, suited for someone worried about symptoms.",
    "academic": "Write in a formal, academic tone — precise terminology, measured claims, suited for a research-adjacent or clinician-facing audience.",
    "seo_blog": "Write in an engaging, conversational SEO-blog tone — short paragraphs, active voice, hooks the reader, still medically accurate.",
}


def _build_prompts(topic, keyword, geo, article_type, language, tone="educational"):
    ctx = rag_context(topic, keyword)
    if language == "hi":
        tone_hi = {
            "educational": "स्पष्ट, शिक्षाप्रद और ज्ञानवर्धक शैली में लिखें।",
            "authoritative": "चिकित्सकीय रूप से प्रामाणिक, गंभीर और सटीक शैली में लिखें।",
            "patient_friendly": "सहानुभूतिपूर्ण, सरल, सुलभ और आत्मीय शैली में लिखें।",
            "academic": "औपचारिक, शोध-आधारित और गंभीर शैक्षणिक शैली में लिखें।",
            "seo_blog": "आकर्षक, रोचक और एसईओ-अनुकूलित ब्लॉग शैली में लिखें।",
        }.get(tone, "स्पष्ट और शिक्षाप्रद शैली में लिखें।")

        word_count = "2500-3000" if article_type == "pillar" else "1000-1500"
        section_budget = (
            "- ओवरव्यू (Overview): ~350-450 शब्द\n"
            "- कारण और ट्रिगर (Causes & Triggers): ~400-500 शब्द\n"
            "- लक्षण (Symptoms): ~400-500 शब्द\n"
            "- आहार और प्रबंधन (Diet & Management): ~600-700 शब्द (तुलना सारणी सहित)\n"
            "- डॉक्टर से कब परामर्श करें (When to Consult a Doctor): ~250-350 शब्द\n"
            "- अक्सर पूछे जाने वाले प्रश्न (FAQs): ~200-300 शब्द"
            if article_type == "pillar" else
            "- ओवरव्यू (Overview): ~150-200 शब्द\n"
            "- कारण और ट्रिगर (Causes & Triggers): ~200-250 शब्द\n"
            "- लक्षण (Symptoms): ~200-250 शब्द\n"
            "- आहार और प्रबंधन (Diet & Management): ~300-400 शब्द (तुलना सारणी सहित)\n"
            "- डॉक्टर से कब परामर्श करें (When to Consult a Doctor): ~150-200 शब्द"
        )

        prompt1 = f"""आप Healthy Gut AI के एक वरिष्ठ चिकित्सा सामग्री लेखक (Medical Content Writer) हैं।
आपको स्वास्थ्य और पाचन तंत्र (Gut Health) विषय पर एक संपूर्ण, सटीक और SEO-अनुकूलित {article_type} लेख लिखना है।

विषय (Topic): {topic}
मुख्य कीवर्ड (Primary Keyword): {keyword}
लक्षित स्थान (Geo-Target): {geo}

सत्यापित चिकित्सा संदर्भ (VERIFIED MEDICAL CONTEXT):
{ctx}

कड़े नियम (STRICT RULES):
- सम्पूर्ण लेख केवल और केवल शुद्ध हिंदी (देवनागरी लिपि) में लिखें। सभी पैराग्राफ, मुख्य शीर्षक (H2, H3), टेबल, अस्वीकरण और एफएक्यू देवनागरी हिंदी में होने चाहिए। केवल मुख्य विषय/टाइटल नाम अंग्रेजी में रह सकता है।
- सत्यापित चिकित्सा संदर्भ से बाहर किसी काल्पनिक आंकड़े या प्रतिशत का उल्लेख न करें।
- किसी भी आहार या उपचार के लिए "पूर्ण इलाज" का दावा न करें। हमेशा "प्रबंधन में मददगार", "राहत दे सकता है" जैसी संतुलित भाषा का उपयोग करें।
- लेख के अंत में स्पष्ट चिकित्सा अस्वीकरण (Medical Disclaimer) शामिल करें।
- टोन और शैली: {tone_hi}

आवश्यक लंबाई: कुल {word_count} शब्द।
संरचना और अनुभाग (Section Budget):
{section_budget}

आउटपुट: केवल मार्कडाउन स्वरूप (Markdown format) में हिंदी लेख दें।"""

        prompt2 = f"""नीचे दिए गए हिंदी लेख को SEO और स्थान "{geo}" के लिए अनुकूलित (Optimize) करें।
कीवर्ड: {keyword}

नियम: लेख के सभी मूल तथ्यों और संपूर्ण लंबाई को सुरक्षित रखें। किसी भी अनुभाग को छोटा या हटाएँ नहीं।

meta_description_variants के लिए ठीक 3 अलग-अलग हिंदी मेटा विवरण (120-160 वर्ण) लिखें:
1. लाभ-केंद्रित (Benefit-led)
2. प्रश्न-केंद्रित (Question-led)
3. Direct/keyword-led

केवल निम्नलिखित मान्य JSON ऑब्जेक्ट लौटाएँ (कोई मार्कडाउन कोड ब्लॉक नहीं):
{{
  "optimized_article_markdown": "हिंदी लेख का संपूर्ण मार्कडाउन",
  "meta_description": "मेटा विवरण 1",
  "meta_description_variants": ["विवरण 1", "विवरण 2", "विवरण 3"],
  "url_slug": "url-slug",
  "faqs": [{{"question": "प्रश्न हिंदी में?", "answer": "उत्तर हिंदी में।"}}],
  "schema_json_ld": {{"@context": "https://schema.org", "@type": "Article", "headline": "{topic}"}},
  "cta_soft": "सॉफ्ट आह्वान हिंदी में",
  "cta_direct": "प्रत्यक्ष आह्वान हिंदी में"
}}

लेख:
{{DRAFT}}"""
        return prompt1, prompt2

    lang_instr = "Write the article in English."
    tone_instr = TONE_INSTRUCTIONS.get(tone, TONE_INSTRUCTIONS["educational"])

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
- TONE: {tone_instr}

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

For meta_description_variants, write exactly 3 alternative meta descriptions, each 120-160 characters,
each including the keyword, but with genuinely different angles:
1. Benefit-led (what the reader gains)
2. Question-led (opens with the reader's likely question)
3. Direct/keyword-led (states the topic plainly, keyword near the start)

Return ONLY a valid JSON object (no markdown fences, no commentary) with exactly these keys:
optimized_article_markdown (string), meta_description (string, same as variant 1),
meta_description_variants (array of exactly 3 strings as described above), url_slug (string),
faqs (array of {{question, answer}}), schema_json_ld (object), cta_soft (string), cta_direct (string).

Article:
{{DRAFT}}"""
    return prompt1, prompt2





def _ensure_meta_variants(result: dict) -> dict:
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

    # Fallback: not enough usable variants from the model — build minimal ones from what we have.
    fallback = [primary] if primary else []
    if primary and not primary.lower().startswith("learn"):
        fallback.append(f"Learn more: {primary}")
    result["meta_description_variants"] = fallback[:3] if fallback else [primary or ""]
    return result


def _append_references(article_markdown: str, matched_chunks: list, language: str = "en") -> str:
    """Appends a real 'Sources Referenced' section listing the actual
    knowledge-base chunks used to ground this article — verifiable, not
    fabricated citations. Skips if already present (idempotent)."""
    if "## sources referenced" in article_markdown.lower() or "## references" in article_markdown.lower() or "## संदर्भित स्रोत" in article_markdown:
        return article_markdown
    if not matched_chunks:
        return article_markdown
    heading = "## संदर्भित स्रोत" if language == "hi" else "## Sources Referenced"
    source_label = "आंतरिक मेडिकल नॉलेज बेस" if language == "hi" else "internal medical knowledge base"
    lines = [f"\n\n{heading}", ""]
    for c in matched_chunks:
        lines.append(f"- {c['title']} — {source_label} (topic: {c['topic']})")
    return article_markdown.rstrip() + "\n" + "\n".join(lines)


def _ensure_disclaimer(article_markdown: str) -> str:
    """Programmatic safety net, not just an LLM instruction: verifiably ensures
    every article carries a medical disclaimer, regardless of provider or
    whether the model followed the prompt instruction."""
    lower = article_markdown.lower()
    if any(marker in lower for marker in DISCLAIMER_MARKERS):
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


async def _run_pipeline(base_url, api_key, model, provider_name, topic, keyword, geo, article_type, language, tone="educational"):
    prompt1, prompt2_template = _build_prompts(topic, keyword, geo, article_type, language, tone)

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


async def llm_generate(topic: str, keyword: str, geo: str, article_type: str, language: str = "en", tone: str = "educational") -> dict:
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
                _run_pipeline(base_url, api_key, model, name, topic, keyword, geo, article_type, language, tone),
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
        result = _mock_result(topic, keyword, geo, language)
        if errors:
            result["provider_note"] = "All configured providers failed; served mock content. " + " | ".join(errors)

    _, matched_chunks = build_rag_context(topic, keyword)
    result["rag_sources"] = [
        {"title": c["title"], "topic": c["topic"], "relevance_score": c["relevance_score"]}
        for c in matched_chunks
    ]
    if "optimized_article_markdown" in result:
        result["optimized_article_markdown"] = _ensure_disclaimer(result["optimized_article_markdown"])
        result["optimized_article_markdown"] = _append_references(result["optimized_article_markdown"], matched_chunks, language)
    result = _ensure_meta_variants(result)
    return result
