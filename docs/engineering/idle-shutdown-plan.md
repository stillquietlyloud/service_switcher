# Plan: Integrated Idle Shutdown in service-switcher (v2 — Hybrid Lock + Hardware)

**Status:** Proposed — not yet implemented  
**Date:** 2026-05-16  
**Replaces:** `service-stopper.service` + `auto-shutdown.service`  
**Revision:** v1 (TCP-only) → v2 (Lock file + TCP drain + hardware fallback)

---

## 1. Problem Statement

The original v1 plan used only TCP connection probing as the activity signal. This handles the common case well but leaves a gap: what if a service is started, loads its model (long, no TCP connections yet), or hangs mid-inference with a stalled connection? The host stays on indefinitely.

The v2 hybrid design adds two layers on top of TCP probing:

1. **A lock file** — set by the switcher when a service is requested, cleared when the TCP drain is confirmed. Makes activity state explicit, durable (visible to ops), and independent of in-memory state.
2. **Hardware polling as a final gate** — GPU/CPU utilization is sampled 5 times before any poweroff is allowed. This is the last line of defense. Nothing gets shut down while hardware is actually working.

The combination gives three independent signals that must all agree before poweroff happens.

---

## 2. Critical Design Clarification: Who Manages the Lock?

The user's proposal mentions "egress POST response deletes the lock file." This requires the AI services to explicitly delete the lock, which means modifying each service — undesirable.

**The switcher manages the lock file entirely on its own**, using TCP connection state as the proxy for "response has been sent":

- **Lock created**: when `start <service>` command is received.
- **Lock refreshed** (timestamp updated): every 30s while TCP connections are detected on the service port — meaning an inference is actively in flight.
- **Lock deleted**: when the TCP probe finds zero connections AND a configurable drain grace period (2 min default) has elapsed since the last observed connection. This is the proxy for "the response was sent and the client disconnected."

No changes to any AI service are required.

---

## 3. State Machine

The idle watcher runs on a 30-second tick and evaluates this state machine:

```
START
  │
  ▼
[BOOT] ──── service switch received ────────────────────────────────────────┐
                                                                             │
                                                                             ▼
                                                                    [LOCK CREATED]
                                                                    lock file written
                                                                    lastActivity = now
                                                                             │
                              ┌──────────────────────────────────────────────┘
                              │
                              ▼  (every 30s tick)
                    ┌─────────────────────────┐
                    │  TCP connections > 0?   │
                    └─────────────────────────┘
                          │           │
                         YES          NO
                          │           │
                          ▼           ▼
                   refresh lock    has TCP been zero for
                   lastActivity     > drain_grace (2min)?
                   = now                │
                                       YES → delete lock
                                        │
                                        ▼
                              ┌──────────────────────────┐
                              │  no lock file AND        │
                              │  idle > idle_timeout?    │
                              │  (15 min)                │
                              └──────────────────────────┘
                                        │
                                       YES
                                        │
                                        ▼
                              ┌──────────────────────────┐
                              │  lock file present AND   │
                              │  lock age > idle_timeout?│
                              │  (stale = hung service)  │
                              └──────────────────────────┘
                            EITHER PATH LEADS TO:
                                        │
                                        ▼
                              ┌──────────────────────────┐
                              │   HARDWARE POLL GATE     │
                              │   5 polls × 60s          │
                              │   GPU util + CPU util    │
                              └──────────────────────────┘
                                        │
                              all 5 below threshold?
                                YES           NO
                                 │             │
                                 ▼             ▼
                           POWEROFF       reset clocks,
                                          log "hardware
                                          active, abort"
```

Two separate entry points lead to the hardware poll gate:
- **Path A (normal idle)**: no lock file, idle timer expired → hardware gate → poweroff
- **Path B (stale lock)**: lock file exists but is older than idle_timeout with no TCP activity → hardware gate → poweroff

Path B is the hung service safety net: the service started, consumed GPU, but never finished. The hardware poll distinguishes "GPU actually computing but slowly" (abort) from "GPU idle, service just leaked a lock" (poweroff).

---

## 4. Lock File

**Location:** `/run/service-switcher/active.lock`

`/run` is a tmpfs (RAM-backed) mount on all systemd hosts. It is:
- Cleared automatically on reboot — no stale lock survives a power cycle.
- Fast to write (no disk I/O).
- Not backed up or replicated — correct behavior.

**File contents:** a single line of JSON for observability:

```json
{"service": "llm-qwen327b", "started_at": "2026-05-16T10:00:00Z", "last_tcp_seen": "2026-05-16T10:04:30Z"}
```

This makes `cat /run/service-switcher/active.lock` immediately useful during ops debugging.

---

## 5. Hardware Poll Gate

### GPU Detection (multi-vendor)

This host runs both AMD and NVIDIA GPUs. The probe must handle both.

**AMD (for llm-*, translator-*):**
```
/sys/class/drm/card*/device/gpu_busy_percent
```
This sysfs file is provided by the `amdgpu` kernel driver with no external tools required. Read one or more files, take the maximum value.

**NVIDIA (for image-*, tts-*, video-*):**
```
nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader,nounits
```
Returns one integer per GPU line. Take the maximum.

**Fallback order:**
1. Try AMD sysfs path (no subprocess, fastest).
2. Try `nvidia-smi` subprocess.
3. If both fail (driver not loaded, tools missing): log a warning and **conservatively return "active"** — meaning no poweroff. This prevents a false shutdown when GPU detection itself is broken.

**CPU Detection:**

Read `/proc/stat`, compute total CPU usage across two samples 1 second apart. This requires no external tools.

Threshold: CPU > 20% is considered "active" (conservative — model serving at rest idles well below this).

### Poll Sequence

```go
func (s *Server) hardwarePollGate() bool {
    // Returns true if it is SAFE to poweroff (hardware idle confirmed).
    threshold := s.config.HardwareIdleThresholdPercent  // default 5
    pollCount := s.config.HardwarePollCount             // default 5
    pollInterval := 60 * time.Second

    idle := 0
    for i := 0; i < pollCount; i++ {
        gpuUtil := readGPUUtilization()   // AMD sysfs + nvidia-smi, max of all GPUs
        cpuUtil := readCPUUtilization()   // /proc/stat two-sample
        if gpuUtil <= threshold && cpuUtil <= threshold {
            idle++
            log.Printf("hw-poll %d/%d: GPU=%d%% CPU=%d%% → idle", i+1, pollCount, gpuUtil, cpuUtil)
        } else {
            log.Printf("hw-poll %d/%d: GPU=%d%% CPU=%d%% → active, aborting shutdown", i+1, pollCount, gpuUtil, cpuUtil)
            return false  // fail fast on first active poll — no need to wait all 5
        }
        if i < pollCount-1 {
            time.Sleep(pollInterval)
        }
    }
    return idle == pollCount
}
```

**Total hardware gate time in the worst case: 5 × 60s = 5 minutes.** This is a deliberate delay — it provides a final human intervention window. If an operator is watching logs and sees the hardware poll sequence starting, they have 5 minutes to send a new `start <service>` command to cancel.

The `start <service>` command resets state at any point, including during the hardware poll sequence. The watcher goroutine checks for this before each poll.

---

## 6. Config Changes (backward-compatible)

All AI services on this host bind on the same port (`:30000`), since only one is ever active at a time. There is no need for a per-service port map — a single `service_port` integer replaces it.

```json
{
  "command_listen_address": "0.0.0.0:20100",
  "status_listen_address": "0.0.0.0:30100",

  "idle_shutdown_minutes": 15,
  "idle_drain_grace_minutes": 2,
  "hardware_idle_threshold_percent": 5,
  "hardware_poll_count": 5,
  "service_port": 30000,

  "services": { ... }
}
```

**New fields:**

| Field | Default | Meaning |
|---|---|---|
| `idle_shutdown_minutes` | `0` (disabled) | Minutes with no lock file before hardware poll gate runs |
| `idle_drain_grace_minutes` | `2` | Minutes after last TCP connection before lock is cleared |
| `hardware_idle_threshold_percent` | `5` | GPU/CPU % below which a single poll is counted as idle |
| `hardware_poll_count` | `5` | Number of consecutive idle polls required before poweroff |
| `service_port` | `0` (probe disabled) | Port that the active service listens on; TCP probe skipped if 0 |

All fields optional. Feature is disabled by default (`idle_shutdown_minutes: 0`).

---

## 7. Server Struct Changes

```go
type Config struct {
    CommandListenAddress          string            `json:"command_listen_address"`
    StatusListenAddress           string            `json:"status_listen_address"`
    IdleShutdownMinutes           int               `json:"idle_shutdown_minutes"`
    IdleDrainGraceMinutes         int               `json:"idle_drain_grace_minutes"`
    HardwareIdleThresholdPercent  int               `json:"hardware_idle_threshold_percent"`
    HardwarePollCount             int               `json:"hardware_poll_count"`
    ServicePort                   int               `json:"service_port"`
    Services                      map[string]string `json:"services"`
}

type Server struct {
    config        Config
    starter       ServiceStarter
    mu            sync.RWMutex
    lastActivated string
    activeTask    bool
    taskStartedAt time.Time
    taskDoneAt    time.Time
    pendingSwitch string

    // NEW — idle shutdown state
    lastActivityAt   time.Time  // last command received (mutex-protected)
    lastTCPSeenAt    time.Time  // last time TCP probe found connections (mutex-protected)
    lockFilePath     string     // resolved on startup: /run/service-switcher/active.lock
}
```

---

## 8. Lock File Lifecycle in Code

```go
// Called from handleCommand, before existing task logic:
func (s *Server) onCommandReceived(svc string) {
    s.mu.Lock()
    s.lastActivityAt = time.Now()
    s.mu.Unlock()
    s.writeLock(svc)
}

func (s *Server) writeLock(svc string) {
    os.MkdirAll(filepath.Dir(s.lockFilePath), 0o700)
    data, _ := json.Marshal(map[string]string{
        "service":       svc,
        "started_at":    time.Now().UTC().Format(time.RFC3339),
        "last_tcp_seen": "",
    })
    os.WriteFile(s.lockFilePath, data, 0o600)
}

func (s *Server) refreshLock(lastTCPSeen time.Time) {
    // Overwrite with updated last_tcp_seen timestamp.
    // Read current, update field, rewrite atomically via temp file + rename.
}

func (s *Server) deleteLock() {
    os.Remove(s.lockFilePath)
}
```

Atomic write (temp file + rename) is used for `refreshLock` to avoid a partial read if the status port reads the file concurrently.

---

## 9. Idle Watcher Goroutine (revised)

```go
func (s *Server) idleWatcher(ctx context.Context) {
    idleTimeout    := time.Duration(s.config.IdleShutdownMinutes) * time.Minute
    drainGrace     := time.Duration(s.config.IdleDrainGraceMinutes) * time.Minute
    ticker         := time.NewTicker(30 * time.Second)
    defer ticker.Stop()

    for {
        select {
        case <-ctx.Done():
            return
        case <-ticker.C:
            s.mu.RLock()
            svc          := s.lastActivated
            lastActivity := s.lastActivityAt
            s.mu.RUnlock()

            lockExists := s.lockFileExists()
            lockAge    := s.lockFileAge()   // time.Since(lock mtime)

            // --- TCP probe: refresh or clear lock ---
            if port := s.config.ServicePort; port > 0 {
                _ = svc  // port is shared by all services
                if probeHasConnections(port) {
                    s.mu.Lock()
                    s.lastTCPSeenAt = time.Now()
                    s.mu.Unlock()
                    s.refreshLock(time.Now())
                    continue  // active — nothing more to do this tick
                }
            }

            // No TCP connections this tick.
            s.mu.RLock()
            lastTCP := s.lastTCPSeenAt
            s.mu.RUnlock()

            // Clear lock if drain grace has passed since last TCP connection.
            if lockExists && !lastTCP.IsZero() && time.Since(lastTCP) >= drainGrace {
                log.Printf("idle-watcher: drain grace elapsed, clearing lock")
                s.deleteLock()
                lockExists = false
            }

            // --- Path A: no lock, idle timer expired ---
            if !lockExists && time.Since(lastActivity) >= idleTimeout {
                log.Printf("idle-watcher: %.0f min idle, no lock — entering hardware poll gate", idleTimeout.Minutes())
                if s.hardwarePollGate(ctx) {
                    s.triggerShutdown()
                    return
                }
                // hardware active: reset activity clock so we don't immediately retry
                s.mu.Lock()
                s.lastActivityAt = time.Now()
                s.mu.Unlock()
            }

            // --- Path B: stale lock (hung service), idle timer expired ---
            if lockExists && lockAge >= idleTimeout {
                log.Printf("idle-watcher: lock is %.0f min old with no TCP — stale lock, entering hardware poll gate", lockAge.Minutes())
                if s.hardwarePollGate(ctx) {
                    s.triggerShutdown()
                    return
                }
                // hardware active: refresh lock mtime so we don't immediately retry
                s.refreshLock(time.Now())
            }
        }
    }
}
```

---

## 10. Status API Changes

```go
type Status struct {
    Healthy        bool      `json:"healthy"`
    LastActivated  string    `json:"last_activated"`
    ActiveTask     bool      `json:"active_task"`
    TaskStartedAt  time.Time `json:"task_started_at,omitempty"`
    TaskDoneAt     time.Time `json:"task_done_at,omitempty"`
    PendingSwitch  string    `json:"pending_switch,omitempty"`

    // NEW
    LastActivityAt  time.Time `json:"last_activity_at,omitempty"`
    LastTCPSeenAt   time.Time `json:"last_tcp_seen_at,omitempty"`
    LockActive      bool      `json:"lock_active"`
    ShutdownAfter   time.Time `json:"shutdown_after,omitempty"`  // projected; zero if disabled
    IdleSeconds     float64   `json:"idle_seconds,omitempty"`
}
```

Example response:

```json
{
  "healthy": true,
  "last_activated": "llm-qwen327b",
  "active_task": false,
  "last_activity_at": "2026-05-16T10:00:00Z",
  "last_tcp_seen_at": "2026-05-16T10:03:47Z",
  "lock_active": false,
  "shutdown_after": "2026-05-16T10:18:47Z",
  "idle_seconds": 183.0
}
```

When `lock_active: true`, it means an inference is considered in-flight. When `lock_active: false`, the idle countdown is running. `shutdown_after` is projected from `last_tcp_seen_at + drain_grace + idle_timeout` for observability.

---

## 11. What Replaces What

| Old component | Behavior | Replaced by |
|---|---|---|
| `service-stopper.service` | Polls GPU util every 60s; stops all AI services if < 5% for 5 min | Hardware poll gate (Path A + B): runs only after idle period confirmed, not continuously |
| `auto-shutdown.service` | Watches for all AI services inactive; shuts down if none activate | Idle watcher Path A: no lock + idle timer expired → poweroff |

Improvements over the old system:
- GPU polling runs **only when shutdown is already being considered**, not constantly every 60s. Less noise, less overhead.
- The lock file explicitly captures "something was requested" independent of TCP state, handling model load time (which can be 2–5 minutes with no connections yet).
- Path B catches hung services that the old system would have missed (GPU idle but service never responded — lock stays, stale lock triggers hardware check anyway).

---

## 12. Edge Cases and Mitigations

| Scenario | Outcome |
|---|---|
| Service takes 5 min to load model before first connection | Lock file was created on `start` command → idle timer does NOT run → no spurious shutdown during load |
| Inference takes 12 min (large video generation) | TCP connections present during entire inference → lock refreshed every 30s → idle timer resets |
| Service hangs mid-inference, connection stalls with no data | TCP probe may still see "established" state → lock refreshed → no shutdown. If connection eventually closes, drain grace starts. |
| Service crashes and no more connections | Drain grace elapses → lock cleared → idle timer starts → 15 min later, hardware gate → poweroff |
| Operator sends `start <service>` while hardware poll gate is running | Command handler calls `onCommandReceived` → creates new lock → watcher checks `lockFileExists()` before each poll → aborts poweroff path |
| `/run/service-switcher/` doesn't exist on first run | `writeLock` calls `os.MkdirAll` — directory created on first command |
| Lock file left from previous run (shouldn't happen — /run is tmpfs) | `active.lock` in `/run` is cleared on every boot. Not a concern. |
| GPU detection fails (driver not loaded, nvidia-smi missing) | `readGPUUtilization()` returns a sentinel `"unknown"` value and the gate returns **false (do not shutdown)**. Conservative. |
| Both AMD and NVIDIA GPUs present | AMD sysfs + nvidia-smi are both read; maximum value across all GPUs is used |

---

## 13. Implementation Steps

1. **Extend `Config` struct** with 4 new fields; set defaults in `loadConfig` when zero.
2. **Add new fields to `Server`** struct: `lastActivityAt`, `lastTCPSeenAt`, `lockFilePath`.
3. **Implement `writeLock`, `refreshLock`, `deleteLock`, `lockFileExists`, `lockFileAge`** — ~40 lines, atomic write for refresh.
4. **Implement `probeHasConnections(port int) bool`** — using `ss`.
5. **Implement `readGPUUtilization() int`** — AMD sysfs glob + nvidia-smi fallback; returns max across all devices.
6. **Implement `readCPUUtilization() int`** — two `/proc/stat` samples, 1s apart.
7. **Implement `hardwarePollGate(ctx context.Context) bool`** — 5 polls × 60s, fail-fast on any active poll, abort if new command received.
8. **Implement `idleWatcher(ctx context.Context)`** — 30s tick, state machine as above.
9. **Implement `triggerShutdown()`** — log + `systemctl poweroff`.
10. **Call `onCommandReceived(svc)` from `handleCommand`** — single call before existing logic.
11. **Launch `idleWatcher` from `run()`** — gated on `IdleShutdownMinutes > 0`.
12. **Extend `Status` struct and `handleStatusConnection`**.
13. **Update `services.json`** with new fields and full `service_ports` map.
14. **Update `main_test.go`** — mock GPU/lock/TCP paths, test Path A and Path B separately.
15. **Test with `idle_shutdown_minutes: 1`, `hardware_poll_count: 2`, `hardware_poll_interval_seconds: 5`** on non-production window.
16. **Disable** `service-stopper.service` and `auto-shutdown.service` after validation.

---

## 14. Risk Analysis

| Risk | Severity | Mitigation |
|---|---|---|
| Spurious poweroff during long inference | HIGH | Lock refreshed every 30s while TCP connections exist; 15-min window is wide |
| Spurious poweroff during model load (no TCP yet) | HIGH | Lock file created at `start` command — idle timer never starts during load |
| Hung service keeps host on indefinitely | MEDIUM | Stale lock path (Path B): lock > 15 min + no TCP → hardware gate → poweroff if idle |
| GPU detection broken, no poweroff ever | LOW | Fail-open is conservative. Log warning on each failed probe so operators notice. |
| GPU detection broken, false idle reading | LOW | AMD sysfs + nvidia-smi cross-checked; both fail independently. Single point of failure unlikely. |
| Lock file stale across reboot | NONE | `/run` is tmpfs — cleared on every boot. |
| `ss` not available | LOW | Startup check with fatal log if missing. |
| `systemctl poweroff` permission | LOW | `service-switcher` already runs as root. Same permission level. |
| Hardware poll blocks for 5 min | LOW | Expected. It is intentional — human intervention window. New command aborts it. |

---

## 15. Files Changed (when implemented)

| File | Change type |
|---|---|
| `main.go` | +~120 lines: 8 new functions, 2 extended structs |
| `services.json` | Add 4 new config fields and full `service_ports` map |
| `main_test.go` | New tests for Path A, Path B, hardware gate abort, lock lifecycle |
| `README.md` | Document new config fields, lock file location, idle shutdown behavior |
| `service-stopper.service` | **Disable after validation** |
| `auto-shutdown.service` | **Disable after validation** |

Total new code in `main.go`: approximately 120 lines. No existing logic modified.
