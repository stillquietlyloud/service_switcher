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
)

const (
	defaultCommandListenAddress = "0.0.0.0:20100"
	defaultStatusListenAddress  = "0.0.0.0:30100"
	maxCommandBytes             = 1024
)

type Config struct {
	CommandListenAddress string            `json:"command_listen_address"`
	StatusListenAddress  string            `json:"status_listen_address"`
	Services             map[string]string `json:"services"`
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
}

type Status struct {
	Healthy       bool   `json:"healthy"`
	LastActivated string `json:"last_activated"`
}

func main() {
	configPath := flag.String("config", "services.json", "path to services.json")
	flag.Parse()

	config, err := loadConfig(*configPath)
	if err != nil {
		log.Fatalf("load config: %v", err)
	}

	server := &Server{
		config:  config,
		starter: SystemctlStarter{},
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

	reader := bufio.NewReader(io.LimitReader(conn, maxCommandBytes))
	command, err := reader.ReadString('\n')
	if err != nil && !errors.Is(err, io.EOF) {
		_, _ = io.WriteString(conn, "error\n")
		return
	}

	response, err := s.handleCommand(ctx, command)
	if err != nil {
		_, _ = io.WriteString(conn, "error\n")
		return
	}

	_, _ = io.WriteString(conn, response)
}

func (s *Server) handleCommand(ctx context.Context, command string) (string, error) {
	fields := strings.Fields(strings.TrimSpace(command))
	if len(fields) != 2 || fields[0] != "start" {
		return "", errors.New("unsupported command")
	}

	name := fields[1]
	location, ok := s.config.Services[name]
	if !ok {
		return "", errors.New("unknown service")
	}

	unit, err := normalizeUnit(location)
	if err != nil {
		return "", err
	}

	if err := s.starter.Start(ctx, unit); err != nil {
		return "", err
	}

	s.mu.Lock()
	s.lastActivated = name
	s.mu.Unlock()

	return "ok\n", nil
}

func (s *Server) handleStatusConnection(conn net.Conn) {
	defer conn.Close()

	s.mu.RLock()
	status := Status{
		Healthy:       true,
		LastActivated: s.lastActivated,
	}
	s.mu.RUnlock()

	_ = json.NewEncoder(conn).Encode(status)
}
