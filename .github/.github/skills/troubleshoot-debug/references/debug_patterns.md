# Debug Patterns for AI Services

## Common Issues
- Model load failures due to path/config drift
- OOM from oversized batches or model duplication
- Latency regressions from synchronous I/O in request path
- 5xx spikes due to unhandled model exceptions

## Triage Sequence
1. Confirm deployment/runtime revision.
2. Inspect logs around first failure timestamp.
3. Check resource utilization and throttling.
4. Reproduce with benchmark probe.
5. Apply smallest viable fix and validate.
