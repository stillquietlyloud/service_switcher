package main

import (
	"bufio"
	"context"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"log"
	"net"
	"os"
	"os/exec"
	"os/signal"
	"path/filepath"
	"strings"
	"sync"
	"syscall"
	"time"
)

const (
	defaultCommandListenAddress = "0.0.0.0:20100"
	defaultStatusListenAddress  = "0.0.0.0:30100"
	maxCommandBytes             = 1024
	activeServiceFilePath       = "/var/log/service-switcher/active.txt"
)

type Config struct {
	CommandListenAddress         string            `json:"command_listen_address"`
	StatusListenAddress          string            `json:"status_listen_address"`
	IdleShutdownMinutes          int               `json:"idle_shutdown_minutes"`
	IdleDrainGraceMinutes        int               `json:"idle_drain_grace_minutes"`
	HardwareIdleThresholdPercent int               `json:"hardware_idle_threshold_percent"`
	HardwarePollCount            int               `json:"hardware_poll_count"`
	ServicePort                  int               `json:"service_port"`
	Services                     map[string]string `json:"services"`
}

type ServiceStarter interface {
	Start(context.Context, string) error
}

type SystemctlStarter struct{}

func (SystemctlStarter) Start(ctx context.Context, unit string) error {
	cmd := exec.CommandContext(ctx, "systemctl", "start", "--", unit)
	output, err := cmd.CombinedOutput()
	if err != nil {
		return fmt.Errorf("systemctl start %s: %w: %s", unit, err, strings.TrimSpace(string(output)))
	}

	return nil
}

type Server struct {
	config        Config
	starter       ServiceStarter
	mu            sync.RWMutex
	lastActivated string

	// Task coordination fields
	activeTask    bool      // true if a task is running
	taskStartedAt time.Time // when the current task started
	taskDoneAt    time.Time // when the last task completed
	pendingSwitch string    // if non-empty, a switch is queued

	// Idle shutdown state
	lastActivityAt time.Time // updated on command received (mutex-protected)
	lastTCPSeenAt  time.Time // last time TCP probe found connections (mutex-protected)
	lockFilePath   string    // e.g. /run/service-switcher/active.lock
}

type Status struct {
	Healthy        bool      `json:"healthy"`
	LastActivated  string    `json:"last_activated"`
	ActiveTask     bool      `json:"active_task"`
	TaskStartedAt  time.Time `json:"task_started_at,omitempty"`
	TaskDoneAt     time.Time `json:"task_done_at,omitempty"`
	PendingSwitch  string    `json:"pending_switch,omitempty"`
	LastActivityAt time.Time `json:"last_activity_at,omitempty"`
	LastTCPSeenAt  time.Time `json:"last_tcp_seen_at,omitempty"`
	LockActive     bool      `json:"lock_active"`
	ShutdownAfter  time.Time `json:"shutdown_after,omitempty"`
	IdleSeconds    float64   `json:"idle_seconds,omitempty"`
}

func main() {
	configPath := flag.String("config", "services.json", "path to services.json")
	flag.Parse()

	config, err := loadConfig(*configPath)
	if err != nil {
		log.Fatalf("load config: %v", err)
	}

	log.Printf("service-switcher starting, config: %s", *configPath)
	log.Printf("services configured: %v", len(config.Services))
	log.Printf("listening on command port: %s", config.CommandListenAddress)
	log.Printf("listening on status port: %s", config.StatusListenAddress)

	server := &Server{
		config:       config,
		starter:      SystemctlStarter{},
		lockFilePath: "/run/service-switcher/active.lock",
	}

	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()

	if err := server.run(ctx); err != nil && !errors.Is(err, context.Canceled) {
		log.Fatalf("run server: %v", err)
	}
}

func loadConfig(path string) (Config, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return Config{}, err
	}

	var config Config
	if err := json.Unmarshal(data, &config); err != nil {
		return Config{}, fmt.Errorf("parse config: %w", err)
	}

	if config.CommandListenAddress == "" {
		config.CommandListenAddress = defaultCommandListenAddress
	}

	if config.StatusListenAddress == "" {
		config.StatusListenAddress = defaultStatusListenAddress
	}

	if len(config.Services) == 0 {
		return Config{}, errors.New("config must define at least one service")
	}

	for name, location := range config.Services {
		if strings.TrimSpace(name) == "" {
			return Config{}, errors.New("service name cannot be empty")
		}

		if _, err := normalizeUnit(location); err != nil {
			return Config{}, fmt.Errorf("invalid service %q: %w", name, err)
		}
	}

	if config.IdleDrainGraceMinutes <= 0 {
		config.IdleDrainGraceMinutes = 2
	}
	if config.HardwareIdleThresholdPercent <= 0 {
		config.HardwareIdleThresholdPercent = 5
	}
	if config.HardwarePollCount <= 0 {
		config.HardwarePollCount = 5
	}

	return config, nil
}

func normalizeUnit(location string) (string, error) {
	trimmed := strings.TrimSpace(location)
	if trimmed == "" {
		return "", errors.New("service location cannot be empty")
	}

	unit := filepath.Base(trimmed)
	if unit == "." || unit == string(filepath.Separator) || unit == "" {
		return "", errors.New("service location must point to a unit")
	}

	if !strings.HasSuffix(unit, ".service") {
		return "", errors.New("service location must end with .service")
	}

	return unit, nil
}

func (s *Server) run(ctx context.Context) error {
	// Seed active.txt from an existing lock file so it survives restarts.
	if s.lockFilePath != "" {
		if data, err := os.ReadFile(s.lockFilePath); err == nil {
			var m map[string]string
			if json.Unmarshal(data, &m) == nil && m["service"] != "" {
				writeActiveFile(m["service"])
			}
		}
	}

	commandListener, err := net.Listen("tcp", s.config.CommandListenAddress)
	if err != nil {
		return fmt.Errorf("listen for commands: %w", err)
	}
	defer commandListener.Close()

	statusListener, err := net.Listen("tcp", s.config.StatusListenAddress)
	if err != nil {
		return fmt.Errorf("listen for status: %w", err)
	}
	defer statusListener.Close()

	if s.config.IdleShutdownMinutes > 0 {
		s.mu.Lock()
		s.lastActivityAt = time.Now()
		s.mu.Unlock()
		go s.idleWatcher(ctx)
		log.Printf("idle-shutdown enabled: %d minutes, service_port: %d",
			s.config.IdleShutdownMinutes, s.config.ServicePort)
	}

	errCh := make(chan error, 2)

	go s.serveCommands(ctx, commandListener, errCh)
	go s.serveStatus(ctx, statusListener, errCh)

	select {
	case <-ctx.Done():
		_ = commandListener.Close()
		_ = statusListener.Close()
		return ctx.Err()
	case err := <-errCh:
		if err != nil && !errors.Is(err, net.ErrClosed) {
			return err
		}
		return nil
	}
}

func (s *Server) serveCommands(ctx context.Context, listener net.Listener, errCh chan<- error) {
	for {
		conn, err := listener.Accept()
		if err != nil {
			select {
			case <-ctx.Done():
				return
			default:
				errCh <- err
				return
			}
		}

		go s.handleCommandConnection(ctx, conn)
	}
}

func (s *Server) serveStatus(ctx context.Context, listener net.Listener, errCh chan<- error) {
	for {
		conn, err := listener.Accept()
		if err != nil {
			select {
			case <-ctx.Done():
				return
			default:
				errCh <- err
				return
			}
		}

		go s.handleStatusConnection(conn)
	}
}

func (s *Server) handleCommandConnection(ctx context.Context, conn net.Conn) {
	defer conn.Close()

	// Set read deadline to prevent hanging indefinitely
	conn.SetReadDeadline(time.Now().Add(5 * time.Second))

	reader := bufio.NewReader(io.LimitReader(conn, maxCommandBytes))
	command, err := reader.ReadString('\n')
	if err != nil {
		if !errors.Is(err, io.EOF) && !errors.Is(err, context.DeadlineExceeded) {
			log.Printf("error reading command: %v", err)
			_, _ = io.WriteString(conn, "error\n")
			return
		}
		// If we got EOF without newline, that's okay - trim and process what we got
		if errors.Is(err, io.EOF) {
			// command already has partial data, will be trimmed below
			log.Printf("received EOF without newline, processing: %q", strings.TrimSpace(command))
		}
	}

	response, err := s.handleCommand(ctx, command)
	if err != nil {
		log.Printf("error handling command %q: %v", strings.TrimSpace(command), err)
		_, _ = io.WriteString(conn, "error\n")
		return
	}

	_, _ = io.WriteString(conn, response)
}

func (s *Server) handleCommand(ctx context.Context, command string) (string, error) {
       fields := strings.Fields(strings.TrimSpace(command))
       if len(fields) != 2 || fields[0] != "start" {
	       log.Printf("invalid command format: %q", strings.TrimSpace(command))
	       return "", errors.New("unsupported command")
       }

       name := fields[1]
       location, ok := s.config.Services[name]
       if !ok {
	       log.Printf("service not found in config: %q", name)
	       return "", errors.New("unknown service")
       }

       s.onCommandReceived(name)

       s.mu.Lock()
       if s.activeTask {
	       // If a task is running, queue the switch and reject this command
	       if s.pendingSwitch == "" {
		       s.pendingSwitch = name
		       log.Printf("task in progress, queued switch to %q", name)
	       } else {
		       log.Printf("task in progress, switch already queued to %q", s.pendingSwitch)
	       }
	       s.mu.Unlock()
	       return "busy\n", nil
       }
       // No active task, proceed
       s.activeTask = true
       s.taskStartedAt = time.Now()
       s.mu.Unlock()

       unit, err := normalizeUnit(location)
       if err != nil {
	       log.Printf("invalid unit path for service %q: %v", name, err)
	       s.mu.Lock()
	       s.activeTask = false
	       s.taskDoneAt = time.Now()
	       s.mu.Unlock()
	       return "", err
       }

       log.Printf("starting service: %q (unit: %q)", name, unit)
       err = s.starter.Start(ctx, unit)

       s.mu.Lock()
       s.lastActivated = name
       s.activeTask = false
       s.taskDoneAt = time.Now()
       // If a switch was queued during this task, start it now
       queued := s.pendingSwitch
       s.pendingSwitch = ""
       s.mu.Unlock()

       if err != nil {
	       log.Printf("failed to start service %q: %v", unit, err)
	       return "", err
       }

       log.Printf("successfully started service: %q", name)
       // If a switch was queued, trigger it in a goroutine
       if queued != "" && queued != name {
	       go func(next string) {
		       log.Printf("processing queued switch to %q", next)
		       // Use background context for queued switch
		       _, _ = s.handleCommand(context.Background(), "start "+next)
	       }(queued)
       }
       return "ok\n", nil
}

func (s *Server) handleStatusConnection(conn net.Conn) {
	defer conn.Close()

	lockActive := s.lockFileExists()

	s.mu.RLock()
	var shutdownAfter time.Time
	idleSeconds := 0.0
	if s.config.IdleShutdownMinutes > 0 && !s.lastActivityAt.IsZero() {
		idleSeconds = time.Since(s.lastActivityAt).Seconds()
		shutdownAfter = s.lastActivityAt.Add(
			time.Duration(s.config.IdleShutdownMinutes) * time.Minute)
	}
	status := Status{
		Healthy:        true,
		LastActivated:  s.lastActivated,
		ActiveTask:     s.activeTask,
		TaskStartedAt:  s.taskStartedAt,
		TaskDoneAt:     s.taskDoneAt,
		PendingSwitch:  s.pendingSwitch,
		LastActivityAt: s.lastActivityAt,
		LastTCPSeenAt:  s.lastTCPSeenAt,
		LockActive:     lockActive,
		ShutdownAfter:  shutdownAfter,
		IdleSeconds:    idleSeconds,
	}
	s.mu.RUnlock()

	_ = json.NewEncoder(conn).Encode(status)
}

// --- Idle Shutdown ---

// onCommandReceived updates the activity clock and writes the lock file.
// Called from handleCommand after the service name is confirmed valid.
// No-op when idle shutdown is disabled (IdleShutdownMinutes == 0).
func (s *Server) onCommandReceived(svc string) {
	if s.config.IdleShutdownMinutes <= 0 {
		return
	}
	s.mu.Lock()
	s.lastActivityAt = time.Now()
	s.mu.Unlock()
	s.writeLock(svc)
}

func writeActiveFile(svc string) {
	if err := os.MkdirAll(filepath.Dir(activeServiceFilePath), 0o755); err != nil {
		log.Printf("active-service-file: mkdirall: %v", err)
		return
	}
	if err := os.WriteFile(activeServiceFilePath, []byte(svc+"\n"), 0o644); err != nil {
		log.Printf("active-service-file: write: %v", err)
	}
}

func (s *Server) writeLock(svc string) {
	dir := filepath.Dir(s.lockFilePath)
	if err := os.MkdirAll(dir, 0o700); err != nil {
		log.Printf("idle-watcher: mkdirall %s: %v", dir, err)
		return
	}
	data, _ := json.Marshal(map[string]string{
		"service":       svc,
		"started_at":    time.Now().UTC().Format(time.RFC3339),
		"last_tcp_seen": "",
	})
	if err := os.WriteFile(s.lockFilePath, data, 0o600); err != nil {
		log.Printf("idle-watcher: write lock: %v", err)
	}
	writeActiveFile(svc)
}

// refreshLock updates last_tcp_seen atomically via temp-file + rename.
func (s *Server) refreshLock(lastTCPSeen time.Time) {
	data, err := os.ReadFile(s.lockFilePath)
	if err != nil {
		return
	}
	var m map[string]string
	if err := json.Unmarshal(data, &m); err != nil {
		return
	}
	m["last_tcp_seen"] = lastTCPSeen.UTC().Format(time.RFC3339)
	updated, _ := json.Marshal(m)
	tmp := s.lockFilePath + ".tmp"
	if err := os.WriteFile(tmp, updated, 0o600); err != nil {
		return
	}
	_ = os.Rename(tmp, s.lockFilePath)
}

func (s *Server) deleteLock() {
	_ = os.Remove(s.lockFilePath)
	_ = os.Remove(activeServiceFilePath)
}

func (s *Server) lockFileExists() bool {
	if s.lockFilePath == "" {
		return false
	}
	_, err := os.Stat(s.lockFilePath)
	return err == nil
}

func (s *Server) lockFileAge() time.Duration {
	info, err := os.Stat(s.lockFilePath)
	if err != nil {
		return 0
	}
	return time.Since(info.ModTime())
}

// probeHasConnections returns true if any established inbound TCP connection
// exists on the given local port, using ss(8) from iproute2.
func probeHasConnections(port int) bool {
	cmd := exec.Command("ss", "-tn", "state", "established",
		fmt.Sprintf("sport = :%d", port))
	out, err := cmd.Output()
	if err != nil {
		return false
	}
	// First line is the header; any additional line is an active connection.
	return strings.Count(strings.TrimSpace(string(out)), "\n") >= 1
}

// readGPUUtilization returns the maximum GPU utilization % across all detected
// GPUs. Checks AMD via sysfs first, then NVIDIA via nvidia-smi.
// Returns -1 if no GPU is detected — callers must treat -1 as "do not shutdown".
func readGPUUtilization() int {
	max := -1

	// AMD: /sys/class/drm/card*/device/gpu_busy_percent (amdgpu kernel driver)
	matches, _ := filepath.Glob("/sys/class/drm/card*/device/gpu_busy_percent")
	for _, p := range matches {
		data, err := os.ReadFile(p)
		if err != nil {
			continue
		}
		val := 0
		if _, err := fmt.Sscanf(strings.TrimSpace(string(data)), "%d", &val); err == nil {
			if val > max {
				max = val
			}
		}
	}

	// NVIDIA: nvidia-smi
	out, err := exec.Command("nvidia-smi",
		"--query-gpu=utilization.gpu",
		"--format=csv,noheader,nounits").Output()
	if err == nil {
		for _, line := range strings.Split(strings.TrimSpace(string(out)), "\n") {
			val := 0
			if _, err := fmt.Sscanf(strings.TrimSpace(line), "%d", &val); err == nil {
				if val > max {
					max = val
				}
			}
		}
	}

	return max
}

// readCPUUtilization returns total CPU usage % sampled over 1 second via /proc/stat.
func readCPUUtilization() int {
	type cpuStat struct{ idle, total uint64 }
	sample := func() cpuStat {
		data, err := os.ReadFile("/proc/stat")
		if err != nil {
			return cpuStat{}
		}
		for _, line := range strings.SplitN(string(data), "\n", 2) {
			if !strings.HasPrefix(line, "cpu ") {
				continue
			}
			fields := strings.Fields(line)
			// fields[1:] = user nice system idle iowait irq softirq steal ...
			var s cpuStat
			for i, f := range fields[1:] {
				var v uint64
				fmt.Sscanf(f, "%d", &v)
				s.total += v
				if i == 3 { // idle column
					s.idle = v
				}
			}
			return s
		}
		return cpuStat{}
	}

	s1 := sample()
	time.Sleep(1 * time.Second)
	s2 := sample()
	dTotal := s2.total - s1.total
	dIdle := s2.idle - s1.idle
	if dTotal == 0 {
		return 0
	}
	return int(100 * (dTotal - dIdle) / dTotal)
}

// hardwarePollGate polls GPU and CPU utilization up to HardwarePollCount times,
// with 60-second waits between polls. Returns true (safe to poweroff) only when
// all polls are below threshold. Returns false on the first active poll, context
// cancellation, or if a new command arrives during polling.
func (s *Server) hardwarePollGate(ctx context.Context) bool {
	threshold := s.config.HardwareIdleThresholdPercent
	count := s.config.HardwarePollCount

	s.mu.RLock()
	baseline := s.lastActivityAt
	s.mu.RUnlock()

	for i := 0; i < count; i++ {
		select {
		case <-ctx.Done():
			return false
		default:
		}

		// Abort if a new command arrived since we entered the gate.
		s.mu.RLock()
		changed := s.lastActivityAt.After(baseline)
		s.mu.RUnlock()
		if changed {
			log.Printf("hw-poll: new command received during gate, aborting shutdown")
			return false
		}

		gpuUtil := readGPUUtilization()
		cpuUtil := readCPUUtilization() // includes 1s sleep internally

		if gpuUtil < 0 {
			log.Printf("hw-poll %d/%d: GPU detection failed, aborting shutdown (conservative)", i+1, count)
			return false
		}
		if gpuUtil > threshold || cpuUtil > threshold {
			log.Printf("hw-poll %d/%d: GPU=%d%% CPU=%d%% → active, aborting shutdown",
				i+1, count, gpuUtil, cpuUtil)
			return false
		}
		log.Printf("hw-poll %d/%d: GPU=%d%% CPU=%d%% → idle", i+1, count, gpuUtil, cpuUtil)

		if i < count-1 {
			select {
			case <-ctx.Done():
				return false
			case <-time.After(60 * time.Second):
			}
		}
	}
	return true
}

func (s *Server) triggerShutdown() {
	log.Println("idle-watcher: all hardware polls confirmed idle, executing systemctl poweroff")
	cmd := exec.Command("systemctl", "poweroff")
	if out, err := cmd.CombinedOutput(); err != nil {
		log.Printf("idle-watcher: poweroff failed: %v: %s", err, strings.TrimSpace(string(out)))
	}
}

// idleWatcher runs as a goroutine and triggers a graceful poweroff when the
// host has been idle for idle_shutdown_minutes. Two paths lead to the hardware
// poll gate:
//
//   - Path A (normal): no lock file AND no activity for idle_shutdown_minutes.
//   - Path B (stale lock): lock file older than idle_shutdown_minutes with no
//     TCP connections — handles hung or frozen AI services.
func (s *Server) idleWatcher(ctx context.Context) {
	idleTimeout := time.Duration(s.config.IdleShutdownMinutes) * time.Minute
	drainGrace := time.Duration(s.config.IdleDrainGraceMinutes) * time.Minute
	ticker := time.NewTicker(30 * time.Second)
	defer ticker.Stop()

	log.Printf("idle-watcher: started — idle_timeout=%v drain_grace=%v hw_threshold=%d%% hw_polls=%d service_port=%d",
		idleTimeout, drainGrace,
		s.config.HardwareIdleThresholdPercent,
		s.config.HardwarePollCount,
		s.config.ServicePort,
	)

	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			s.mu.RLock()
			lastActivity := s.lastActivityAt
			s.mu.RUnlock()

			lockExists := s.lockFileExists()
			lockAge := s.lockFileAge()

			// TCP probe: if connections are active, refresh lock and skip checks.
			if port := s.config.ServicePort; port > 0 {
				if probeHasConnections(port) {
					now := time.Now()
					s.mu.Lock()
					s.lastTCPSeenAt = now
					s.mu.Unlock()
					s.refreshLock(now)
					log.Printf("idle-watcher: TCP connection active on :%d, lock refreshed", port)
					continue
				}
			}

			// No TCP connections this tick. Check drain grace.
			s.mu.RLock()
			lastTCP := s.lastTCPSeenAt
			s.mu.RUnlock()

			if lockExists && !lastTCP.IsZero() && time.Since(lastTCP) >= drainGrace {
				log.Printf("idle-watcher: drain grace elapsed (last TCP %v ago), clearing lock",
					time.Since(lastTCP).Round(time.Second))
				s.deleteLock()
				lockExists = false
			}

			// Path A: no lock file, idle timer expired.
			if !lockExists && time.Since(lastActivity) >= idleTimeout {
				log.Printf("idle-watcher: %.0f min idle, no active lock — entering hardware poll gate",
					time.Since(lastActivity).Minutes())
				if s.hardwarePollGate(ctx) {
					s.triggerShutdown()
					return
				}
				// Hardware was active: bump clock so we don't retry immediately.
				s.mu.Lock()
				s.lastActivityAt = time.Now()
				s.mu.Unlock()
				continue
			}

			// Path B: stale lock (hung/frozen service), idle timer expired.
			if lockExists && lockAge >= idleTimeout {
				log.Printf("idle-watcher: lock is %.0f min old with no TCP — stale lock, entering hardware poll gate",
					lockAge.Minutes())
				if s.hardwarePollGate(ctx) {
					s.triggerShutdown()
					return
				}
				// Hardware was active: refresh mtime to avoid immediate retry.
				s.refreshLock(time.Now())
			}
		}
	}
}
