# Code Quality Patterns Reference

Expected patterns and best practices for AI service projects. Use these as a baseline when evaluating projects.

---

## FastAPI Service Patterns

### Recommended Structure

```
project/
├── app/
│   ├── __init__.py
│   ├── main.py                 # Entry point
│   ├── api/
│   │   ├── __init__.py
│   │   ├── endpoints/
│   │   │   ├── __init__.py
│   │   │   ├── health.py       # /health, /ready endpoints
│   │   │   └── inference.py    # Main API routes
│   │   └── models.py           # Request/response Pydantic models
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py           # Configuration management
│   │   ├── logging.py          # Structured logging setup
│   │   └── security.py         # Auth, rate limiting
│   ├── ml/
│   │   ├── __init__.py
│   │   ├── model_loader.py     # Model loading, warmup
│   │   ├── inference.py        # Inference logic
│   │   └── preprocessing.py    # Input preprocessing
│   └── middleware/
│       ├── __init__.py
│       ├── error_handler.py    # Global error handling
│       └── logging.py          # Request/response logging
├── tests/
│   ├── __init__.py
│   ├── test_endpoints.py       # API endpoint tests
│   ├── test_inference.py       # Model inference tests
│   └── conftest.py             # Pytest fixtures
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── .github/workflows/
│   └── test.yml
├── README.md
└── pyproject.toml
```

---

### Pattern 1: Type-Hinted Endpoints

**✓ Good:**
```python
from typing import List
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI()

class InputRequest(BaseModel):
    text: str
    max_length: int = 100

class PredictionResponse(BaseModel):
    prediction: str
    confidence: float

@app.post("/predict", response_model=PredictionResponse)
async def predict(request: InputRequest) -> PredictionResponse:
    """Generate prediction from input text."""
    try:
        result = await model.inference(request.text)
        return PredictionResponse(
            prediction=result["output"],
            confidence=result["confidence"]
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
```

**✗ Poor:**
```python
@app.post("/predict")
async def predict(data):
    result = model.run(data)
    return result  # No type hints, no error handling
```

---

### Pattern 2: Structured Error Handling

**✓ Good:**
```python
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc):
    return JSONResponse(
        status_code=400,
        content={
            "error": "validation_error",
            "message": "Invalid request",
            "details": exc.errors()
        }
    )

@app.exception_handler(Exception)
async def generic_exception_handler(request, exc):
    logger.error("Unhandled exception", exc_info=exc)
    return JSONResponse(
        status_code=500,
        content={
            "error": "internal_error",
            "message": "An unexpected error occurred"
        }
    )
```

**✗ Poor:**
```python
@app.post("/predict")
async def predict(data):
    return model.run(data)  # Will crash on error with 500
```

---

### Pattern 3: Health & Ready Endpoints

**✓ Good:**
```python
from enum import Enum

class HealthStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"

@app.get("/health")
async def health_check() -> dict:
    """Service health status (liveness probe)."""
    return {
        "status": HealthStatus.HEALTHY,
        "timestamp": datetime.utcnow().isoformat()
    }

@app.get("/ready")
async def readiness_check() -> dict:
    """Service readiness for traffic (readiness probe)."""
    try:
        # Check model is loaded
        assert model is not None
        # Check database connection
        await db.execute("SELECT 1")
        return {
            "ready": True,
            "components": {
                "model": "loaded",
                "database": "connected"
            }
        }
    except Exception as e:
        logger.error("Readiness check failed", exc_info=e)
        return {
            "ready": False,
            "error": str(e)
        }, 503
```

**✗ Poor:**
```python
@app.get("/status")
async def status():
    return {"status": "ok"}  # No standard endpoints, insufficient info
```

---

### Pattern 4: Structured Logging

**✓ Good:**
```python
import logging
import json
from datetime import datetime
from pythonjsonlogger import jsonlogger

logger = logging.getLogger(__name__)

handler = logging.StreamHandler()
formatter = jsonlogger.JsonFormatter()
handler.setFormatter(formatter)
logger.addHandler(handler)

@app.post("/predict")
async def predict(request: InputRequest) -> PredictionResponse:
    logger.info("prediction_request_received", extra={
        "trace_id": request.headers.get("X-Trace-ID", "unknown"),
        "input_length": len(request.text),
        "timestamp": datetime.utcnow().isoformat()
    })
    
    try:
        result = await model.inference(request.text)
        logger.info("prediction_success", extra={
            "confidence": result["confidence"],
            "duration_ms": result["duration"]
        })
        return PredictionResponse(**result)
    except Exception as e:
        logger.error("prediction_failed", exc_info=e, extra={
            "error_type": type(e).__name__
        })
        raise
```

**✗ Poor:**
```python
@app.post("/predict")
async def predict(data):
    print(f"Predicting for {data}")  # Unstructured print to stdout
    return model.run(data)
```

---

### Pattern 5: Graceful Shutdown

**✓ Good:**
```python
import signal
import asyncio
from contextlib import asynccontextmanager

# Global state
active_requests = set()
shutdown_event = asyncio.Event()

@app.middleware("http")
async def track_requests(request, call_next):
    request_id = id(asyncio.current_task())
    active_requests.add(request_id)
    try:
        response = await call_next(request)
    finally:
        active_requests.discard(request_id)
    return response

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting service")
    await model.load()
    yield
    # Shutdown
    logger.info("Shutting down gracefully")
    shutdown_event.set()
    
    # Wait for in-flight requests
    timeout = 30
    start = asyncio.get_event_loop().time()
    while active_requests:
        if asyncio.get_event_loop().time() - start > timeout:
            logger.warning(f"Timeout waiting for {len(active_requests)} requests")
            break
        await asyncio.sleep(0.1)
    
    logger.info("Shutdown complete")

app = FastAPI(lifespan=lifespan)
```

**✗ Poor:**
```python
app = FastAPI()  # No lifecycle management, abrupt shutdown
```

---

### Pattern 6: Configuration Management

**✓ Good:**
```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Core
    app_name: str = "ml-service"
    debug: bool = False
    
    # Model
    model_path: str = "/models/model.pt"
    model_device: str = "cuda"  # or "cpu"
    
    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    workers: int = 4
    
    # Logging
    log_level: str = "INFO"
    
    # Database
    db_url: str = "postgresql://localhost/db"
    
    class Config:
        env_file = ".env"
        case_sensitive = False

settings = Settings()

# Usage in main.py
if __name__ == "__main__":
    uvicorn.run(
        app,
        host=settings.host,
        port=settings.port,
        workers=settings.workers,
        log_level=settings.log_level.lower()
    )
```

**✗ Poor:**
```python
MODEL_PATH = "/models/model.pt"
DB_USER = "admin"
DB_PASS = "password123"  # Hardcoded secrets!

# Hardcoded in code, no env config
```

---

## PyTorch Model Patterns

### Pattern: Device-Aware Model Loading

**✓ Good:**
```python
import torch
from typing import Optional

class ModelLoader:
    def __init__(self):
        self.device = self._get_device()
        self.model = None
    
    @staticmethod
    def _get_device() -> str:
        """Detect available device (GPU or CPU)."""
        if torch.cuda.is_available():
            device = "cuda"
            logger.info(f"Using GPU: {torch.cuda.get_device_name(0)}")
        else:
            device = "cpu"
            logger.warning("GPU not available, using CPU")
        return device
    
    def load(self, model_path: str) -> None:
        """Load and validate model."""
        try:
            self.model = torch.load(model_path, map_location=self.device)
            self.model.eval()  # Inference mode
            self.model.to(self.device)
            logger.info(f"Model loaded successfully on {self.device}")
        except Exception as e:
            logger.error(f"Failed to load model: {e}")
            raise
    
    def inference(self, input_tensor: torch.Tensor) -> torch.Tensor:
        """Run inference with error handling."""
        if self.model is None:
            raise RuntimeError("Model not loaded")
        
        with torch.no_grad():  # No gradients needed
            try:
                output = self.model(input_tensor.to(self.device))
            except RuntimeError as e:
                logger.error(f"Inference failed: {e}")
                raise
        
        return output.cpu()  # Return to CPU
```

**✗ Poor:**
```python
model = torch.load("model.pt")  # Hardcoded path, no error handling
output = model(input)  # May crash if GPU not available
```

---

### Pattern: Batch Processing with Error Handling

**✓ Good:**
```python
def batch_inference(
    model: torch.nn.Module,
    inputs: List[torch.Tensor],
    batch_size: int = 32,
    device: str = "cuda"
) -> List[torch.Tensor]:
    """Process inputs in batches with error handling."""
    results = []
    
    with torch.no_grad():
        for i in range(0, len(inputs), batch_size):
            batch = torch.stack(inputs[i:i+batch_size]).to(device)
            try:
                output = model(batch)
                results.extend(output.cpu().split(1))
            except RuntimeError as e:
                logger.error(f"Batch {i} failed: {e}")
                # Return placeholder results
                results.extend([None] * len(inputs[i:i+batch_size]))
    
    return results
```

**✗ Poor:**
```python
results = [model(inp.to("cuda")) for inp in inputs]  # No error handling, may OOM
```

---

## TensorFlow Model Patterns

### Pattern: Model Serving with Warmup

**✓ Good:**
```python
import tensorflow as tf
from typing import Dict, Any

class TFModelServer:
    def __init__(self, model_path: str):
        self.model = tf.keras.models.load_model(model_path)
        self.warmup_complete = False
    
    def warmup(self, warmup_data: tf.Tensor) -> None:
        """Warm up model to avoid cold-start latency."""
        logger.info("Starting model warmup...")
        try:
            _ = self.model(warmup_data, training=False)
            self.warmup_complete = True
            logger.info("Warmup complete")
        except Exception as e:
            logger.error(f"Warmup failed: {e}")
            raise
    
    def predict(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Run inference."""
        if not self.warmup_complete:
            raise RuntimeError("Model not warmed up")
        
        try:
            output = self.model(input_data, training=False)
            return {"prediction": output.numpy().tolist()}
        except Exception as e:
            logger.error(f"Prediction failed: {e}")
            raise
```

**✗ Poor:**
```python
model = tf.keras.models.load_model("model.h5")
predictions = model(data)  # No warmup, slow first request
```

---

## General Python Service Patterns

### Pattern: Dependency Injection

**✓ Good:**
```python
from abc import ABC, abstractmethod
from typing import Optional

class ModelProvider(ABC):
    @abstractmethod
    def get_model(self):
        pass

class LocalModelProvider(ModelProvider):
    def get_model(self):
        return load_local_model()

class RemoteModelProvider(ModelProvider):
    def get_model(self):
        return load_remote_model()

class PredictionService:
    def __init__(self, model_provider: ModelProvider):
        self.model_provider = model_provider
        self.model = model_provider.get_model()
    
    def predict(self, data):
        return self.model.inference(data)

# Easy to test and swap implementations
service = PredictionService(LocalModelProvider())
```

**✗ Poor:**
```python
class PredictionService:
    def __init__(self):
        self.model = load_local_model()  # Hard to test, tightly coupled

# Hard to mock, difficult to test
```

---

### Pattern: Testing Structure

**✓ Good:**
```python
# tests/test_endpoints.py
import pytest
from fastapi.testclient import TestClient
from app.main import app

@pytest.fixture
def client():
    return TestClient(app)

def test_health_endpoint(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"

def test_ready_endpoint_before_startup(client):
    """Ready should fail if model not loaded."""
    response = client.get("/ready")
    assert response.status_code in [503, 500]

@pytest.mark.asyncio
async def test_prediction_with_valid_input(client):
    response = client.post("/predict", json={
        "text": "hello world",
        "max_length": 100
    })
    assert response.status_code == 200
    assert "prediction" in response.json()

def test_prediction_with_invalid_input(client):
    response = client.post("/predict", json={})
    assert response.status_code == 422  # Validation error
```

**✗ Poor:**
```python
# No tests, or all tests in a single 1000-line file
def test_everything():
    pass  # Placeholder
```

---

## Anti-Patterns to Avoid

| ✗ Anti-Pattern | Why It's Bad | ✓ Better Way |
|---|---|---|
| Global state without cleanup | Causes test failures and hard-to-trace bugs | Use dependency injection or fixtures |
| Bare `except:` clauses | Catches all exceptions, including KeyboardInterrupt | Catch specific exceptions |
| No type hints on public APIs | IDE can't help, easier to pass wrong types | Add type hints to all public functions |
| Magic strings/hardcoded values | Hard to maintain, easy to miss when updating | Define constants or use configuration |
| Print to stdout for logging | Can't control levels, hard to parse | Use logging module with handlers |
| Large monolithic functions | Hard to test, hard to reuse | Break into smaller, testable functions |
| No error handling in main paths | Service crashes on edge cases | Add try-catch and proper error responses |
| No health checks | Can't monitor service, hard to orchestrate | Implement /health and /ready endpoints |
| Synchronous I/O in async code | Blocks event loop, reduces concurrency | Use async/await or thread pools |

---

*Code Quality Patterns v1.0*  
*Reference for Project Evaluator Agent*
