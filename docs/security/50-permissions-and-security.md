# Permissions and Security Model

**Audience:** Security reviewers, ops  
**Last updated:** 2026-05-15

---

## 1. Authentication and authorization

**No authentication is implemented on any port.**

| Port | Auth | Notes |
|---|---|---|
| 20100/TCP (command) | None | Any host that can reach the port can start any service |
| 30100/TCP (status) | None | Status JSON is readable by anyone |
| 30000/TCP (service HTTP) | None | All inference endpoints are unauthenticated |

**Implication:** The node must only be reachable from a trusted network (LAN segment, VLAN, or VPN). Expose to untrusted networks only behind an authenticated reverse proxy.

---

## 2. Privilege level

The service-switcher process runs as the user defined in `service-switcher.service`. The default unit file does not specify `User=`, so it runs as **root** under systemd. This is required because `systemctl start` for system units requires root or polkit authorization.

**Risk:** A process running as root with a world-accessible TCP socket is a high-privilege attack surface. See Section 7 for mitigations.

---

## 3. Input validation

`handleCommand()` in `main.go` validates:

- The command must split into exactly two tokens.
- The first token must be the literal string `start`.
- The second token must match a key in the in-memory service registry (`config.Services`).
- The resolved path must pass `normalizeUnit()`: non-empty, base component not `.` or `/`, must end with `.service`.

**Command injection:** The unit name is passed as a positional argument to `exec.CommandContext(ctx, "systemctl", "start", "--", unit)`. The `--` separator prevents the unit name from being interpreted as a flag. The unit name is derived solely from a pre-validated config file path, not from raw user input, so command injection via the TCP socket is not possible.

**Max read:** Incoming command bytes are capped at `maxCommandBytes = 1024` via `io.LimitReader`. This prevents oversized input attacks.

**Read deadline:** A 5-second read deadline prevents slow-loris style connection exhaustion.

---

## 4. Secrets and credentials

No secrets, tokens, API keys, or passwords are present in the switcher codebase or configuration files. The `services.json` config contains only service names and systemd unit file paths — no sensitive values.

---

## 5. Network exposure

The default config binds to `0.0.0.0` on all interfaces for both ports 20100 and 30100. The service workload HTTP endpoint on port 30000 is bound by the individual service, not the switcher.

| Port | Bound address | Risk |
|---|---|---|
| 20100 | `0.0.0.0` | Reachable on all interfaces — restrict via firewall to trusted sources |
| 30100 | `0.0.0.0` | Same |
| 30000 | Per-service config | Not verified from this repository |

---

## 6. systemd unit (service-switcher.service)

```ini
[Service]
Type=simple
WorkingDirectory=/opt/service_switcher
ExecStart=/opt/service_switcher/service_switcher -config /opt/service_switcher/services.json
Restart=always
RestartSec=2
```

Notable absences:
- No `User=` or `Group=` — runs as root
- No `NoNewPrivileges=`
- No `ProtectSystem=`, `ProtectHome=`, `ReadOnlyPaths=`
- No `RestrictAddressFamilies=`
- No `CapabilityBoundingSet=`

See gap analysis ([80-best-practices-gap-analysis.md](../leadership/80-best-practices-gap-analysis.md)) for hardening recommendations.

---

## 7. Attack surface summary

| Vector | Risk | Current control | Recommendation |
|---|---|---|---|
| Unauthorized service switching via TCP 20100 | High — can start any service, change GPU load | None | Firewall to trusted IPs; add token auth |
| Information disclosure via TCP 30100 | Low — reveals which service is active | None | Firewall to trusted IPs |
| Unauthenticated inference via HTTP 30000 | High — unrestricted model access, GPU exhaustion | None | Reverse proxy with auth; rate limiting |
| Root process with open TCP socket | Critical — root code execution if vulnerabilities exist | Input validation, size limits, deadline | systemd sandboxing, drop to non-root |

---

## 8. File permissions

Default `install.sh` sets:

| Path | Mode | Notes |
|---|---|---|
| `/opt/service_switcher/` | `0755` | Directory |
| `/opt/service_switcher/service_switcher` | binary (no explicit mode) | Should be `0750` or `0755` |
| `/opt/service_switcher/services.json` | `0644` | Config readable by all; no secrets in it |
| `/etc/systemd/system/service-switcher.service` | `0644` | Standard systemd unit permissions |

---

## Evidence

- [main.go](../../main.go) — `handleCommand`, `handleCommandConnection`, `loadConfig`, `normalizeUnit`
- [service-switcher.service](../../service-switcher.service) — unit file
- [install.sh](../../install.sh) — install permissions

---

## Open questions / not verified

- Whether individual AI service units (`image-sdxl.service` etc.) run as non-root or with sandboxing — unit files not present in this repository
- Whether port 30000 binds to `0.0.0.0` or `127.0.0.1` for individual services — not verified
- Firewall/iptables rules on the node — not verifiable from repository
