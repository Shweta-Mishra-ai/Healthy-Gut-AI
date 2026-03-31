import os
import json
import re
import asyncio
from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles  # ✅ FIX 1: Added missing import

# ====== RAG Knowledge Base ======
KNOWLEDGE_BASE = {
    "gut":  "The gut microbiome is crucial for immune function, digestion, and mental health via the gut-brain axis. Fermented foods, fiber, and polyphenols support a healthy gut.",
    "ibs":  "IBS (Irritable Bowel Syndrome) is a functional GI disorder with symptoms of abdominal pain, bloating, and altered bowel habits. Low FODMAP diet is the first-line dietary intervention.",
    "ibd":  "IBD (Inflammatory Bowel Disease) includes Crohn's disease and Ulcerative Colitis — involving chronic GI inflammation and structural damage requiring medical treatment.",
}

def rag_context(topic: str) -> str:
    t = topic.lower()
    chunks = [v for k, v in KNOWLEDGE_BASE.items() if k in t]
    return " ".join(chunks) if chunks else KNOWLEDGE_BASE["gut"]


# ====== Metrics ======
def keyword_density(text: str, kw: str) -> dict:
    words = re.findall(r'\S+', text.lower())
    total = len(words) or 1
    count = sum(1 for w in words if kw.lower() in w)
    return {"totalWords": total, "keywordCount": count, "keywordDensityPercent": round(count/total*100, 2)}

def count_syllables(word):
    return len(re.findall(r'[aeiouy]+', word.lower())) or 1

def readability(text: str) -> dict:
    words = re.findall(r'\S+', text)
    sentences = len(re.findall(r'[.!?]', text)) or 1
    syllables = sum(count_syllables(w) for w in words)
    nw = len(words) or 1
    score = round(206.835 - 1.015*(nw/sentences) - 84.6*(syllables/nw), 2)
    return {"fleschReadingEase": score}


# ====== LLM Generate ======
async def llm_generate(topic, keyword, geo, article_type):
    api_key = os.getenv("OPENAI_API_KEY", "")
    ctx = rag_context(topic)

    if not api_key:
        # Mock response when no API key set
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
                {"question": f"Is {topic} common in {geo}?", "answer": f"Yes, {topic} affects millions in {geo}."}
            ],
            "schema_json_ld": {"@context": "https://schema.org", "@type": "Article", "headline": f"{topic} Guide"},
            "cta_soft": "Explore more free gut health resources on our blog.",
            "cta_direct": f"Try Healthy Gut AI FREE today — personalized plans for {geo}!"
        }

    # Real OpenAI call
    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=api_key)
        prompt1 = f"""You are a senior medical writer for Healthy Gut AI.
Write a fully referenced, medically accurate, SEO-optimized {article_type} article about: {topic}
Primary keyword: {keyword}
MEDICAL CONTEXT (RAG): {ctx}
Word count: {'2500-3000' if article_type=='pillar' else '1000-1500'} words.
Include: H1 with keyword, comparison table, diet section, medical disclaimer.
Output: Markdown only."""

        r1 = await client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role":"user","content":prompt1}]
        )
        draft = r1.choices[0].message.content

        prompt2 = f"""Optimize this article for SEO and geo-target {geo}.
Article: {draft}
Keyword: {keyword}
Return JSON with keys: optimized_article_markdown, meta_description, url_slug, faqs, schema_json_ld, cta_soft, cta_direct"""

        r2 = await client.chat.completions.create(
            model="gpt-4o",
            response_format={"type":"json_object"},
            messages=[{"role":"user","content":prompt2}]
        )
        return json.loads(r2.choices[0].message.content)
    except Exception as e:
        return {"error": str(e)}


# ====== FastAPI App ======
app = FastAPI(title="Healthy Gut AI")

# ✅ FIX 2: Mount static files so CSS/JS load correctly
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/debug")
def debug():
    return {"routes": [r.path for r in app.routes]}

# ✅ FIX 3: Serve static/index.html instead of inline HTML string
@app.get("/", response_class=HTMLResponse)
def root():
    return FileResponse("static/index.html")

@app.post("/generate")
async def generate(
    topic: str = Form(...),
    primary_keyword: str = Form(...),
    geo_target: str = Form(...),
    article_type: str = Form(...)
):
    try:
        result = await llm_generate(topic, primary_keyword, geo_target, article_type)
        if "error" in result:
            return JSONResponse(status_code=500, content=result)
        article_md = result.get("optimized_article_markdown", "")
        result["metrics"] = {
            "readability": readability(article_md),
            "keywordDensity": keyword_density(article_md, primary_keyword)
        }
        return JSONResponse(content=result)
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
