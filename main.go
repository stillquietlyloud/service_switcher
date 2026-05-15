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

       s.mu.RLock()
       status := Status{
	       Healthy:       true,
	       LastActivated: s.lastActivated,
	       ActiveTask:    s.activeTask,
	       TaskStartedAt: s.taskStartedAt,
	       TaskDoneAt:    s.taskDoneAt,
	       PendingSwitch: s.pendingSwitch,
       }
       s.mu.RUnlock()

       _ = json.NewEncoder(conn).Encode(status)
}
