from fastapi import FastAPI
from app.routes.generate import router

app = FastAPI()

@app.get("/")
def root():
    return {"message": "API is working ✅"}

@app.get("/health")
def health():
    return {"status": "ok"}

# IMPORTANT: add prefix
app.include_router(router, prefix="")
