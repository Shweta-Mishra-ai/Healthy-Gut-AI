from fastapi import FastAPI

app = FastAPI()

@app.get("/")
def home():
    return {"message": "WORKING ✅"}

@app.get("/health")
def health():
    return {"status": "ok"}
