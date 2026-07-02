package main

import (
	"bytes"
	"context"
	"log/slog"
	"net/http"
	"os"
	"os/exec"
	"testing"

	"github.com/nats-io/nats.go"
	"github.com/stretchr/testify/assert"
	"github.com/university-ecosystem/ws-hub/pkg/config"
)

// TestMain_InvalidPortExitsCleanly tests that running main() with an invalid port
// and NATS mocked to nil triggers an immediate startup failure in the server loop,
// leading to a clean, graceful shutdown without panicking or calling os.Exit.
func TestMain_InvalidPortExitsCleanly(t *testing.T) {
	http.DefaultServeMux = http.NewServeMux()

	// Backup original initNats function
	oldInitNats := initNats
	defer func() { initNats = oldInitNats }()

	// Mock NATS connect to return nil so it doesn't try to connect to a real broker
	initNats = func(ctx context.Context, cfg *config.Config, logger *slog.Logger) *nats.Conn {
		return nil
	}

	// Setup environment config variables
	t.Setenv("WS_HUB_PORT", "-1")
	t.Setenv("WS_HUB_INTERNAL_SECRET", "test-secret-at-least-32-characters-long")
	t.Setenv("BACKEND_URL", "http://localhost:8080")
	t.Setenv("REDIS_URL", "") // disable redis cache
	t.Setenv("JWKS_URL", "")  // skip JWKS setup

	assert.NotPanics(t, func() {
		main()
	})
}

// TestMain_ExitOnMissingInternalSecret verifies that main() exits with 1 when the internal secret is empty.
func TestMain_ExitOnMissingInternalSecret(t *testing.T) {
	if os.Getenv("RUN_CRASHING_MAIN") == "SECRET" {
		t.Setenv("WS_HUB_INTERNAL_SECRET", "")
		main()
		return
	}

	cmd := exec.Command(os.Args[0], "-test.run=TestMain_ExitOnMissingInternalSecret")
	cmd.Env = append(os.Environ(), "RUN_CRASHING_MAIN=SECRET")
	var errStdout, errStderr bytes.Buffer
	cmd.Stdout = &errStdout
	cmd.Stderr = &errStderr

	err := cmd.Run()
	if e, ok := err.(*exec.ExitError); ok && !e.Success() {
		assert.Equal(t, 1, e.ExitCode())
		return
	}
	t.Fatalf("process ran without expected exit status 1: %v, stdout: %s, stderr: %s", err, errStdout.String(), errStderr.String())
}

// TestMain_ExitOnJWKSFailure verifies that main() exits with 1 when the JWKS setup fails.
func TestMain_ExitOnJWKSFailure(t *testing.T) {
	if os.Getenv("RUN_CRASHING_MAIN") == "JWKS" {
		oldInitNats := initNats
		defer func() { initNats = oldInitNats }()
		initNats = func(ctx context.Context, cfg *config.Config, logger *slog.Logger) *nats.Conn {
			return nil
		}

		http.DefaultServeMux = http.NewServeMux()

		t.Setenv("WS_HUB_PORT", "0")
		t.Setenv("WS_HUB_INTERNAL_SECRET", "test-secret-at-least-32-characters-long")
		t.Setenv("BACKEND_URL", "http://localhost:8080")
		t.Setenv("REDIS_URL", "")
		// Invalid JWKS URL containing a control character to guarantee SetupJWKS returns an error
		t.Setenv("JWKS_URL", "http://[::1]:\x00")
		main()
		return
	}

	cmd := exec.Command(os.Args[0], "-test.run=TestMain_ExitOnJWKSFailure")
	cmd.Env = append(os.Environ(), "RUN_CRASHING_MAIN=JWKS")
	err := cmd.Run()
	if e, ok := err.(*exec.ExitError); ok && !e.Success() {
		assert.Equal(t, 1, e.ExitCode())
		return
	}
	t.Fatalf("process ran without expected exit status 1: %v", err)
}
