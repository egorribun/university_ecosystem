package main

import (
	"bytes"
	"context"
	"os"
	"os/exec"
	"testing"

	"github.com/alicebob/miniredis/v2"
	"github.com/stretchr/testify/assert"
	"github.com/university-ecosystem/gateway/internal/config"
)

// TestMain_InvalidPortExitsCleanly tests that running main() with an invalid port
// causes the server to fail immediately and trigger graceful shutdown, running
// all deferred cleanup logic and exiting main() without calling os.Exit.
func TestMain_InvalidPortExitsCleanly(t *testing.T) {
	// Set valid config parameters except port
	t.Setenv("GATEWAY_PORT", "-1")
	t.Setenv("JWT_SECRET", "test-secret-at-least-32-characters-long")
	t.Setenv("BACKEND_URL", "http://localhost:8080")
	t.Setenv("REDIS_URL", "") // disable redis rate limiter
	t.Setenv("GRPC_USE_TLS", "false")
	t.Setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "")
	t.Setenv("SENTRY_DSN", "")

	// We run run() directly in the test context.
	// Since port is -1, ListenAndServe fails immediately, runServer handles the error,
	// performs orderly shutdown, and returns an error. run() executes all defers and returns the error.
	assert.NotPanics(t, func() {
		err := run()
		assert.Error(t, err)
	})
}

// TestMain_ExitOnShortJWTSecret verifies that main() exits with 1 when the JWT secret is too short.
func TestMain_ExitOnShortJWTSecret(t *testing.T) {
	if os.Getenv("RUN_CRASHING_MAIN") == "JWT" {
		t.Setenv("GATEWAY_PORT", "0")
		t.Setenv("JWT_SECRET", "too-short")
		t.Setenv("BACKEND_URL", "http://localhost:8080")
		t.Setenv("REDIS_URL", "")
		t.Setenv("GRPC_USE_TLS", "false")
		t.Setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "")
		main()
		return
	}

	cmd := exec.CommandContext(t.Context(), os.Args[0], "-test.run=TestMain_ExitOnShortJWTSecret") //nolint:gosec // G204: intentional re-exec of test binary
	cmd.Env = append(os.Environ(), "RUN_CRASHING_MAIN=JWT")
	var errStdout, errStderr bytes.Buffer
	cmd.Stdout = &errStdout
	cmd.Stderr = &errStderr

	err := cmd.Run()
	if e, ok := err.(*exec.ExitError); ok && !e.Success() {
		// Verify it exited with 1
		assert.Equal(t, 1, e.ExitCode())
		return
	}
	t.Fatalf("process ran without expected exit status 1: %v, stdout: %s, stderr: %s", err, errStdout.String(), errStderr.String())
}

// TestMain_ExitOnInvalidBackendURL verifies that main() exits with 1 when the backend URL is unparseable.
func TestMain_ExitOnInvalidBackendURL(t *testing.T) {
	if os.Getenv("RUN_CRASHING_MAIN") == "BACKEND" {
		t.Setenv("GATEWAY_PORT", "0")
		t.Setenv("JWT_SECRET", "test-secret-at-least-32-characters-long")
		t.Setenv("BACKEND_URL", "://invalid-url")
		t.Setenv("REDIS_URL", "")
		t.Setenv("GRPC_USE_TLS", "false")
		t.Setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "")
		main()
		return
	}

	cmd := exec.CommandContext(t.Context(), os.Args[0], "-test.run=TestMain_ExitOnInvalidBackendURL") //nolint:gosec // G204: intentional re-exec of test binary
	cmd.Env = append(os.Environ(), "RUN_CRASHING_MAIN=BACKEND")
	err := cmd.Run()
	if e, ok := err.(*exec.ExitError); ok && !e.Success() {
		assert.Equal(t, 1, e.ExitCode())
		return
	}
	t.Fatalf("process ran without expected exit status 1: %v", err)
}

// TestMain_ExitOnConfigLoadFailure verifies that main() exits with 1 when config loading fails.
func TestMain_ExitOnConfigLoadFailure(t *testing.T) {
	if os.Getenv("RUN_CRASHING_MAIN") == "CONFIG" {
		t.Setenv("JWT_SECRET", "") // triggers fail-secure config error
		t.Setenv("GATEWAY_PORT", "0")
		t.Setenv("BACKEND_URL", "http://localhost:8080")
		t.Setenv("REDIS_URL", "")
		main()
		return
	}

	cmd := exec.CommandContext(t.Context(), os.Args[0], "-test.run=TestMain_ExitOnConfigLoadFailure") //nolint:gosec // G204: intentional re-exec of test binary
	cmd.Env = append(os.Environ(), "RUN_CRASHING_MAIN=CONFIG")
	err := cmd.Run()
	if e, ok := err.(*exec.ExitError); ok && !e.Success() {
		assert.Equal(t, 1, e.ExitCode())
		return
	}
	t.Fatalf("process ran without expected exit status 1: %v", err)
}

func TestSetupRouter_FullFeatures(t *testing.T) {
	mr := miniredis.RunT(t)

	cfg := &config.Config{
		Port:                "0",
		BackendURL:          "http://localhost:8080",
		RedisURL:            "redis://" + mr.Addr(),
		JWTSecret:           "test-secret-at-least-32-characters-long",
		SentryDSN:           "http://test@localhost/1",
		JWKSEndpoint:        "http://localhost:1/jwks",
		JWKSRefreshInterval: 5,
		AllowedOrigins:      []string{"http://localhost:3000"},
		InternalHMACSecret:  "test-secret",
	}

	assert.NotPanics(t, func() {
		router, err := setupRouter(cfg, initLogger(), nil, nil, context.Background())
		assert.NoError(t, err)
		assert.NotNil(t, router)
	})
}

func TestInitGRPC_TLS(t *testing.T) {
	cfg := &config.Config{
		FileProcessorAddr: "localhost:50051",
		GrpcUseTLS:        true,
	}
	conn, client, err := initGRPC(cfg, initLogger())
	assert.NoError(t, err)
	assert.NotNil(t, conn)
	assert.NotNil(t, client)
	if err := conn.Close(); err != nil {
		t.Logf("gRPC conn close: %v", err)
	}
}

func TestInitTracer_TLS(t *testing.T) {
	cfg := &config.Config{
		OtelEndpoint: "localhost:4317",
		GrpcUseTLS:   true,
	}
	tp, err := initTracer(context.Background(), cfg)
	if err == nil {
		assert.NotNil(t, tp)
		if shutdownErr := tp.Shutdown(context.Background()); shutdownErr != nil {
			t.Logf("tracer shutdown: %v", shutdownErr)
		}
	}
}
