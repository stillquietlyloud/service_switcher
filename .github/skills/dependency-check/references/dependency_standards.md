# Dependency Standards

## Baseline Policy
- Pin production dependencies with conservative version ranges.
- Validate PyTorch/TensorFlow compatibility before upgrades.
- Keep FastAPI and ASGI server versions aligned.

## Checks
- Missing critical packages
- Incompatible major versions
- Duplicate or conflicting transitive dependencies
- Known CVE advisories for runtime packages
