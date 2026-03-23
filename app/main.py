from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from app.services.llm_service import generate_article
from app.services.metrics import calculate_readability, calculate_keyword_density
import os

app = FastAPI(title="Healthy Gut AI Backend")

# Make sure static directory exists for serving
os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/", response_class=HTMLResponse)
async def read_root():
    with open("static/index.html", "r", encoding="utf-8") as f:
        return f.read()

@app.post("/generate")
async def generate(
    topic: str = Form(...),
    primary_keyword: str = Form(...),
    geo_target: str = Form(...),
    article_type: str = Form(...)
):
    try:
        # Generate with LLM & RAG
        result = await generate_article(topic, primary_keyword, geo_target, article_type)
        
        if "error" in result:
             return JSONResponse(status_code=500, content=result)
             
        article_md = result.get("optimized_article_markdown", "")
        
        # Calculate Metrics
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

