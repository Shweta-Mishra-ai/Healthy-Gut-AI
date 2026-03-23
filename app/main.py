from fastapi import FastAPI
from app.routes.generate import router

app = FastAPI()

@app.get("/")
def root():
    return {"message": "Healthy Gut AI is LIVE 🚀"}

@app.get("/health")
def health():
    return {"status": "ok"}

app.include_router(router)
