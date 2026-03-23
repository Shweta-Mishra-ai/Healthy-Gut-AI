from fastapi import FastAPI
from app.routes.generate import router

app = FastAPI(title="Healthy Gut AI")

@app.get("/")
async def root():
    return {"status": "ok"}

@app.get("/health")
async def health():
    return {"status": "healthy"}

app.include_router(router)
