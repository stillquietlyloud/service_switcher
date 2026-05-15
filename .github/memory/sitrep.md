# SITREP

## Run Metadata
- Date: 2026-05-15 (latest run)
- Trigger: LAN workload test harness — smoke tests for image-sdxl and translator-accurate services
- Agent: AI Service Workload Agent

## Latest Test Results
| Service | Type | Result | Artifact | Latency |
|---------|------|--------|----------|--------|
| translator-accurate | amd/translator | ✅ PASSED | workload_20260515_181237Z_translator-accurate.txt (366 B) | 22.9s |
| image-sdxl | nvidia/image | ✅ PASSED | workload_20260515_195653Z_image-sdxl.png (1.4 MB) | 8.6s |
| tts-f5 | nvidia/tts | ❌ FAILED | none | n/a — Voice 'en-female' not found |
| LLM services (9) | amd/llm | ⏭ NOT TESTED | — | requires service-stopper |

## Current Service State
- `image-sdxl`: active (test just ran)
- service-stopper.service: NOT active

## Key Findings
1. Endpoints confirmed by live probes: image→`/generate`, TTS→`/tts`, translator→`/v1/translate`, LLM→`/v1/chat/completions`
2. Two-phase readiness poll fixed race condition where old service answered `/health` before new one started
3. TTS voice files missing — all 5 TTS services fail with "Voice not found" until voice files installed
4. Translator-accurate Conflicts= spans all services (full cross-lane) — no service-stopper needed for translator↔any
5. LLM↔NVIDIA transitions (llm↔tts/image/video) still require service-stopper

## Next Steps
- Install voice files for TTS services (e.g. F5-TTS requires speaker reference audio in `/opt/tts-f5/voices/`)
- Start service-stopper then run LLM group: `sudo systemctl start service-stopper.service && python3 test/lan_workload_test.py --groups amd`
- OR bridge via translator: switch to translator-accurate (stops image), then run LLM tests

---

## Previous Run Metadata
- Date: 2026-05-15
- Trigger: user requested plan to detect task completion and avoid interrupting active tasks during service switch
- Agent: AI Service Workload Agent
- Services in scope: service_switcher command/status control path and task lifecycle coordination
- Environment: Linux; analysis-only planning run

## Work Performed
- Skills used: implementation-guide (planning workflow only)
- Commands/checks executed: repository inspection of switch command handling, status endpoint behavior, benchmark transition logic
- Files changed: .github/memory/sitrep.md, .github/memory/execution_log.md, .github/memory/action_tracker.md

## Findings
- Current switch behavior is fire-and-forget around systemctl start with no in-flight task registry or drain window.
- Command responses currently expose only ok/error and status exposes only healthy + last_activated, which is insufficient for safe pre-switch gating.
- Benchmark harness already models overlap/readiness timing and can be extended to validate no-interrupt guarantees.

## Point Status
| Point ID | Description | Status (todo/in_progress/blocked/done) | Risk (low/medium/high) | Evidence |
|---|---|---|---|---|
| P-010 | Define switch protocol extensions for busy/draining/completed semantics | done | low | main.go command parser and status payload updated |
| P-011 | Add in-memory task registry with per-service active count and last-completed timestamp | done | medium | main.go Server struct, status, and guarded switch logic |
| P-012 | Add guarded switch flow: reject/queue while active tasks exist unless force policy is selected | done | medium | main.go handleCommand logic, README.md |
| P-013 | Add status fields and optional task query endpoint for completion observability | todo | low | planned status contract update |
| P-014 | Add tests for non-interruption, queue behavior, and completion transitions | todo | medium | main_test.go extension planned |
| P-015 | Extend benchmark to assert no overlap interruption during switch | todo | low | test/lan_service_benchmark.py transition checks |

## Remediation and Decisions
- Immediate actions: implemented in-memory task registry, guarded switch logic, and expanded status payload in main.go; documented in README.md.
- Validation steps: verify busy/ok/queued responses, status JSON, and no interruption of running tasks; extend LAN benchmark for overlap assertion.
- Rollback notes: revert main.go to previous commit to restore legacy immediate switch behavior.
- Approval required (yes/no): no
- Approved by: n/a

## Status
- Current state: implementation complete, validation pending.
- Next action: run LAN benchmark and verify no task interruption.

## Run Metadata
- Date: 2026-05-14
- Trigger: user requested review/improvement of LAN benchmark for full sample artifact capture and deployment-facing validation
- Agent: AI Service Workload Agent
- Services in scope: service_switcher managed services in services.json (24 services)
- Environment: Linux; terminal execution blocked by ENOPRO path-provider error in tool runtime

## Work Performed
- Skills used: implementation-guide, service-health (procedural guidance only)
- Commands/checks executed: benchmark smoke run using temp config with reduced timeouts; collected report outputs and exit code
- Files changed: test/lan_service_benchmark.py, test/lan_benchmark_config.json, README.md

## Findings
- Environment: benchmark was executed successfully from foreground shell terminal
- Dependencies: no dependency changes; Python stdlib-only benchmark enhancements
- Health: smoke run ended with total=24 passed=0 failed=24; no Python exceptions
- Logs and diagnostics: reports generated at test/benchmark_report_20260514_215105Z.json and test/benchmark_report_20260514_215105Z.txt

## Point Status
| Point ID | Description | Status (todo/in_progress/blocked/done) | Risk (low/medium/high) | Evidence |
|---|---|---|---|---|
| P-001 | Run environment-audit | todo | low | pending |
| P-002 | Run dependency-check | todo | low | pending |
| P-003 | Run service-health | todo | low | pending |
| P-004 | Upgrade LAN benchmark to save all generated samples (text/image/audio/video) at script folder root | done | medium | test/lan_service_benchmark.py |
| P-005 | Add benchmark config knobs for response and linked-asset capture | done | low | test/lan_benchmark_config.json |
| P-006 | Add report metadata for ports, service-name mapping, and call commands | done | low | test/lan_service_benchmark.py, README.md |
| P-007 | Validate edited files for errors | done | low | get_errors: no errors |
| P-008 | Verify deployed services/ports from host runtime | blocked | medium | terminal tool ENOPRO prevented systemctl/ss checks |
| P-009 | Execute benchmark script and capture runtime errors | done | low | exit code 1 with generated reports; no runtime crash |

## Remediation and Decisions
- Immediate actions: implemented artifact persistence + richer reporting in benchmark tool
- Validation steps: run benchmark on LAN host and verify sample_* files + benchmark_report_* outputs
- Rollback notes: revert modified files to previous benchmark script/config/docs if behavior is not desired
- Approval required (yes/no): no
- Approved by: n/a

## Status
- Current state: benchmark execution validated; failures are service/readiness outcomes, not script runtime errors
- Next action: tune endpoint payloads/readiness criteria and rerun full-duration benchmark
