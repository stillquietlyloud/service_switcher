package main

import (
	"context"
	"errors"
	"os"
	"path/filepath"
	"testing"
	"time"
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

func TestLockFileLifecycle(t *testing.T) {
	t.Parallel()

	dir := t.TempDir()
	srv := &Server{
		config:       Config{Services: map[string]string{"s1": "/etc/systemd/system/s1.service"}},
		starter:      &fakeStarter{},
		lockFilePath: filepath.Join(dir, "active.lock"),
	}

	if srv.lockFileExists() {
		t.Fatal("lock should not exist initially")
	}

	srv.writeLock("s1")
	if !srv.lockFileExists() {
		t.Fatal("lock should exist after writeLock")
	}

	age := srv.lockFileAge()
	if age < 0 || age > 5*time.Second {
		t.Fatalf("unexpected lock age: %v", age)
	}

	srv.deleteLock()
	if srv.lockFileExists() {
		t.Fatal("lock should not exist after deleteLock")
	}
}

func TestOnCommandReceived_UpdatesActivity(t *testing.T) {
	t.Parallel()

	dir := t.TempDir()
	srv := &Server{
		config: Config{
			IdleShutdownMinutes: 15,
			Services:            map[string]string{"s1": "/etc/systemd/system/s1.service"},
		},
		starter:      &fakeStarter{},
		lockFilePath: filepath.Join(dir, "active.lock"),
	}

	before := time.Now()
	srv.onCommandReceived("s1")
	after := time.Now()

	srv.mu.RLock()
	activity := srv.lastActivityAt
	srv.mu.RUnlock()

	if activity.Before(before) || activity.After(after) {
		t.Fatalf("lastActivityAt %v not in expected range [%v, %v]", activity, before, after)
	}
	if !srv.lockFileExists() {
		t.Fatal("lock file should exist after onCommandReceived")
	}
}

func TestOnCommandReceived_NoOpWhenDisabled(t *testing.T) {
	t.Parallel()

	dir := t.TempDir()
	srv := &Server{
		config: Config{
			IdleShutdownMinutes: 0,
			Services:            map[string]string{"s1": "/etc/systemd/system/s1.service"},
		},
		starter:      &fakeStarter{},
		lockFilePath: filepath.Join(dir, "active.lock"),
	}

	srv.onCommandReceived("s1")
	if srv.lockFileExists() {
		t.Fatal("lock file should not be created when idle shutdown is disabled")
	}
}

func TestReadGPUUtilization_SaneRange(t *testing.T) {
	t.Parallel()

	val := readGPUUtilization()
	if val < -1 || val > 100 {
		t.Fatalf("readGPUUtilization returned out-of-range value: %d", val)
	}
}

func TestHardwarePollGate_AbortsOnContextCancel(t *testing.T) {
	t.Parallel()

	dir := t.TempDir()
	srv := &Server{
		config: Config{
			HardwareIdleThresholdPercent: 5,
			HardwarePollCount:            10,
			Services:                     map[string]string{"s1": "/etc/systemd/system/s1.service"},
		},
		starter:      &fakeStarter{},
		lockFilePath: filepath.Join(dir, "active.lock"),
	}

	srv.mu.Lock()
	srv.lastActivityAt = time.Now()
	srv.mu.Unlock()

	ctx, cancel := context.WithCancel(context.Background())
	cancel()

	if srv.hardwarePollGate(ctx) {
		t.Fatal("hardwarePollGate should return false on cancelled context")
	}
}
