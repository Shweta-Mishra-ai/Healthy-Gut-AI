from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse, JSONResponse
import os

app = FastAPI(title="Healthy Gut AI Backend")

UI_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Healthy Gut AI | SEO Article Generator</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700&display=swap" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
<style>
:root{--primary:#4F46E5;--secondary:#10B981;--dark:#1F2937;}
*{box-sizing:border-box;margin:0;padding:0;}
body{font-family:Inter,sans-serif;background:#E0E7FF;min-height:100vh;}
.glob{position:fixed;border-radius:50%;filter:blur(80px);opacity:.6;z-index:-1;animation:drift 20s infinite alternate;}
.g1{width:600px;height:600px;background:linear-gradient(135deg,#4F46E5,#A78BFA);top:-100px;left:-100px;}
.g2{width:500px;height:500px;background:linear-gradient(135deg,#10B981,#34D399);bottom:-100px;right:-100px;animation-delay:-10s;}
@keyframes drift{0%{transform:translate(0,0);}100%{transform:translate(-50px,50px);}}
.wrap{max-width:900px;margin:0 auto;padding:3rem 1.5rem;}
h1{text-align:center;font-size:2.8rem;font-weight:700;background:linear-gradient(to right,#4F46E5,#10B981);-webkit-background-clip:text;-webkit-text-fill-color:transparent;margin-bottom:.5rem;}
p.sub{text-align:center;color:#6B7280;margin-bottom:2rem;}
.card{background:rgba(255,255,255,.75);backdrop-filter:blur(16px);border:1px solid rgba(255,255,255,.35);border-radius:1.5rem;padding:2.5rem;box-shadow:0 10px 40px rgba(0,0,0,.05);}
.fg{margin-bottom:1.25rem;}
.row{display:flex;gap:1.25rem;}
.col{flex:1;}
label{display:block;font-weight:600;margin-bottom:.45rem;color:#374151;font-size:.95rem;}
input,select{width:100%;padding:.75rem 1rem;border:1px solid #D1D5DB;border-radius:.7rem;font:1rem Inter,sans-serif;background:rgba(255,255,255,.85);}
input:focus,select:focus{outline:none;border-color:#4F46E5;box-shadow:0 0 0 3px rgba(79,70,229,.18);}
.btn{width:100%;padding:1rem;font:700 1.1rem Inter,sans-serif;color:#fff;background:linear-gradient(135deg,#4F46E5,#818CF8);border:none;border-radius:.75rem;cursor:pointer;margin-top:1rem;transition:transform .2s,box-shadow .2s;}
.btn:hover{transform:translateY(-2px);box-shadow:0 6px 18px rgba(79,70,229,.4);}
.hidden{display:none!important;}
#loading{text-align:center;margin-top:2rem;}
.sp{width:40px;height:40px;border:4px solid rgba(79,70,229,.2);border-top:4px solid #4F46E5;border-radius:50%;animation:spin 1s linear infinite;margin:0 auto 1rem;}
@keyframes spin{to{transform:rotate(360deg);}}
.res{margin-top:2rem;}
.rh{display:flex;justify-content:space-between;align-items:center;margin-bottom:1.5rem;}
.mg{display:grid;grid-template-columns:1fr 1fr;gap:1rem;margin-bottom:1.5rem;}
.mc{background:#fff;padding:1.25rem;border-radius:1rem;text-align:center;}
.mc h3{font-size:2rem;color:#4F46E5;}
.mc p{font-size:.85rem;color:#6B7280;text-transform:uppercase;letter-spacing:.05em;font-weight:600;}
.ac{background:#fff;padding:2rem;border-radius:1rem;line-height:1.65;color:#1F2937;}
.ac h1,.ac h2,.ac h3{margin:1.5rem 0 .6rem;}
.ac p{margin-bottom:.9rem;}
.ac table{width:100%;border-collapse:collapse;margin-bottom:1.5rem;}
.ac th,.ac td{padding:.65rem;border:1px solid #E5E7EB;}
.sm{margin-top:1.5rem;padding:1.25rem;background:#F3F4F6;border-radius:1rem;border-left:4px solid #10B981;font-size:.92rem;}
.sm p{margin-bottom:.4rem;}
</style>
</head>
<body>
<div class="glob g1"></div>
<div class="glob g2"></div>
<div class="wrap">
  <h1>🥗 Healthy Gut AI</h1>
  <p class="sub">Medically accurate, SEO-optimized gut health articles — generated instantly.</p>
  <div class="card">
    <form id="form">
      <div class="fg"><label>Article Topic</label><input name="topic" placeholder="e.g. Irritable Bowel Syndrome" required></div>
      <div class="fg"><label>Primary Keyword</label><input name="primary_keyword" placeholder="e.g. IBS symptoms" required></div>
      <div class="fg row">
        <div class="col"><label>Geo-Target</label><input name="geo_target" placeholder="e.g. New York, USA" required></div>
        <div class="col"><label>Article Type</label>
          <select name="article_type"><option value="pillar">Pillar (2500+ words)</option><option value="supporting">Supporting (1000+ words)</option></select>
        </div>
      </div>
      <button class="btn" id="btn" type="submit">✨ Generate Article</button>
    </form>
    <div id="loading" class="hidden"><div class="sp"></div><p>Consulting RAG knowledge base and synthesising…</p></div>
  </div>
  <div id="results" class="res hidden card"></div>
</div>
<script>
document.getElementById('form').addEventListener('submit',async(e)=>{
  e.preventDefault();
  const btn=document.getElementById('btn'),load=document.getElementById('loading'),res=document.getElementById('results');
  btn.disabled=true;load.classList.remove('hidden');res.classList.add('hidden');
  try{
    const r=await fetch('/generate',{method:'POST',body:new FormData(e.target)});
    const d=await r.json();
    if(d.error){alert('Error: '+d.error);return;}
    const den=d.metrics?.keywordDensity?.keywordDensityPercent??0;
    const read=d.metrics?.readability?.fleschReadingEase??0;
    res.innerHTML=`<div class="rh"><h2>Generated Article</h2>
      <button class="btn" style="width:auto;padding:.5rem 1.2rem;margin:0" onclick="window.print()">Print / PDF</button></div>
      <div class="mg"><div class="mc"><h3>${den}%</h3><p>Keyword Density</p></div>
      <div class="mc"><h3>${read}</h3><p>Readability Score</p></div></div>
      <div class="ac">${marked.parse(d.optimized_article_markdown||'')}</div>
      <div class="sm"><p><strong>Meta:</strong> ${d.meta_description||''}</p>
      <p><strong>Slug:</strong> /${d.url_slug||''}</p>
      <p><strong>CTA:</strong> ${d.cta_direct||''}</p></div>`;
    res.classList.remove('hidden');res.scrollIntoView({behavior:'smooth'});
  }catch(err){alert('Connection failed.');}
  finally{btn.disabled=false;load.classList.add('hidden');}
});
</script>
</body>
</html>"""

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.get("/debug")
async def debug():
    return {"routes": [r.path for r in app.routes]}

@app.get("/", response_class=HTMLResponse)
async def root():
    return HTMLResponse(content=UI_HTML)

@app.post("/generate")
async def generate(
    topic: str = Form(...),
    primary_keyword: str = Form(...),
    geo_target: str = Form(...),
    article_type: str = Form(...)
):
    try:
        from app.services.llm_service import generate_article
        from app.services.metrics import calculate_readability, calculate_keyword_density
        result = await generate_article(topic, primary_keyword, geo_target, article_type)
        if "error" in result:
            return JSONResponse(status_code=500, content=result)
        article_md = result.get("optimized_article_markdown", "")
        result["metrics"] = {
            "readability": calculate_readability(article_md),
            "keywordDensity": calculate_keyword_density(article_md, primary_keyword)
        }
        return JSONResponse(content=result)
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port)
