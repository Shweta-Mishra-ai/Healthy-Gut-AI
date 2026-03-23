from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from app.services.llm_service import generate_article
from app.services.metrics import calculate_readability, calculate_keyword_density
import os

app = FastAPI(title="Healthy Gut AI Backend")

# ---  Single-file UI: embed HTML directly to avoid StaticFiles startup crash ---
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
body{font-family:'Inter',sans-serif;background:#E0E7FF;min-height:100vh;overflow-x:hidden;position:relative;}
.globe{position:fixed;border-radius:50%;filter:blur(80px);opacity:.6;z-index:-1;animation:drift 20s infinite alternate;}
.g1{width:600px;height:600px;background:linear-gradient(135deg,#4F46E5,#A78BFA);top:-100px;left:-100px;}
.g2{width:500px;height:500px;background:linear-gradient(135deg,#10B981,#34D399);bottom:-100px;right:-100px;animation-delay:-10s;}
@keyframes drift{0%{transform:translate(0,0);}100%{transform:translate(-50px,50px);}}
.container{max-width:900px;margin:0 auto;padding:3rem 1.5rem;}
header{text-align:center;margin-bottom:2.5rem;}
h1{font-size:3rem;font-weight:700;background:linear-gradient(to right,#4F46E5,#10B981);-webkit-background-clip:text;-webkit-text-fill-color:transparent;}
.glass{background:rgba(255,255,255,.7);backdrop-filter:blur(16px);border:1px solid rgba(255,255,255,.3);border-radius:1.5rem;padding:2.5rem;box-shadow:0 10px 40px rgba(0,0,0,.05);}
.form-group{margin-bottom:1.5rem;}
.row{display:flex;gap:1.5rem;}
.col{flex:1;}
label{display:block;font-weight:600;margin-bottom:.5rem;color:#374151;}
input,select{width:100%;padding:.8rem 1.2rem;border:1px solid #D1D5DB;border-radius:.75rem;font-size:1rem;font-family:inherit;background:rgba(255,255,255,.8);transition:all .3s ease;}
input:focus,select:focus{outline:none;border-color:#4F46E5;box-shadow:0 0 0 3px rgba(79,70,229,.2);}
.btn-primary{width:100%;padding:1rem;font-size:1.1rem;font-weight:600;color:#fff;background:linear-gradient(135deg,#4F46E5,#818CF8);border:none;border-radius:.75rem;cursor:pointer;transition:transform .2s,box-shadow .2s;margin-top:1rem;}
.btn-primary:hover{transform:translateY(-2px);box-shadow:0 5px 15px rgba(79,70,229,.4);}
.hidden{display:none!important;}
#loading{text-align:center;margin-top:2rem;}
.spinner{width:40px;height:40px;border:4px solid rgba(79,70,229,.2);border-top:4px solid #4F46E5;border-radius:50%;animation:spin 1s linear infinite;margin:0 auto 1rem;}
@keyframes spin{0%{transform:rotate(0deg);}100%{transform:rotate(360deg);}}
.results-panel{margin-top:2rem;}
.results-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:1.5rem;}
.metrics-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:1rem;margin-bottom:2rem;}
.metric-card{background:#fff;padding:1.5rem;border-radius:1rem;text-align:center;}
.metric-card h3{font-size:2rem;color:#4F46E5;margin-bottom:.2rem;}
.metric-card p{font-size:.9rem;color:#6B7280;text-transform:uppercase;letter-spacing:.05em;font-weight:600;}
.article-content{background:#fff;padding:2.5rem;border-radius:1rem;line-height:1.6;color:#1F2937;}
.article-content h1,.article-content h2,.article-content h3{margin:1.5rem 0 .75rem;}
.article-content p{margin-bottom:1rem;}
.article-content table{width:100%;border-collapse:collapse;margin-bottom:1.5rem;}
.article-content th,.article-content td{padding:.75rem;border:1px solid #E5E7EB;text-align:left;}
.seo-meta{margin-top:2rem;padding:1.5rem;background:#F3F4F6;border-radius:1rem;border-left:4px solid #10B981;}
.seo-meta p{margin-bottom:.5rem;font-size:.95rem;}
    </style>
</head>
<body>
    <div class="globe g1"></div>
    <div class="globe g2"></div>
    <main class="container">
        <header>
            <h1>🥗 Healthy Gut AI</h1>
            <p>Generate medically accurate, SEO-optimized gut health articles instantly.</p>
        </header>
        <section class="glass">
            <form id="generate-form">
                <div class="form-group">
                    <label>Article Topic</label>
                    <input type="text" name="topic" placeholder="e.g. Irritable Bowel Syndrome" required>
                </div>
                <div class="form-group">
                    <label>Primary Keyword</label>
                    <input type="text" name="primary_keyword" placeholder="e.g. IBS symptoms" required>
                </div>
                <div class="form-group row">
                    <div class="col">
                        <label>Geo-Target</label>
                        <input type="text" name="geo_target" placeholder="e.g. New York, USA" required>
                    </div>
                    <div class="col">
                        <label>Article Type</label>
                        <select name="article_type">
                            <option value="pillar">Pillar (2500+ words)</option>
                            <option value="supporting">Supporting (1000+ words)</option>
                        </select>
                    </div>
                </div>
                <button type="submit" id="btn" class="btn-primary">✨ Generate Article</button>
            </form>
            <div id="loading" class="hidden"><div class="spinner"></div><p>Consulting knowledge base and synthesizing…</p></div>
        </section>
        <section id="results" class="results-panel glass hidden"></section>
    </main>
    <script>
document.getElementById('generate-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const btn = document.getElementById('btn');
    const loading = document.getElementById('loading');
    const results = document.getElementById('results');
    btn.disabled = true; loading.classList.remove('hidden'); results.classList.add('hidden');
    try {
        const res = await fetch('/generate', {method:'POST', body: new FormData(e.target)});
        const data = await res.json();
        if (!res.ok || data.error) { alert('Error: ' + (data.error || 'Server error')); return; }
        const density = data.metrics?.keywordDensity?.keywordDensityPercent ?? 0;
        const readability = data.metrics?.readability?.fleschReadingEase ?? 0;
        results.innerHTML = `
            <div class="results-header"><h2>Generated Article</h2>
            <button class="btn-primary" style="width:auto;padding:.5rem 1.5rem;margin-top:0" onclick="window.print()">Print / PDF</button></div>
            <div class="metrics-grid">
                <div class="metric-card"><h3>${density}%</h3><p>Keyword Density</p></div>
                <div class="metric-card"><h3>${readability}</h3><p>Readability Score</p></div>
            </div>
            <div class="article-content">${marked.parse(data.optimized_article_markdown||'')}</div>
            <div class="seo-meta">
                <p><strong>Meta:</strong> ${data.meta_description||''}</p>
                <p><strong>Slug:</strong> /${data.url_slug||''}</p>
                <p><strong>CTA:</strong> ${data.cta_direct||''}</p>
            </div>`;
        results.classList.remove('hidden');
        results.scrollIntoView({behavior:'smooth'});
    } catch(err) { alert('Connection failed.'); }
    finally { btn.disabled = false; loading.classList.add('hidden'); }
});
    </script>
</body>
</html>"""

@app.get("/health")
async def health_check():
    return {"status": "ok"}

@app.get("/", response_class=HTMLResponse)
async def read_root():
    return HTMLResponse(content=UI_HTML)

@app.post("/generate")
async def generate(
    topic: str = Form(...),
    primary_keyword: str = Form(...),
    geo_target: str = Form(...),
    article_type: str = Form(...)
):
    try:
        result = await generate_article(topic, primary_keyword, geo_target, article_type)

        if "error" in result:
            return JSONResponse(status_code=500, content=result)

        article_md = result.get("optimized_article_markdown", "")
        readability = calculate_readability(article_md)
        keyword_density = calculate_keyword_density(article_md, primary_keyword)

        result["metrics"] = {
            "readability": readability,
            "keywordDensity": keyword_density
        }

        return JSONResponse(content=result)
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port)
