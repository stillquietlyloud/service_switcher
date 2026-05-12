package main

import (
	"context"
	"errors"
	"os"
	"path/filepath"
	"testing"
)

type fakeStarter struct {
	unit    string
	started bool
	err     error
}

func (f *fakeStarter) Start(_ context.Context, unit string) error {
	f.unit = unit
	f.started = true
	return f.err
}

func TestLoadConfigAppliesDefaults(t *testing.T) {
	t.Parallel()

	dir := t.TempDir()
	path := filepath.Join(dir, "services.json")

	err := os.WriteFile(path, []byte(`{"services":{"service01":"/etc/systemd/system/service01.service"}}`), 0o600)
	if err != nil {
		t.Fatalf("write config: %v", err)
	}

	config, err := loadConfig(path)
	if err != nil {
		t.Fatalf("loadConfig returned error: %v", err)
	}

	if config.CommandListenAddress != defaultCommandListenAddress {
		t.Fatalf("got command address %q", config.CommandListenAddress)
	}

	if config.StatusListenAddress != defaultStatusListenAddress {
		t.Fatalf("got status address %q", config.StatusListenAddress)
	}
}

func TestHandleCommandStartsMappedService(t *testing.T) {
	t.Parallel()

	starter := &fakeStarter{}
	server := &Server{
		config: Config{
			Services: map[string]string{
				"service01": "/etc/systemd/system/service01.service",
			},
		},
		starter: starter,
	}

	response, err := server.handleCommand(context.Background(), "start service01\n")
	if err != nil {
		t.Fatalf("handleCommand returned error: %v", err)
	}

	if response != "ok\n" {
		t.Fatalf("got response %q", response)
	}

	if !starter.started {
		t.Fatal("expected starter to be called")
	}

	if starter.unit != "service01.service" {
		t.Fatalf("got unit %q", starter.unit)
	}

	if server.lastActivated != "service01" {
		t.Fatalf("got lastActivated %q", server.lastActivated)
	}
}

func TestHandleCommandRejectsUnknownService(t *testing.T) {
	t.Parallel()

	server := &Server{
		config: Config{
			Services: map[string]string{
				"service01": "/etc/systemd/system/service01.service",
			},
		},
		starter: &fakeStarter{},
	}

	if _, err := server.handleCommand(context.Background(), "start missing\n"); err == nil {
		t.Fatal("expected error for unknown service")
	}
}

func TestHandleCommandPropagatesStarterErrors(t *testing.T) {
	t.Parallel()

	server := &Server{
		config: Config{
			Services: map[string]string{
				"service01": "/etc/systemd/system/service01.service",
			},
		},
		starter: &fakeStarter{err: errors.New("boom")},
	}

	if _, err := server.handleCommand(context.Background(), "start service01\n"); err == nil {
		t.Fatal("expected starter error")
	}
}
