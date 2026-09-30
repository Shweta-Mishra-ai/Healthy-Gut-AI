"""Template article served when no provider is configured, or when every
configured provider failed.

The English template is built from the knowledge-base chunks retrieved for
the topic (the same ones a provider would be grounded in, and the same ones
listed under "Sources Referenced"), each as its own section, plus the
knowledge base's red-flag guidance for the "when to see a doctor" section.
It used to paste the retrieved text as one paragraph under a few generic
bullets — about 350 words — so every template article scored far below the
length target and read as filler. No statistics or prevalence claims are
added that the knowledge base doesn't make.
"""
from app.rag.knowledge_base import KNOWLEDGE_BASE
from app.rag.retriever import build_rag_context

RED_FLAGS_CHUNK_ID = "when_to_see_doctor"


def _chunk(chunk_id: str) -> dict | None:
    return next((c for c in KNOWLEDGE_BASE if c["id"] == chunk_id), None)


def _first_sentence(text: str) -> str:
    head, sep, _ = text.partition(". ")
    return head + "." if sep else text


# A retrieved chunk becomes its own section only if it scores at least this
# fraction of the best match; weaker matches (gastritis for an acid-reflux
# query scores ~14% of GERD) would read as an off-topic detour.
SECTION_MIN_RELATIVE_SCORE = 0.25


def _section_chunks(chunks: list[dict]) -> list[dict]:
    top = max((c.get("relevance_score", 0.0) for c in chunks), default=0.0)
    if top <= 0:
        return chunks[:1]
    return [c for c in chunks if c.get("relevance_score", 0.0) >= SECTION_MIN_RELATIVE_SCORE * top]


def _english_article(topic: str, keyword: str, geo: str, chunks: list[dict]) -> str:
    title = topic.title()
    sections = [c for c in _section_chunks(chunks) if c["id"] != RED_FLAGS_CHUNK_ID]
    background = "\n\n".join(f"## {c['title']}\n{c['content']}" for c in sections)
    red_flags = _chunk(RED_FLAGS_CHUNK_ID)
    red_flags_text = f"\n\n{red_flags['content']}" if red_flags else ""
    first_fact = _first_sentence(chunks[0]["content"]) if chunks else ""

    return f"""# {title}: Your Complete Guide

**{keyword}** is one of the most searched topics in gut health today. This guide brings together what is well established about {topic}, the approaches that commonly help, and the signs that mean symptoms need a doctor rather than home management.

## What is {topic}?
{title} relates to the digestive (gastrointestinal) tract and is something many readers in **{geo}** look for guidance on. Symptoms, triggers and the most suitable approach differ from person to person, so the sections below describe common patterns rather than a single plan that suits everyone.

{background}

## Common Symptoms
- Abdominal discomfort or pain
- Bloating and gas
- Changes in bowel habits — looser, harder, more or less frequent
- Feeling full quickly, or uncomfortable after meals

Digestive symptoms often come and go. Keeping a short diary of meals, symptoms, sleep and stress for two to three weeks usually makes patterns easier to see, and gives a clinician far more to work with than a description from memory.

## Diet and Lifestyle Approaches
Diet is one of the most common starting points, but it works best when changes are made one at a time, so it is clear which change made a difference.

| Foods that often help | Foods that commonly trigger symptoms |
|---|---|
| Oats and other sources of soluble fibre | Fried and very fatty foods |
| Fermented yogurt or kefir, if dairy is tolerated | Highly processed snacks |
| Cooked vegetables | Carbonated drinks |
| Ginger tea | Large amounts of caffeine or alcohol |
| Water spread through the day | Very large or late-night meals |

Beyond individual foods, several habits are commonly recommended:
- Eat at regular times and avoid skipping meals.
- Increase fibre gradually, together with fluids, to limit extra gas and bloating.
- Stay physically active; regular movement supports healthy gut motility.
- Manage stress — the gut-brain axis means stress can make digestive symptoms worse.
- Protect sleep, since poor sleep and digestive symptoms often reinforce each other.

Restrictive diets should be time-limited and, if followed for more than a few weeks, planned with a registered dietitian to avoid nutritional gaps.

## When to See a Doctor
If symptoms persist for more than 3 weeks, keep returning, or affect daily life, consult a gastroenterologist in **{geo}**.{red_flags_text}

## Frequently Asked Questions

### What is {topic}?
{first_fact}

### Can diet changes help?
Many people find that adjusting meal patterns, fibre intake and specific trigger foods eases their symptoms, but the right changes differ between individuals and are best worked out with professional guidance.

### Should I stop my medication if my symptoms improve?
No — do not stop or change prescribed medication without talking to the doctor who prescribed it.

---
*Medical Disclaimer: This article is educational and not a substitute for professional medical advice.*"""


def _hindi_article(topic: str, keyword: str, geo: str) -> str:
    title = topic.title()
    return f"""# {title}: आपकी संपूर्ण गाइड

**{keyword}** आज गट हेल्थ (पाचन तंत्र) से जुड़े सबसे ज़्यादा खोजे जाने वाले विषयों में से एक है। इस गाइड में {topic} से जुड़ी भरोसेमंद जानकारी, आम तौर पर मदद करने वाले उपाय और वे संकेत दिए गए हैं जिनमें घरेलू देखभाल के बजाय डॉक्टर से मिलना ज़रूरी है।

## {topic} क्या है?
{title} पाचन तंत्र से जुड़ी एक स्थिति है, जिसके बारे में **{geo}** के कई पाठक जानकारी खोजते हैं। इसके लक्षण, कारण और सही उपाय हर व्यक्ति में अलग हो सकते हैं, इसलिए नीचे दी गई जानकारी आम पैटर्न बताती है, हर किसी के लिए एक जैसी योजना नहीं।

## आम कारण और ट्रिगर
- अनियमित खान-पान या भोजन छोड़ना
- बहुत तला-भुना, मसालेदार या प्रोसेस्ड भोजन
- भोजन में फाइबर और पानी की कमी
- तनाव और नींद की कमी
- कुछ दवाएँ — लेकिन डॉक्टर की सलाह के बिना कोई दवा बंद न करें

## आम लक्षण
- पेट में असुविधा या दर्द
- सूजन (ब्लोटिंग) और गैस
- मल त्याग की आदतों में बदलाव
- थोड़ा खाने पर ही पेट भरा हुआ लगना

लक्षण अक्सर आते-जाते रहते हैं। दो-तीन हफ्तों तक भोजन, लक्षण, नींद और तनाव की एक छोटी डायरी रखने से पैटर्न समझना आसान हो जाता है और डॉक्टर को भी सही जानकारी मिलती है।

## डाइट सुझाव
| खाने योग्य चीज़ें | परहेज़ करने योग्य चीज़ें |
|---|---|
| फर्मेंटेड दही | तली हुई चीज़ें |
| फाइबर युक्त सब्ज़ियाँ | प्रोसेस्ड स्नैक्स |
| अदरक की चाय | कार्बोनेटेड ड्रिंक्स |
| दलिया और ओट्स | बहुत ज़्यादा चाय-कॉफ़ी |
| दिन भर में पर्याप्त पानी | देर रात भारी भोजन |

## जीवनशैली सुझाव
- रोज़ तय समय पर भोजन करें और भोजन न छोड़ें।
- फाइबर धीरे-धीरे बढ़ाएँ और साथ में पानी भी बढ़ाएँ, ताकि गैस और सूजन न बढ़े।
- रोज़ाना हल्की शारीरिक गतिविधि करें, जैसे टहलना।
- तनाव कम करने के उपाय अपनाएँ, क्योंकि तनाव पाचन के लक्षणों को बढ़ा सकता है।
- पूरी नींद लें।

कोई भी बदलाव एक-एक करके करें, ताकि पता चल सके कि किस बदलाव से राहत मिली। कुछ हफ्तों से लंबी सख्त डाइट किसी पंजीकृत आहार विशेषज्ञ की सलाह से ही अपनाएँ।

## डॉक्टर से कब मिलें
अगर लक्षण 3 हफ्तों से ज़्यादा बने रहें या बार-बार लौटें, तो **{geo}** में किसी गैस्ट्रोएंटेरोलॉजिस्ट से सलाह लें। इन संकेतों में तुरंत डॉक्टर से मिलें:
- बिना कारण वज़न कम होना
- मल में खून या काला मल
- लगातार उल्टी
- निगलने में कठिनाई
- ऐसे लक्षण जो रात में नींद से जगा दें

## अक्सर पूछे जाने वाले प्रश्न

### क्या डाइट में बदलाव से मदद मिल सकती है?
कई लोगों को भोजन के समय, फाइबर और ट्रिगर करने वाली चीज़ों में बदलाव से राहत मिलती है, लेकिन सही बदलाव हर व्यक्ति के लिए अलग होते हैं और विशेषज्ञ की सलाह से तय करना बेहतर है।

### लक्षण ठीक होने पर क्या दवा बंद कर सकते हैं?
नहीं — दवा लिखने वाले डॉक्टर से बात किए बिना कोई दवा बंद न करें और न ही उसकी मात्रा बदलें।

---
*चिकित्सा अस्वीकरण: यह लेख केवल शैक्षिक उद्देश्यों के लिए है और पेशेवर चिकित्सा सलाह का विकल्प नहीं है।*"""


def mock_result(topic: str, keyword: str, geo: str, language: str = "en") -> dict:
    _, chunks = build_rag_context(topic, keyword)

    if language == "hi":
        article = _hindi_article(topic, keyword, geo)
        meta_variants = [
            f"{keyword} के बारे में हमारी विशेषज्ञ गाइड पढ़ें, {geo} के लिए तैयार। लक्षण, डाइट टिप्स जानें।",
            f"क्या आप {keyword} से जूझ रहे हैं? {geo} के लिए कारण, लक्षण और प्रबंधन के तरीके जानें।",
            f"{topic.title()} पूरी जानकारी: {geo} के पाठकों के लिए लक्षण, डाइट और देखभाल की जानकारी।",
        ]
        faqs = [
            {"question": f"{topic} क्या है?", "answer": f"{topic.title()} पाचन तंत्र से जुड़ी एक स्थिति है, जिसमें जीवनशैली और आहार में बदलाव से कई लोगों को राहत मिल सकती है।"},
            {"question": "डॉक्टर से कब मिलना चाहिए?", "answer": f"अगर लक्षण 3 हफ्तों से ज़्यादा बने रहें, या मल में खून, वज़न कम होना या लगातार उल्टी हो, तो {geo} में डॉक्टर से मिलें।"},
        ]
        cta_soft = "गट हेल्थ से जुड़े और मुफ़्त संसाधन हमारे ब्लॉग पर देखें।"
        cta_direct = f"आज ही Healthy Gut मुफ़्त में आज़माएँ — {geo} के लिए पर्सनलाइज़्ड प्लान!"
    else:
        article = _english_article(topic, keyword, geo, chunks)
        meta_variants = [
            f"Learn about {keyword} with our expert guide targeting {geo}. Find symptoms, diet tips, and when to seek help.",
            f"Struggling with {keyword}? Discover causes, symptoms, and management options tailored for {geo}.",
            f"{topic.title()} explained: what {geo} readers need to know about symptoms, diet, and care.",
        ]
        faqs = [
            {"question": f"What is {topic}?", "answer": _first_sentence(chunks[0]["content"]) if chunks else ""},
            {"question": "When should I see a doctor?", "answer": f"If symptoms last more than 3 weeks, or you notice blood in stool, unexplained weight loss or persistent vomiting, see a doctor in {geo}."},
        ]
        cta_soft = "Explore more free gut health resources on our blog."
        cta_direct = f"Try Healthy Gut FREE today — personalized plans for {geo}!"

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
