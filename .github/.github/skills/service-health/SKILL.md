---
name: service-health
description: "Use when checking AI service availability, endpoint readiness, resource pressure, and baseline latency."
user-invocable: true
tools:
  - read
  - execute
  - search
---

# Service Health

## Purpose
Measure service operability and identify immediate runtime bottlenecks.

## Procedure
1. Run service probes using `.github/skills/service-health/scripts/run_service_check.sh`.
2. Run GPU/resource probes with `.github/skills/service-health/scripts/run_gpu_probe.sh`.
3. If available, run benchmark probe to sample latency.
4. Compare with previous baseline in `.github/memory/service_state.json`.
5. Update `.github/memory/sitrep.md` with service health outcomes.
6. Append probes, metrics summary, and evidence to `.github/memory/execution_log.md`.
7. Update point statuses in `.github/memory/action_tracker.md`.

## Outputs
- Service up/down and endpoint readiness summary.
- Resource utilization and anomaly indicators.
- Recommended follow-up skill (troubleshoot-debug or implementation-guide).
- Updated SITREP, execution log, and action tracker entries.
