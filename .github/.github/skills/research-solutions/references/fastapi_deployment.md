# FastAPI Deployment Patterns

- Separate startup initialization from request execution.
- Expose /health and /ready endpoints.
- Use worker counts that match CPU and model memory constraints.
- Apply timeouts and graceful shutdown handlers.
- Capture structured logs for request and inference metrics.
