# Action Tracker

Track each finding/remediation point until closure.

| Point ID | Category | Description | Owner | Risk | Status (todo/in_progress/blocked/done) | Evidence | Last Updated |
|---|---|---|---|---|---|---|---|
| P-001 | baseline | Run environment-audit | AI Service Workload Agent | low | todo | pending | not set |
| P-002 | baseline | Run dependency-check | AI Service Workload Agent | low | todo | pending | not set |
| P-003 | baseline | Run service-health | AI Service Workload Agent | low | todo | pending | not set |
| P-004 | benchmark | Save all generated response samples (text/image/audio/video) to script directory root | AI Service Workload Agent | medium | done | test/lan_service_benchmark.py | 2026-05-14 |
| P-005 | benchmark | Add sample-capture controls to benchmark config | AI Service Workload Agent | low | done | test/lan_benchmark_config.json | 2026-05-14 |
| P-006 | benchmark | Add report details for ports, services, and call commands | AI Service Workload Agent | low | done | test/lan_service_benchmark.py, README.md | 2026-05-14 |
| P-007 | validation | Validate modified files for editor errors | AI Service Workload Agent | low | done | get_errors returned no issues | 2026-05-14 |
| P-008 | runtime-check | Validate deployed services and live ports via host commands | AI Service Workload Agent | medium | blocked | terminal ENOPRO blocked systemctl/ss checks | 2026-05-14 |
| P-009 | runtime-check | Run benchmark script and monitor runtime errors | AI Service Workload Agent | low | done | benchmark_report_20260514_215105Z.json and .txt; exit code 1 | 2026-05-14 |
| P-010 | switch-coordination | Define switch protocol extensions for busy/draining/completed semantics | AI Service Workload Agent | low | done | main.go command and status behavior updated | 2026-05-15 |
| P-011 | switch-coordination | Add in-memory task registry with per-service active count and last-completed timestamp | AI Service Workload Agent | medium | done | main.go Server struct, status, and guarded switch logic | 2026-05-15 |
| P-012 | switch-coordination | Add guarded switch flow to avoid interruption while active tasks exist (reject/queue policy) | AI Service Workload Agent | medium | done | main.go handleCommand logic, README.md | 2026-05-15 |
| P-013 | observability | Expand status payload and add optional task query endpoint | AI Service Workload Agent | low | todo | planned protocol/status extension | 2026-05-15 |
| P-014 | validation | Add tests for busy handling, queue behavior, and completion transitions | AI Service Workload Agent | medium | todo | main_test.go expansion planned | 2026-05-15 |
| P-015 | validation | Extend LAN benchmark assertions for non-interrupting switches | AI Service Workload Agent | low | todo | test/lan_service_benchmark.py transition checks | 2026-05-15 |
| P-016 | workload-test | Build LAN workload test harness with real inference payloads and artifact saving | AI Service Workload Agent | medium | done | test/lan_workload_test.py + test/lan_workload_test_config.json | 2026-05-15 |
| P-017 | workload-test | Smoke-test translator-accurate | AI Service Workload Agent | low | done | workload_20260515_181237Z_translator-accurate.txt — PASSED | 2026-05-15 |
| P-018 | workload-test | Smoke-test image-sdxl | AI Service Workload Agent | low | done | workload_20260515_195653Z_image-sdxl.png 1.4MB — PASSED | 2026-05-15 |
| P-019 | workload-test | TTS voice files missing on tts-f5 (and likely all TTS services) | AI Service Workload Agent | medium | blocked | GET /voices returns []; "Voice 'en-female' not found" | 2026-05-15 |
| P-020 | workload-test | Smoke-test LLM services (9 services) | AI Service Workload Agent | medium | todo | Requires service-stopper; bridge via translator if needed | 2026-05-15 |
| P-021 | architecture | Plan: integrate idle-shutdown into service-switcher (replace service-stopper + auto-shutdown) | AI Service Workload Agent | medium | done | docs/engineering/idle-shutdown-plan.md v2 (hybrid lock+hardware) | 2026-05-16 |
| P-022 | architecture | Implement idle-shutdown integration (awaiting user approval) | user | high | todo | Pending review of idle-shutdown-plan.md v2 | 2026-05-16 |
