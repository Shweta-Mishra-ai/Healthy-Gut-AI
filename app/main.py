from fastapi import FastAPI

app = FastAPI()


@app.get("/")
def home():
    return {"message": "Healthy Gut AI is running 🚀"}


@app.get("/health")
def health():
    return {"status": "ok"}
