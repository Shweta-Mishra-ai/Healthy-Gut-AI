from fastapi import FastAPI
from app.routes.generate import router

app = FastAPI()

# ✅ ROOT FIX (IMPORTANT)
@app.get("/")
def root():
    return {"message": "Healthy Gut AI is LIVE 🚀"}

# optional but good
@app.get("/health")
def health():
    return {"status": "ok"}

# include your API routes
app.include_router(router)
