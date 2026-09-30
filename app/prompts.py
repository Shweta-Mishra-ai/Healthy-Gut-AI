"""Prompt text for the two-step generation pipeline (draft, then SEO/JSON
pass), in English and Hindi, plus the correction appended on a retry."""
from app.rag.retriever import build_rag_context


def rag_context(topic: str, keyword: str = "") -> str:
    context_text, _ = build_rag_context(topic, keyword)
    return context_text



TONE_INSTRUCTIONS = {
    "educational": "Write in a clear, educational tone for a general audience — approachable but informative, like a trusted health website.",
    "authoritative": "Write in an authoritative, confident clinical tone — precise terminology, minimal hedging, suited to an expert-reviewed health resource.",
    "patient_friendly": "Write in a warm, reassuring, patient-friendly tone — simple words, short sentences, empathetic framing, suited for someone worried about symptoms.",
    "academic": "Write in a formal, academic tone — precise terminology, measured claims, suited for a research-adjacent or clinician-facing audience.",
    "seo_blog": "Write in an engaging, conversational SEO-blog tone — short paragraphs, active voice, hooks the reader, still medically accurate.",
}


def _feedback_block(feedback: str, language: str) -> str:
    """A medical reviewer rejected the previous draft of this same article.
    Their note is the most specific instruction available — without it a
    regeneration tends to repeat exactly what was rejected."""
    feedback = (feedback or "").strip()
    if not feedback:
        return ""
    if language == "hi":
        return (
            "\n\nसमीक्षक की प्रतिक्रिया (अनिवार्य): इसी विषय का पिछला लेख एक चिकित्सा समीक्षक ने इस कारण "
            f"अस्वीकार किया था — \"{feedback}\"। नया लेख लिखते समय इस आपत्ति को पूरी तरह दूर करें।"
        )
    return (
        "\n\nREVIEWER FEEDBACK (must be addressed): a medical reviewer rejected the previous draft of this "
        f"article for this reason: \"{feedback}\". Write the new article so this objection no longer applies."
    )


def build_prompts(topic, keyword, geo, article_type, language, tone="educational", feedback=""):
    ctx = rag_context(topic, keyword)
    feedback_block = _feedback_block(feedback, language)
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

        prompt1 = f"""आप Healthy Gut के एक वरिष्ठ चिकित्सा सामग्री लेखक (Medical Content Writer) हैं।
आपको स्वास्थ्य और पाचन तंत्र (Gut Health) विषय पर एक संपूर्ण, सटीक और SEO-अनुकूलित {article_type} लेख लिखना है।

विषय (Topic): {topic}
मुख्य कीवर्ड (Primary Keyword): {keyword}
लक्षित स्थान (Geo-Target): {geo}

सत्यापित चिकित्सा संदर्भ (VERIFIED MEDICAL CONTEXT):
{ctx}

कड़े नियम (STRICT RULES):
- सम्पूर्ण लेख केवल और केवल शुद्ध हिंदी (देवनागरी लिपि) में लिखें। सभी पैराग्राफ, मुख्य शीर्षक (H2, H3), टेबल, अस्वीकरण और एफएक्यू देवनागरी हिंदी में होने चाहिए। केवल मुख्य विषय/टाइटल नाम अंग्रेजी में रह सकता है।
- लिपि नियम (अत्यंत महत्वपूर्ण): केवल देवनागरी और (तकनीकी शब्दों के लिए) रोमन लिपि का प्रयोग करें। चीनी, जापानी, कोरियाई, सिरिलिक, अरबी या किसी अन्य लिपि का एक भी अक्षर लेख में नहीं आना चाहिए। ऐसा उत्तर पूरी तरह अस्वीकार कर दिया जाएगा।
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
        return prompt1 + feedback_block, prompt2

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

    prompt1 = f"""You are a senior medical content writer for Healthy Gut, writing for an educated general
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
    return prompt1 + feedback_block, prompt2


# Appended to the drafting prompt on a retry that follows a script failure.
# Telling the model *why* its last answer was thrown away is far more
# effective than repeating the original instruction verbatim.
LANGUAGE_CORRECTION = {
    "hi": (
        "\n\nअत्यावश्यक सुधार: आपका पिछला उत्तर अस्वीकार कर दिया गया क्योंकि उसमें देवनागरी के "
        "अलावा किसी दूसरी लिपि (जैसे चीनी, जापानी, कोरियाई या सिरिलिक) के अक्षर आ गए थे। "
        "इस बार पूरा लेख केवल देवनागरी लिपि में लिखें — एक भी अक्षर किसी अन्य लिपि का नहीं होना चाहिए। "
        "तकनीकी शब्दों के लिए अंग्रेज़ी (रोमन) लिपि का सीमित प्रयोग स्वीकार्य है।"
    ),
    "en": (
        "\n\nIMPORTANT CORRECTION: your previous response was rejected because it contained "
        "characters from a non-Latin writing system. Write the entire article in English only."
    ),
}
