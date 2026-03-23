from fastapi import FastAPI
from app.routes.generate import router

app = FastAPI(title="Healthy Gut AI")

# Root route (VERY IMPORTANT for Railway)
@app.get("/")
def home():
    return {"status": "ok", "message": "Healthy Gut AI is running 🚀"}

# Health check route
@app.get("/health")
def health():
    return {"status": "healthy"}

# Your main route
app.include_router(router)
