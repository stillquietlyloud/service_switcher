---
name: environment-audit
description: "Use when auditing host/runtime readiness for AI services, including Python environment, OS details, and GPU capability."
user-invocable: true
tools:
  - read
  - execute
  - search
---

# Environment Audit

## Purpose
Create a reliable baseline of runtime capabilities before development or troubleshooting.

## Procedure
1. Read current state from `.github/memory/environment.json` if present.
2. Run local environment probes:
   - `.github/skills/environment-audit/scripts/run_collect_env.sh`
   - `.github/skills/environment-audit/scripts/run_gpu_probe.sh`
3. Normalize key details into structured JSON.
4. Save summary findings in `.github/memory/sitrep.md`.

## Outputs
- Environment snapshot with Python/runtime/GPU state.
- Readiness flags and warnings.
- Suggested next skill (usually dependency-check or service-health).
