---
description: "Use when editing PyTorch inference services, model loading code, or GPU device handling logic."
applyTo: "**/*torch*.py"
---

## PyTorch Patterns
- Resolve device once and pass explicitly to model and tensors.
- Use eval mode and disable gradients for inference.
- Validate checkpoint compatibility at startup.
- Handle CPU fallback if GPU is unavailable.

## Performance
- Warm up model after load.
- Use no_grad and consider autocast when appropriate.
- Keep preprocessing on CPU unless proven beneficial on GPU.
