from fastapi import FastAPI

app = FastAPI()

@app.get("/")
def home():
    return {"message": "Healthy Gut AI running ✅"}

@app.get("/health")
def health():
    return {"status": "ok"}
