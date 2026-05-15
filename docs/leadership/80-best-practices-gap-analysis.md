# Best-Practices Gap Analysis and Recommendations

**Audience:** Tech lead, engineering leadership  
**Last updated:** 2026-05-15

---

## Summary

The service-switcher is well-suited to its role as a minimal LAN-only coordinator. The core logic is correct, safe from injection, and operationally simple. The primary gaps are in **security hardening** (no auth, root process), **observability** (no metrics, no structured logging), and **resilience** (no health check feedback loop, single-slot queue).

---

## 1. Security

### 1a. No authentication on any port — **Critical**

**Current state:** Ports 20100, 30100, and 30000 accept connections from any IP with no credentials required.

**Risk:** Anyone with network access can activate any service, read system state, and make unlimited inference requests. On an open LAN this is a significant abuse vector.

**Recommendations (prioritized):**

| Priority | Action |
|---|---|
| P0 | Restrict ports 20100 and 30100 to specific source IPs via firewall (`iptables`/`nftables`). |
| P1 | Add a shared-secret token to the command protocol (e.g. `start <token> <service>\n`). |
| P2 | Place port 30000 behind an authenticating reverse proxy (nginx, Caddy) with at minimum HTTP Basic Auth. |

---

### 1b. Switcher runs as root — **High**

**Current state:** `service-switcher.service` has no `User=` directive; the process runs as root.

**Risk:** Any bug in the TCP parsing path (however unlikely) executes with full root privileges.

**Recommendations:**

```ini
# Add to service-switcher.service [Service] section
User=service-switcher
Group=service-switcher
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/opt/service_switcher
RestrictAddressFamilies=AF_INET AF_INET6
CapabilityBoundingSet=
AmbientCapabilities=
```

For `systemctl start` to work as a non-root user, use a polkit rule or a sudo wrapper.

---

### 1c. No TLS on any port — **Medium**

**Current state:** All communication is plaintext TCP and HTTP.

**Risk:** Traffic on the LAN can be observed and tampered with.

**Recommendation:** For a trusted LAN this is acceptable. If the node is accessible from broader network segments, add TLS via a reverse proxy for port 30000 and consider wrapping the TCP protocol in a TLS-capable proxy for ports 20100/30100.

---

## 2. systemd unit hardening — **High**

**Current state:** The service unit has no sandboxing directives.

**Recommended additions:**

```ini
[Service]
User=service-switcher
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
PrivateTmp=true
RestrictAddressFamilies=AF_INET AF_INET6
SystemCallFilter=@system-service
CapabilityBoundingSet=
```

Reference: [systemd exec security options](https://www.freedesktop.org/software/systemd/man/systemd.exec.html#Sandboxing)

---

## 3. Observability — **Medium**

### 3a. No structured logging

**Current state:** The switcher uses Go's `log` package with free-text output. No log level, no JSON format, no request IDs.

**Recommendation:** Add structured JSON logging with fields `service`, `unit`, `duration_ms`, `result`, `peer_addr`. This makes log aggregation (Loki, ELK) straightforward.

### 3b. No metrics

**Current state:** No Prometheus metrics, no counters for switches, errors, or latency.

**Recommendation:** Add a `/metrics` HTTP endpoint (standard `prometheus/client_golang`) exposing:
- `switcher_switches_total{service, result}` counter
- `switcher_switch_duration_seconds` histogram
- `switcher_active_task` gauge

### 3c. `healthy` is always `true`

**Current state:** The `Status.Healthy` field is hardcoded to `true`; it does not reflect whether the last started service is actually responding.

**Recommendation:** Optionally probe `http://localhost:30000/health` periodically and surface the result in `healthy`.

---

## 4. Resilience — **Medium**

### 4a. Single pending-switch slot

**Current state:** Only one switch can be queued. A second `start` command while busy drops the first queued request silently (the newer one overwrites it based on the `if s.pendingSwitch == ""` check).

Actually looking at the code: if `pendingSwitch` is already set, the new request is **rejected** (only the first queued switch is kept). The client receives `busy` and must retry.

**Recommendation:** Document this clearly at the protocol level (it is a feature, not a bug). Consider returning a structured reply (`{"status":"busy","queued":"image-sdxl"}`) instead of the bare string.

### 4b. No readiness feedback from the switcher itself

**Current state:** After `systemctl start` returns, the service may still be loading. The switcher returns `ok` immediately; the client must poll `/health` independently.

**Recommendation (optional):** Add an optional `wait_healthy` flag to the command protocol. When set, the switcher polls `/health` and only returns `ok` once the service is healthy. This makes the client integration simpler.

### 4c. `Restart=always` with 2-second delay

**Current state:** The unit restarts immediately on failure with a 2-second gap, which is appropriate. However, a crash loop could cause rapid systemd unit start storms.

**Recommendation:** Add `StartLimitIntervalSec=60` and `StartLimitBurst=5` to cap restart rate.

---

## 5. Protocol ergonomics — **Low**

**Current state:** The command protocol is bare text (`start <name>\n`). Responses are bare strings (`ok`, `busy`, `error`).

**Recommendation:** Consider a minimal JSON protocol for new clients:
```json
→ {"action": "start", "service": "image-sdxl"}
← {"status": "ok", "last_activated": "image-sdxl"}
← {"status": "busy", "pending": "image-sdxl"}
← {"status": "error", "message": "unknown service"}
```
This is backwards-incompatible; version with a flag or a new port.

---

## 6. TTS voice files — **Operational blocker**

**Current state:** All five TTS services fail with `404` until voice reference files are installed. There is no automated check or installer for these files.

**Recommendation:** Create an install script or Ansible task that downloads/copies speaker reference files and verifies `GET /voices` returns a non-empty list before marking the service as operational.

---

## 7. What is working well

- **Command injection prevention:** `--` separator and pre-validated service map make injection impossible.
- **Input size limits:** `io.LimitReader(conn, 1024)` and 5-second read deadline prevent resource exhaustion.
- **Graceful shutdown:** Signal handling and context propagation are correct.
- **Task coordination:** Single-slot queue prevents concurrent `systemctl start` calls from racing.
- **Config validation:** `normalizeUnit()` rejects malformed paths at startup, not at runtime.
- **Test coverage:** `main_test.go` uses interface injection; the core dispatch logic is testable without root.

---

## Evidence

- [main.go](../../main.go) — security and resilience patterns
- [service-switcher.service](../../service-switcher.service) — missing hardening directives
- [test/LAN_WORKLOAD_TEST.md](../../test/LAN_WORKLOAD_TEST.md) Section 12 — known deployment issues
- [security/50-permissions-and-security.md](../security/50-permissions-and-security.md)
