# PyTorch Service Patterns

- Load model once during startup and keep it in memory.
- Use model.eval and no_grad for inference.
- Add explicit device selection and CPU fallback.
- Warm up the model to reduce first-request latency.
- Prefer deterministic preprocessing pipelines.
