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
4. Update `.github/memory/sitrep.md` with current environment findings.
5. Append run evidence and commands to `.github/memory/execution_log.md`.
6. Update point statuses in `.github/memory/action_tracker.md`.

## Outputs
- Environment snapshot with Python/runtime/GPU state.
- Readiness flags and warnings.
- Suggested next skill (usually dependency-check or service-health).
- Updated SITREP, execution log, and action tracker entries.
