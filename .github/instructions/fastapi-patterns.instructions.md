---
description: "Use when implementing or troubleshooting FastAPI model serving routes, middleware, or startup lifecycle."
applyTo: "**/*fastapi*.py"
---

## FastAPI Service Patterns
- Use startup hooks to initialize model and runtime state.
- Keep request validation strict and explicit.
- Separate route handlers from model execution helpers.
- Include /health and /ready endpoints.

## Operational Guidance
- Add timeouts for external calls.
- Return stable response contracts.
- Capture request IDs in logs where available.
