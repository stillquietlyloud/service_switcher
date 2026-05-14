---
description: "Use when creating or updating Python code for AI services, diagnostics, and runtime tooling."
applyTo: "**/*.py"
---

## Python AI Service Conventions
- Use explicit type hints for function inputs/outputs.
- Keep inference logic separate from transport layers.
- Prefer clear, testable pure functions for preprocessing/postprocessing.
- Return structured error details where possible.

## Logging
- Log model initialization start/end and load duration.
- Log inference latency, batch size, and input shape metadata.
- Avoid logging raw sensitive payloads.

## Reliability
- Include startup checks for model path and runtime dependencies.
- Add health endpoints for service readiness.
- Fail fast on invalid configuration.
