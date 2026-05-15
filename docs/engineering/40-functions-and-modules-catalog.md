# Functions and Modules Catalog

**Audience:** Maintainers, contributors  
**Last updated:** 2026-05-15

---

## Source file: `main.go`

Single-file Go application. All types, interfaces, and functions are defined here.

---

### Types

#### `Config`

```go
type Config struct {
    CommandListenAddress string            `json:"command_listen_address"`
    StatusListenAddress  string            `json:"status_listen_address"`
    Services             map[string]string `json:"services"`
}
```

Loaded from `services.json`. Maps logical service names to systemd unit file paths.

---

#### `Status`

```go
type Status struct {
    Healthy       bool      `json:"healthy"`
    LastActivated string    `json:"last_activated"`
    ActiveTask    bool      `json:"active_task"`
    TaskStartedAt time.Time `json:"task_started_at,omitempty"`
    TaskDoneAt    time.Time `json:"task_done_at,omitempty"`
    PendingSwitch string    `json:"pending_switch,omitempty"`
}
```

Serialized to JSON and written to every status port connection.

---

#### `Server`

```go
type Server struct {
    config        Config
    starter       ServiceStarter
    mu            sync.RWMutex
    lastActivated string
    activeTask    bool
    taskStartedAt time.Time
    taskDoneAt    time.Time
    pendingSwitch string
}
```

Holds all mutable runtime state. The `mu` mutex guards `lastActivated`, `activeTask`, `taskStartedAt`, `taskDoneAt`, and `pendingSwitch`.

---

#### `ServiceStarter` (interface)

```go
type ServiceStarter interface {
    Start(context.Context, string) error
}
```

Allows the real systemctl implementation (`SystemctlStarter`) to be replaced with a test double. Used in `main_test.go`.

---

#### `SystemctlStarter`

```go
type SystemctlStarter struct{}

func (SystemctlStarter) Start(ctx context.Context, unit string) error
```

Runs `systemctl start -- <unit>` as a subprocess. Returns an error if the command exits non-zero; includes combined stdout/stderr in the error message.

---

### Functions

#### `main()`

Entry point. Parses `-config` flag (default `services.json`), calls `loadConfig`, constructs `Server`, installs signal handlers, calls `server.run(ctx)`.

---

#### `loadConfig(path string) (Config, error)`

Reads and JSON-parses the config file. Validates:
- At least one service is defined.
- No service name is empty or whitespace.
- Every service location passes `normalizeUnit()`.
- Fills in default addresses if omitted.

Returns an error if any validation fails.

---

#### `normalizeUnit(location string) (string, error)`

Extracts `filepath.Base(location)` from a systemd unit file path. Validates:
- Not empty or whitespace.
- Base component is not `.` or `/`.
- Ends with `.service`.

Used both during config load (validation) and during command handling (deriving the unit name to pass to systemctl).

---

#### `(s *Server) run(ctx context.Context) error`

Opens both TCP listeners, starts `serveCommands` and `serveStatus` goroutines, waits for context cancellation or a listener error.

---

#### `(s *Server) serveCommands(ctx context.Context, listener net.Listener, errCh chan<- error)`

Accepts connections in a loop. Each connection is handled in a new goroutine via `handleCommandConnection`. Exits on context cancellation.

---

#### `(s *Server) serveStatus(ctx context.Context, listener net.Listener, errCh chan<- error)`

Accepts connections in a loop. Each connection is handled in a new goroutine via `handleStatusConnection`. Exits on context cancellation.

---

#### `(s *Server) handleCommandConnection(ctx context.Context, conn net.Conn)`

Per-connection handler for port 20100:
1. Sets 5-second read deadline.
2. Reads up to `maxCommandBytes` (1024) via `bufio.Reader`.
3. Calls `handleCommand(ctx, command)`.
4. Writes `ok\n` / `busy\n` / `error\n` to the connection.

---

#### `(s *Server) handleCommand(ctx context.Context, command string) (string, error)`

Core dispatch logic:
1. Tokenizes and validates: must be exactly `["start", "<name>"]`.
2. Looks up `<name>` in `config.Services`.
3. Acquires mutex — checks `activeTask`:
   - If active: sets `pendingSwitch` (if not already set), returns `"busy\n"`.
   - Else: sets `activeTask = true`, records `taskStartedAt`.
4. Calls `normalizeUnit`, then `starter.Start(ctx, unit)`.
5. Releases mutex — clears `activeTask`, sets `taskDoneAt`, sets `lastActivated`.
6. If `pendingSwitch` was set, triggers it recursively.
7. Returns `"ok\n"` on success or `""` + error on failure.

---

#### `(s *Server) handleStatusConnection(conn net.Conn)`

Serializes the current `Status` struct to JSON and writes it to the connection.

---

### Constants

| Constant | Value | Purpose |
|---|---|---|
| `defaultCommandListenAddress` | `"0.0.0.0:20100"` | Default if `command_listen_address` is absent from config |
| `defaultStatusListenAddress` | `"0.0.0.0:30100"` | Default if `status_listen_address` is absent from config |
| `maxCommandBytes` | `1024` | Maximum bytes read from a command connection |

---

## Test file: `main_test.go`

Uses a mock `ServiceStarter` implementation to test `handleCommand` and `loadConfig` without invoking real systemctl. Evidence: [main_test.go](../../main_test.go).

---

## Test scripts (`test/`)

| File | Language | Purpose |
|---|---|---|
| `lan_workload_test.py` | Python 3 | End-to-end quality and latency test harness for all 24 services |
| `lan_workload_test_config.json` | JSON | Per-service endpoint URLs, payloads, and timeouts |
| `lan_service_tester.py` | Python 3 | Simpler portable tester; hardcoded endpoints |
| `lan_service_benchmark.py` | Python 3 | Timing benchmark harness with Wake-on-LAN support |
| `lan_benchmark_config.json` | JSON | Benchmark configuration |
| `probe_api.py` | Python 3 | One-shot OpenAPI schema probe for the currently running service |
| `LAN_WORKLOAD_TEST.md` | Markdown | Full reference documentation for the workload test harness |

---

## Evidence

- [main.go](../../main.go) — all functions above
- [main_test.go](../../main_test.go) — test coverage
