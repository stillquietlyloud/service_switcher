# AI Node Documentation — Index

**Node:** `192.168.8.5`  
**Last updated:** 2026-05-15  
**Audience:** All — see per-file audience headers for details

---

## What this node is

A single Linux host running 24 AI inference services managed by a lightweight TCP service switcher. Only one service runs at a time, sharing a single HTTP port (30000). Clients connect directly over LAN.

---

## Reading paths by role

| Role | Start here |
|---|---|
| New user / quick start | [30-api-endpoints-reference.md](integration/30-api-endpoints-reference.md) |
| Executive / leadership | [10-executive-summary.md](executives/10-executive-summary.md) |
| Engineer onboarding | [20-architecture-and-logic.md](engineering/20-architecture-and-logic.md) |
| Integration / client developer | [30-api-endpoints-reference.md](integration/30-api-endpoints-reference.md) |
| Ops / sysadmin | [60-operations-runbook.md](operations/60-operations-runbook.md) |
| Security reviewer | [50-permissions-and-security.md](security/50-permissions-and-security.md) |
| Maintainer / contributor | [40-functions-and-modules-catalog.md](engineering/40-functions-and-modules-catalog.md) · [70-paths-folders-and-assets.md](maintainers/70-paths-folders-and-assets.md) |
| Tech lead / gap analysis | [80-best-practices-gap-analysis.md](leadership/80-best-practices-gap-analysis.md) |

---

## Document list

| File | Title | Audience |
|---|---|---|
| [executives/10-executive-summary.md](executives/10-executive-summary.md) | Executive Summary | Leadership |
| [engineering/20-architecture-and-logic.md](engineering/20-architecture-and-logic.md) | Architecture and Logic | Engineering |
| [integration/30-api-endpoints-reference.md](integration/30-api-endpoints-reference.md) | API Endpoints Reference | Integration / all |
| [engineering/40-functions-and-modules-catalog.md](engineering/40-functions-and-modules-catalog.md) | Functions and Modules Catalog | Maintainers / engineers |
| [security/50-permissions-and-security.md](security/50-permissions-and-security.md) | Permissions and Security Model | Security |
| [operations/60-operations-runbook.md](operations/60-operations-runbook.md) | Operations Runbook | Ops / sysadmin |
| [maintainers/70-paths-folders-and-assets.md](maintainers/70-paths-folders-and-assets.md) | Paths, Folders, and Assets | Maintainers |
| [leadership/80-best-practices-gap-analysis.md](leadership/80-best-practices-gap-analysis.md) | Best-Practices Gap Analysis | Tech lead / leadership |

---

## Port summary (quick reference)

| Port | Protocol | Purpose |
|---|---|---|
| `20100/TCP` | Plain text | Switcher command socket — send `start <service>\n` |
| `30100/TCP` | JSON over TCP | Switcher status socket — read health/state JSON |
| `30000/TCP` | HTTP/1.1 | AI service workload, health, and schema endpoints |

---

## Evidence

- [main.go](../main.go) — switcher server source
- [services.json](../services.json) — service registry
- [service-switcher.service](../service-switcher.service) — systemd unit
- [test/lan_workload_test_config.json](../test/lan_workload_test_config.json) — full per-service endpoint config
- [test/LAN_WORKLOAD_TEST.md](../test/LAN_WORKLOAD_TEST.md) — harness reference
