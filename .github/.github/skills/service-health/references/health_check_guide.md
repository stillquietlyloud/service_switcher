# Service Health Guide

## Required Checks
- API liveness endpoint responds
- Readiness endpoint confirms model loaded
- Process memory and CPU within thresholds
- GPU memory pressure monitored when enabled
- P95 inference latency tracked

## Escalation
- If error rate spikes, collect logs and invoke troubleshoot-debug.
- If latency regresses, run benchmark probe and inspect model load path.
