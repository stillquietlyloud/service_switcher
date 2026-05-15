# Architecture and Logic

**Audience:** Engineers, maintainers  
**Last updated:** 2026-05-15

---

## 1. System overview

```
┌─────────────────── LAN client ──────────────────────┐
│                                                      │
│  1. TCP :20100  →  "start <service>\n"               │
│  2. TCP :30100  →  read status JSON                  │
│  3. HTTP :30000 →  POST /generate  /tts  /v1/...     │
│                                                      │
└───────────────────────────────────────────────────── ┘
                         │
              192.168.8.5 (AI node)
                         │
          ┌──────────────────────────┐
          │     service-switcher     │  Go binary
          │  /opt/service_switcher/  │  systemd unit: service-switcher.service
          │                          │
          │  command listener :20100 │  TCP, plain text
          │  status  listener :30100 │  TCP, JSON
          └──────────┬───────────────┘
                     │ systemctl start <unit>
          ┌──────────▼───────────────────────────────────┐
          │            systemd                           │
          │                                              │
          │  NVIDIA lane (one at a time)                 │
          │    image-flux / image-qwen / image-sdxl /    │
          │    image-sdxl-turbo / tts-* / video-*        │
          │                                              │
          │  AMD lane (one at a time)                    │
          │    llm-* / translator-*                      │
          │                                              │
          │  All services bind HTTP on :30000            │
          └──────────────────────────────────────────────┘
```

---

## 2. service-switcher

Written in Go. Source: [main.go](../../main.go).

### Startup

```
main()
  → loadConfig(services.json)        # parse JSON, validate service names and .service paths
  → Server.run(ctx)
      → net.Listen(tcp, :20100)      # command socket
      → net.Listen(tcp, :30100)      # status socket
      → go serveCommands(ctx, ...)
      → go serveStatus(ctx, ...)
```

### Command handling (port 20100)

Each accepted TCP connection:

1. Read deadline set to **5 seconds**.
2. Read up to `maxCommandBytes` (1024) with `bufio.Reader.ReadString('\n')`.
3. Parse: must be exactly `start <name>`.
4. Look up `<name>` in `config.Services`.
5. Acquire mutex:
   - If `activeTask == true` → reply `busy\n`, queue `pendingSwitch` (only one slot).
   - Else → set `activeTask = true`, record `taskStartedAt`.
6. Resolve unit name: `filepath.Base(location)`.
7. Run `systemctl start -- <unit>` via `exec.CommandContext`.
8. On completion: clear `activeTask`, set `taskDoneAt`, set `lastActivated`.
9. If `pendingSwitch` was set, trigger it immediately.
10. Reply `ok\n` or `error\n`.

### Status handling (port 30100)

Each accepted TCP connection:

1. Serialize `Status` struct to JSON (fields: `healthy`, `last_activated`, `active_task`, `task_started_at`, `task_done_at`, `pending_switch`).
2. Write JSON bytes and close connection.

`healthy` is always `true` in the current implementation (the switcher itself is running by definition).

---

## 3. GPU lanes and Conflicts=

All 24 services bind port 30000. Only one can be active at a time per lane. Mutual exclusion is enforced via systemd `Conflicts=` directives:

| Lane | Services | Cross-lane conflict |
|---|---|---|
| NVIDIA | image-*, tts-*, video-* | Declare `Conflicts=` against each other within the lane |
| AMD LLM | llm-* | Declare `Conflicts=` against other LLM and translator services |
| AMD Translator | translator-* | Declare `Conflicts=` against **all** services (full cross-lane coverage) |

**Result:** Starting any translator service stops everything else automatically. Starting an LLM after a NVIDIA service does **not** stop the NVIDIA service automatically — `service-stopper.service` is required for that transition.

---

## 4. service-stopper

A helper systemd service (not managed by the switcher itself) that stops services which don't self-stop via `Conflicts=` when crossing GPU lanes. Required for NVIDIA → LLM transitions and vice versa.

Check its status:

```bash
sudo systemctl status service-stopper.service
```

---

## 5. Data flow for a single inference call

```
Client                     switcher(:20100)         systemd          service(:30000)
  │                              │                     │                    │
  │── "start image-sdxl\n" ────▶│                     │                    │
  │◀── "ok\n" ──────────────────│                     │                    │
  │                              │── systemctl start ─▶│                    │
  │                              │                     │── spawn process ──▶│
  │── GET /health ─────────────────────────────────────────────────────────▶│
  │◀── 200 {"status":"ok"} ──────────────────────────────────────────────── │
  │── POST /generate ──────────────────────────────────────────────────────▶│
  │◀── 200  raw PNG bytes ────────────────────────────────────────────────── │
```

---

## 6. Config resolution

`services.json` maps logical names to systemd unit file paths:

```json
{
  "command_listen_address": "0.0.0.0:20100",
  "status_listen_address": "0.0.0.0:30100",
  "services": {
    "image-sdxl": "/etc/systemd/system/image-sdxl.service"
  }
}
```

`normalizeUnit()` extracts `filepath.Base(path)` → `image-sdxl.service`. The switcher calls `systemctl start image-sdxl.service`.

---

## 7. Graceful shutdown

The Go process traps `SIGINT` / `SIGTERM` via `signal.NotifyContext`. Both listeners are closed; in-progress `systemctl start` calls run to completion or are cancelled by the context deadline.

---

## Evidence

- [main.go](../../main.go) lines 1–300+
- [services.json](../../services.json)
- [service-switcher.service](../../service-switcher.service)
- [test/LAN_WORKLOAD_TEST.md](../../test/LAN_WORKLOAD_TEST.md) Section 11 (Conflicts= table)

---

## Open questions / not verified

- Exact `Conflicts=` lines inside individual service unit files — not read directly
- service-stopper.service implementation — not present in this repository
- Whether `healthy` in status JSON ever returns `false` — not implemented in current code
