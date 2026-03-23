import os
import json
import re
import asyncio
from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse, JSONResponse

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


# ====== Metrics (Python port of JS scripts) ======
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


# ====== Mock LLM (replace with openai when key is set) ======
async def llm_generate(topic, keyword, geo, article_type):
    api_key = os.getenv("OPENAI_API_KEY", "")
    ctx = rag_context(topic)

    if not api_key:
        # Full mock response
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

UI = r"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Healthy Gut AI | SEO Article Generator</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700&display=swap" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
<style>
:root{--p:#4F46E5;--s:#10B981}*{box-sizing:border-box;margin:0;padding:0}
body{font-family:Inter,sans-serif;background:#E0E7FF;min-height:100vh}
.g{position:fixed;border-radius:50%;filter:blur(80px);opacity:.6;z-index:-1;animation:d 20s infinite alternate}
.g1{width:600px;height:600px;background:linear-gradient(135deg,#4F46E5,#A78BFA);top:-100px;left:-100px}
.g2{width:500px;height:500px;background:linear-gradient(135deg,#10B981,#34D399);bottom:-100px;right:-100px;animation-delay:-10s}
@keyframes d{to{transform:translate(-50px,50px)}}
.w{max-width:900px;margin:0 auto;padding:3rem 1.5rem}
h1{text-align:center;font-size:2.8rem;font-weight:700;background:linear-gradient(to right,var(--p),var(--s));-webkit-background-clip:text;-webkit-text-fill-color:transparent;margin-bottom:.5rem}
p.s{text-align:center;color:#6B7280;margin-bottom:2rem}
.c{background:rgba(255,255,255,.75);backdrop-filter:blur(16px);border:1px solid rgba(255,255,255,.35);border-radius:1.5rem;padding:2.5rem;box-shadow:0 10px 40px rgba(0,0,0,.05)}
.f{margin-bottom:1.25rem}.r{display:flex;gap:1.25rem}.col{flex:1}
label{display:block;font-weight:600;margin-bottom:.45rem;color:#374151;font-size:.95rem}
input,select{width:100%;padding:.75rem 1rem;border:1px solid #D1D5DB;border-radius:.7rem;font:1rem Inter,sans-serif;background:rgba(255,255,255,.85)}
input:focus,select:focus{outline:none;border-color:var(--p);box-shadow:0 0 0 3px rgba(79,70,229,.18)}
.btn{width:100%;padding:1rem;font:700 1.1rem Inter,sans-serif;color:#fff;background:linear-gradient(135deg,var(--p),#818CF8);border:none;border-radius:.75rem;cursor:pointer;margin-top:1rem;transition:transform .2s,box-shadow .2s}
.btn:hover{transform:translateY(-2px);box-shadow:0 6px 18px rgba(79,70,229,.4)}
.hidden{display:none!important}
#load{text-align:center;margin-top:2rem}
.sp{width:40px;height:40px;border:4px solid rgba(79,70,229,.2);border-top:4px solid var(--p);border-radius:50%;animation:spin 1s linear infinite;margin:0 auto 1rem}
@keyframes spin{to{transform:rotate(360deg)}}
.res{margin-top:2rem}.rh{display:flex;justify-content:space-between;align-items:center;margin-bottom:1.5rem}
.mg{display:grid;grid-template-columns:1fr 1fr;gap:1rem;margin-bottom:1.5rem}
.mc{background:#fff;padding:1.25rem;border-radius:1rem;text-align:center}
.mc h3{font-size:2rem;color:var(--p)}.mc p{font-size:.85rem;color:#6B7280;text-transform:uppercase;letter-spacing:.05em;font-weight:600}
.ac{background:#fff;padding:2rem;border-radius:1rem;line-height:1.65;color:#1F2937}
.ac h1,.ac h2,.ac h3{margin:1.5rem 0 .6rem}.ac p{margin-bottom:.9rem}
.ac table{width:100%;border-collapse:collapse;margin-bottom:1.5rem}.ac th,.ac td{padding:.65rem;border:1px solid #E5E7EB}
.sm{margin-top:1.5rem;padding:1.25rem;background:#F3F4F6;border-radius:1rem;border-left:4px solid var(--s);font-size:.92rem}
.sm p{margin-bottom:.4rem}
</style></head><body>
<div class="g g1"></div><div class="g g2"></div>
<div class="w">
<h1>🥗 Healthy Gut AI</h1>
<p class="s">Medically accurate, SEO-optimised gut health articles — generated instantly.</p>
<div class="c">
  <form id="frm">
    <div class="f"><label>Article Topic</label><input name="topic" placeholder="e.g. Irritable Bowel Syndrome" required></div>
    <div class="f"><label>Primary Keyword</label><input name="primary_keyword" placeholder="e.g. IBS symptoms" required></div>
    <div class="f r">
      <div class="col"><label>Geo-Target</label><input name="geo_target" placeholder="e.g. New York, USA" required></div>
      <div class="col"><label>Article Type</label>
        <select name="article_type"><option value="pillar">Pillar (2500+ w)</option><option value="supporting">Supporting (1000+ w)</option></select>
      </div>
    </div>
    <button class="btn" id="btn" type="submit">✨ Generate Article</button>
  </form>
  <div id="load" class="hidden"><div class="sp"></div><p>Consulting RAG knowledge base and synthesising…</p></div>
</div>
<div id="res" class="res hidden c"></div>
</div>
<script>
document.getElementById('frm').addEventListener('submit',async e=>{
  e.preventDefault();
  const btn=document.getElementById('btn'),ld=document.getElementById('load'),rs=document.getElementById('res');
  btn.disabled=true;ld.classList.remove('hidden');rs.classList.add('hidden');
  try{
    const r=await fetch('/generate',{method:'POST',body:new FormData(e.target)});
    const d=await r.json();
    if(!r.ok||d.error){alert('Error: '+(d.error||'Server error'));return;}
    const den=d.metrics?.keywordDensity?.keywordDensityPercent??0;
    const rd=d.metrics?.readability?.fleschReadingEase??0;
    rs.innerHTML=`<div class="rh"><h2>Generated Article</h2>
      <button class="btn" style="width:auto;padding:.5rem 1.2rem;margin:0" onclick="window.print()">Print/PDF</button></div>
      <div class="mg"><div class="mc"><h3>${den}%</h3><p>Keyword Density</p></div>
      <div class="mc"><h3>${rd}</h3><p>Readability</p></div></div>
      <div class="ac">${marked.parse(d.optimized_article_markdown||'')}</div>
      <div class="sm"><p><strong>Meta:</strong> ${d.meta_description||''}</p>
      <p><strong>Slug:</strong> /${d.url_slug||''}</p>
      <p><strong>CTA:</strong> ${d.cta_direct||''}</p></div>`;
    rs.classList.remove('hidden');rs.scrollIntoView({behavior:'smooth'});
  }catch(err){alert('Connection failed.');}
  finally{btn.disabled=false;ld.classList.add('hidden');}
});
</script></body></html>"""

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/debug")
def debug():
    return {"routes": [r.path for r in app.routes]}

@app.get("/", response_class=HTMLResponse)
def root():
    return HTMLResponse(content=UI)

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
