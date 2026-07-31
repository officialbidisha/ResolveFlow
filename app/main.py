from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()


class AnalyzeRequest(BaseModel):
    url: str


@app.get("/")
def home():
    return {
        "message": "GitHub Issue Agent API is running!"
    }


@app.post("/analyze")
def analyze(request: AnalyzeRequest):
    return {
        "status": "received",
        "url": request.url
    }