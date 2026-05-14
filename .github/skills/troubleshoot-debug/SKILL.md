---
name: troubleshoot-debug
description: "Use when diagnosing failures, latency regressions, OOM issues, or service instability in AI workloads."
user-invocable: true
tools:
  - read
  - execute
  - search
---

# Troubleshoot and Debug

## Purpose
Perform focused root-cause analysis and produce safe, testable remediation options.

## Procedure
1. Collect logs with `.github/skills/troubleshoot-debug/scripts/run_logs_collect.sh`.
2. Run benchmark probe for latency and throughput clues.
3. Correlate errors with recent config/dependency changes.
4. Produce likely causes ranked by confidence.
5. Propose fixes and explicit verification commands.
6. Update `.github/memory/sitrep.md` with root-cause and remediation status.
7. Append diagnostics commands and evidence to `.github/memory/execution_log.md`.
8. Update point statuses in `.github/memory/action_tracker.md`.

## Outputs
- Root-cause hypothesis list with confidence labels.
- Minimal remediation set.
- Validation sequence and rollback notes.
- Updated SITREP, execution log, and action tracker entries.
