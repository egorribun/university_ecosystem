package main

import (
	"bytes"
	"context"
	"crypto/tls"
	"errors"
	"log/slog"
	"net/http"
	"os"
	"os/exec"
	"testing"

	"github.com/alicebob/miniredis/v2"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	pb "github.com/university-ecosystem/core/gen/go/file_processor/v1"
	"github.com/university-ecosystem/gateway/internal/config"
	"github.com/university-ecosystem/services/pkg/spiffe"
	sdktrace "go.opentelemetry.io/otel/sdk/trace"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials"
	"google.golang.org/grpc/credentials/insecure"
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
		RevocationRedisURL:  "redis://" + mr.Addr(),
		JWTSecret:           "test-secret-at-least-32-characters-long",
		SentryDSN:           "http://test@localhost/1",
		JWKSEndpoint:        "http://localhost:1/jwks",
		JWKSRefreshInterval: 5,
		AllowedOrigins:      []string{"http://localhost:3000"},
		InternalHMACSecret:  "test-secret",
	}

	assert.NotPanics(t, func() {
		router, err := setupRouter(cfg, initLogger(), nil, nil, t.Context())
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

func TestInitGRPC_Insecure(t *testing.T) {
	cfg := &config.Config{
		FileProcessorAddr: "localhost:50051",
		GrpcUseTLS:        false,
	}
	conn, fileClient, err := initGRPC(cfg, initLogger())
	assert.NoError(t, err)
	assert.NotNil(t, conn)
	assert.NotNil(t, fileClient)
	if conn != nil {
		assert.NoError(t, conn.Close())
	}
}

func TestInitGRPC_SpiffeRequiresClient(t *testing.T) {
	conn, fileClient, err := initGRPC(&config.Config{
		FileProcessorAddr: "localhost:50051",
		SpiffeEnabled:     true,
	}, initLogger())
	assert.Nil(t, conn)
	assert.Nil(t, fileClient)
	assert.ErrorIs(t, err, http.ErrServerClosed)
}

func TestInitGRPC_SpiffeClientCredentialFailure(t *testing.T) {
	conn, fileClient, err := initGRPC(&config.Config{
		FileProcessorAddr:     "localhost:50051",
		SpiffeEnabled:         true,
		FileProcessorSpiffeID: "spiffe://university.ecosystem/ns/services/sa/file-processor",
	}, initLogger(), &spiffe.Client{})

	assert.Nil(t, conn)
	assert.Nil(t, fileClient)
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "uninitialized")
}

func TestInitGRPC_SpiffeClientCredentialSuccess(t *testing.T) {
	oldCredentials := newSpiffeGRPCCredentialsFunc
	t.Cleanup(func() { newSpiffeGRPCCredentialsFunc = oldCredentials })
	newSpiffeGRPCCredentialsFunc = func(*spiffe.Client, string) (credentials.TransportCredentials, error) {
		return insecure.NewCredentials(), nil
	}

	conn, fileClient, err := initGRPC(&config.Config{
		FileProcessorAddr: "localhost:50051",
		SpiffeEnabled:     true,
	}, initLogger(), &spiffe.Client{})
	require.NoError(t, err)
	require.NotNil(t, conn)
	require.NotNil(t, fileClient)
	require.NoError(t, conn.Close())
}

func TestInitGRPC_InvalidTargetReturnsError(t *testing.T) {
	oldNewClient := newGRPCClientFunc
	t.Cleanup(func() { newGRPCClientFunc = oldNewClient })
	newGRPCClientFunc = func(string, ...grpc.DialOption) (*grpc.ClientConn, error) {
		return nil, errors.New("synthetic grpc client failure")
	}

	conn, fileClient, err := initGRPC(&config.Config{FileProcessorAddr: "localhost:50051"}, initLogger())
	assert.Nil(t, conn)
	assert.Nil(t, fileClient)
	assert.EqualError(t, err, "synthetic grpc client failure")
}

func TestSetupRouter_InvalidWsHubURL(t *testing.T) {
	cfg := &config.Config{
		BackendURL:     "http://localhost:8080",
		WsHubURL:       "://invalid-url",
		JWTSecret:      "test-secret-at-least-32-characters-long",
		AllowedOrigins: []string{"http://localhost"},
	}
	router, err := setupRouter(cfg, initLogger(), nil, nil, t.Context())
	assert.Nil(t, router)
	assert.Error(t, err)
}

func TestSetupRouter_SpiffeRequiresClient(t *testing.T) {
	cfg := &config.Config{
		BackendURL:     "http://localhost:8080",
		JWTSecret:      "test-secret-at-least-32-characters-long",
		AllowedOrigins: []string{"http://localhost"},
		SpiffeEnabled:  true,
	}
	router, err := setupRouter(cfg, initLogger(), nil, nil, t.Context())
	assert.Nil(t, router)
	assert.ErrorIs(t, err, http.ErrServerClosed)
}

func TestSetupRouter_SpiffeBackendCredentialFailure(t *testing.T) {
	cfg := &config.Config{
		BackendURL:     "http://localhost:8080",
		JWTSecret:      "test-secret-at-least-32-characters-long",
		AllowedOrigins: []string{"http://localhost"},
		SpiffeEnabled:  true,
	}

	router, err := setupRouter(cfg, initLogger(), nil, nil, t.Context(), &spiffe.Client{})
	assert.Nil(t, router)
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "uninitialized")
}

func TestSetupRouter_SpiffeClientTLSConfigSuccess(t *testing.T) {
	oldTLSConfig := newSpiffeClientTLSConfigFunc
	t.Cleanup(func() { newSpiffeClientTLSConfigFunc = oldTLSConfig })
	newSpiffeClientTLSConfigFunc = func(*spiffe.Client, string) (*tls.Config, error) {
		return &tls.Config{MinVersion: tls.VersionTLS13}, nil
	}

	router, err := setupRouter(&config.Config{
		BackendURL:         "http://localhost:8080",
		WsHubURL:           "http://localhost:8081",
		RevocationRedisURL: "not-a-redis-url",
		JWTSecret:          "test-secret-at-least-32-characters-long",
		AllowedOrigins:     []string{"http://localhost"},
		SpiffeEnabled:      true,
		BackendSpiffeID:    "spiffe://university.ecosystem/ns/services/backend",
	}, initLogger(), nil, nil, t.Context(), &spiffe.Client{})
	require.NoError(t, err)
	require.NotNil(t, router)
}

func TestDefaultSpiffeCloseWrapperIsSafeForEmptyClient(t *testing.T) {
	assert.NoError(t, closeSpiffeClientFunc(&spiffe.Client{}))
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

func TestRun_SpiffeInitializationFailureReturnsError(t *testing.T) {
	t.Setenv("GATEWAY_PORT", "0")
	t.Setenv("JWT_SECRET", "test-secret-at-least-32-characters-long")
	t.Setenv("BACKEND_URL", "http://localhost:8080")
	t.Setenv("REDIS_URL", "")
	t.Setenv("GRPC_USE_TLS", "false")
	t.Setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "")
	t.Setenv("SENTRY_DSN", "")
	t.Setenv("SPIFFE_ENABLED", "true")
	t.Setenv("SPIFFE_TRUST_DOMAIN", "invalid trust domain with spaces!")

	err := run()
	require.Error(t, err)
	assert.Contains(t, err.Error(), "trust")
}

func setValidRunEnvironment(t *testing.T) {
	t.Helper()
	t.Setenv("GATEWAY_PORT", "0")
	t.Setenv("JWT_SECRET", "test-secret-at-least-32-characters-long")
	t.Setenv("BACKEND_URL", "http://localhost:8080")
	t.Setenv("REDIS_URL", "")
	t.Setenv("GRPC_USE_TLS", "false")
	t.Setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "")
	t.Setenv("SENTRY_DSN", "")
	t.Setenv("SPIFFE_ENABLED", "false")
}

func TestRun_TracerFailureStillPropagatesGRPCFailure(t *testing.T) {
	setValidRunEnvironment(t)
	oldTracer := initTracerFunc
	oldGRPC := initGRPCFunc
	t.Cleanup(func() {
		initTracerFunc = oldTracer
		initGRPCFunc = oldGRPC
	})
	initTracerFunc = func(context.Context, *config.Config) (*sdktrace.TracerProvider, error) {
		return nil, errors.New("synthetic tracer failure")
	}
	initGRPCFunc = func(*config.Config, *slog.Logger, ...*spiffe.Client) (*grpc.ClientConn, pb.FileProcessingServiceClient, error) {
		return nil, nil, errors.New("synthetic gRPC failure")
	}

	err := run()
	require.EqualError(t, err, "synthetic gRPC failure")
}

func TestRun_EnabledSPIFFEWithNilClientFailsClosed(t *testing.T) {
	setValidRunEnvironment(t)
	t.Setenv("SPIFFE_ENABLED", "true")
	oldClient := newSpiffeClientFunc
	t.Cleanup(func() { newSpiffeClientFunc = oldClient })
	newSpiffeClientFunc = func(context.Context, spiffe.Config, *slog.Logger) (*spiffe.Client, error) {
		return nil, nil
	}

	err := run()
	require.EqualError(t, err, "SPIFFE is enabled but client initialization returned nil")
}

func TestRun_SpiffeCloseErrorDoesNotMaskStartupFailure(t *testing.T) {
	setValidRunEnvironment(t)
	t.Setenv("SPIFFE_ENABLED", "true")
	oldClient := newSpiffeClientFunc
	oldClose := closeSpiffeClientFunc
	oldGRPC := initGRPCFunc
	t.Cleanup(func() {
		newSpiffeClientFunc = oldClient
		closeSpiffeClientFunc = oldClose
		initGRPCFunc = oldGRPC
	})
	newSpiffeClientFunc = func(context.Context, spiffe.Config, *slog.Logger) (*spiffe.Client, error) {
		return &spiffe.Client{}, nil
	}
	closeSpiffeClientFunc = func(*spiffe.Client) error { return errors.New("synthetic close failure") }
	initGRPCFunc = func(*config.Config, *slog.Logger, ...*spiffe.Client) (*grpc.ClientConn, pb.FileProcessingServiceClient, error) {
		return nil, nil, errors.New("synthetic startup failure")
	}

	err := run()
	require.EqualError(t, err, "synthetic startup failure")
}

type failingSpanExporter struct{}

func (failingSpanExporter) ExportSpans(context.Context, []sdktrace.ReadOnlySpan) error {
	return nil
}

func (failingSpanExporter) Shutdown(context.Context) error {
	return errors.New("synthetic tracer shutdown failure")
}

func TestRun_LogsTracerShutdownFailure(t *testing.T) {
	setValidRunEnvironment(t)
	oldTracer := initTracerFunc
	oldGRPC := initGRPCFunc
	t.Cleanup(func() {
		initTracerFunc = oldTracer
		initGRPCFunc = oldGRPC
	})
	initTracerFunc = func(context.Context, *config.Config) (*sdktrace.TracerProvider, error) {
		return sdktrace.NewTracerProvider(sdktrace.WithSyncer(failingSpanExporter{})), nil
	}
	initGRPCFunc = func(*config.Config, *slog.Logger, ...*spiffe.Client) (*grpc.ClientConn, pb.FileProcessingServiceClient, error) {
		return nil, nil, errors.New("synthetic startup failure")
	}

	require.EqualError(t, run(), "synthetic startup failure")
}

func TestSetupRouter_RejectsShortJWTSecretWithoutExiting(t *testing.T) {
	router, err := setupRouter(&config.Config{
		BackendURL:     "http://localhost:8080",
		WsHubURL:       "http://localhost:8081",
		JWTSecret:      "too-short",
		AllowedOrigins: []string{"http://localhost"},
	}, initLogger(), nil, nil, t.Context())
	assert.Nil(t, router)
	assert.ErrorIs(t, err, http.ErrServerClosed)
}
