from fastapi import FastAPI

app = FastAPI()

@app.get("/")
def root():
    return {"status": "WORKING"}

@app.get("/health")
def health():
    return {"status": "ok"}
