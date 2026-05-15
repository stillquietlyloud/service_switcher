# Paths, Folders, and Assets

**Audience:** Maintainers, contributors  
**Last updated:** 2026-05-15

---

## Repository layout

```
/git/service_switcher/
│
├── main.go                          # Switcher server — all Go source
├── main_test.go                     # Unit tests
├── go.mod                           # Go module definition
├── services.json                    # Service registry (source copy)
├── service-switcher.service         # systemd unit template
├── install.sh                       # Build + install script
├── README.md                        # Developer quick-start
│
├── test/
│   ├── LAN_WORKLOAD_TEST.md         # Harness reference documentation
│   ├── lan_workload_test.py         # End-to-end quality test harness
│   ├── lan_workload_test_config.json  # Per-service endpoint config
│   ├── lan_service_tester.py        # Simple portable tester
│   ├── lan_service_benchmark.py     # Timing benchmark harness
│   ├── lan_benchmark_config.json    # Benchmark config
│   ├── probe_api.py                 # OpenAPI schema probe (one-shot)
│   └── workload_report_*/           # Generated test reports
│
└── docs/                            # This documentation package
    ├── 00-index.md
    ├── executives/10-executive-summary.md
    ├── engineering/20-architecture-and-logic.md
    ├── integration/30-api-endpoints-reference.md
    ├── engineering/40-functions-and-modules-catalog.md
    ├── security/50-permissions-and-security.md
    ├── operations/60-operations-runbook.md
    ├── maintainers/70-paths-folders-and-assets.md  ← this file
    └── leadership/80-best-practices-gap-analysis.md
```

---

## Deployed paths (on the AI node)

| Path | Purpose |
|---|---|
| `/opt/service_switcher/` | Installation root |
| `/opt/service_switcher/service_switcher` | Go binary |
| `/opt/service_switcher/services.json` | Live service registry |
| `/etc/systemd/system/service-switcher.service` | Switcher systemd unit |
| `/etc/systemd/system/<service-name>.service` | Individual AI service units (one per service) |

---

## Key config files

### `/opt/service_switcher/services.json`

Runtime configuration for the switcher. Contains:
- `command_listen_address` — TCP address for command port (default `0.0.0.0:20100`)
- `status_listen_address` — TCP address for status port (default `0.0.0.0:30100`)
- `services` — map of service name → systemd unit file path

Source copy: [services.json](../../services.json)

### `test/lan_workload_test_config.json`

Test harness configuration. Contains:
- Switcher host and port addresses
- Timeout settings
- Per-service endpoint URLs, request payloads, and quality criteria

Source copy: [test/lan_workload_test_config.json](../../test/lan_workload_test_config.json)

---

## Generated artifacts

The workload test harness writes output to `test/`:

| Pattern | Content |
|---|---|
| `workload_report_<timestamp>.json` | Machine-readable full test results |
| `workload_report_<timestamp>.txt` | Human-readable report |
| `workload_<timestamp>_<service>.<ext>` | Inference artifact (PNG, WAV, MP3, MP4, TXT) |

Timestamps are UTC in format `YYYYMMDD_HHMMSSz`.

---

## Build and install steps

```bash
# Build only
cd /git/service_switcher
go build .
# Output: ./service_switcher binary

# Full install (requires root)
sudo bash install.sh
# Installs to /opt/service_switcher/, enables service-switcher.service
```

---

## Evidence

- [install.sh](../../install.sh)
- [go.mod](../../go.mod)
- Directory listing verified from workspace structure
