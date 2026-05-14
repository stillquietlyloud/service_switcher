from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Any, Dict
import time

app = FastAPI(title="AI Service", version="0.1.0")


class PredictRequest(BaseModel):
    payload: Dict[str, Any]


class PredictResponse(BaseModel):
    output: Dict[str, Any]
    latency_ms: float


def run_inference(payload: Dict[str, Any]) -> Dict[str, Any]:
    # Replace with real model inference.
    return {"echo": payload}


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/ready")
def ready() -> Dict[str, str]:
    return {"status": "ready"}


@app.post("/predict", response_model=PredictResponse)
def predict(request: PredictRequest) -> PredictResponse:
    start = time.perf_counter()
    try:
        output = run_inference(request.payload)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    latency_ms = (time.perf_counter() - start) * 1000.0
    return PredictResponse(output=output, latency_ms=latency_ms)
