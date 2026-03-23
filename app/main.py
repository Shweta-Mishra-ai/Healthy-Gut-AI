from fastapi import FastAPI
from app.routes.generate import router

app = FastAPI(title="Healthy Gut AI")

app.include_router(router)
