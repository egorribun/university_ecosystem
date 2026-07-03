package main

import (
	"bufio"
	"bytes"
	"context"
	"io"
	"log/slog"
	"net"
	"net/http"
	"os"
	"os/exec"
	"strings"
	"testing"

	"github.com/alicebob/miniredis/v2"
	"github.com/nats-io/nats.go"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"github.com/university-ecosystem/ws-hub/pkg/config"
)

// TestMain_InvalidPortExitsCleanly tests that running main() with an invalid port
// and NATS mocked to nil triggers an immediate startup failure in the server loop,
// leading to a clean, graceful shutdown without panicking or calling os.Exit.
func TestMain_InvalidPortExitsCleanly(t *testing.T) {
	http.DefaultServeMux = http.NewServeMux()

	lc := net.ListenConfig{}
	l, err := lc.Listen(t.Context(), "tcp", "127.0.0.1:0")
	require.NoError(t, err)
	defer func() { _ = l.Close() }() //nolint:errcheck // test listener cleanup

	go func() {
		conn, err := l.Accept()
		if err != nil {
			return
		}
		defer func() { _ = conn.Close() }() //nolint:errcheck // test conn cleanup
		if _, writeErr := conn.Write([]byte(`INFO {"server_id":"MOCK","version":"2.0.0","host":"127.0.0.1","port":4222,"auth_required":false}` + "\r\n")); writeErr != nil {
			t.Logf("mock NATS INFO write failed: %v", writeErr)
			return
		}

		reader := bufio.NewReader(conn)
		for {
			line, err := reader.ReadString('\n')
			if err != nil {
				return
			}
			if strings.HasPrefix(line, "PING") {
				if _, writeErr := conn.Write([]byte("PONG\r\n")); writeErr != nil {
					t.Logf("mock NATS PONG write failed: %v", writeErr)
					return
				}
			}
		}
	}()

	mr := miniredis.RunT(t)

	t.Setenv("WS_HUB_PORT", "-1")
	t.Setenv("WS_HUB_INTERNAL_SECRET", "test-secret-at-least-32-characters-long")
	t.Setenv("BACKEND_URL", "http://localhost:8080")
	t.Setenv("NATS_URL", "nats://"+l.Addr().String())
	t.Setenv("REDIS_URL", mr.Addr())
	t.Setenv("JWKS_URL", "http://127.0.0.1:1/jwks")

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

	cmd := exec.CommandContext(t.Context(), os.Args[0], "-test.run=TestMain_ExitOnMissingInternalSecret") //nolint:gosec // G204: intentional re-exec of test binary
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

	cmd := exec.CommandContext(t.Context(), os.Args[0], "-test.run=TestMain_ExitOnJWKSFailure") //nolint:gosec // G204: intentional re-exec of test binary
	cmd.Env = append(os.Environ(), "RUN_CRASHING_MAIN=JWKS")
	err := cmd.Run()
	if e, ok := err.(*exec.ExitError); ok && !e.Success() {
		assert.Equal(t, 1, e.ExitCode())
		return
	}
	t.Fatalf("process ran without expected exit status 1: %v", err)
}

func TestInitNats_Success(t *testing.T) {
	lc := net.ListenConfig{}
	l, err := lc.Listen(t.Context(), "tcp", "127.0.0.1:0")
	require.NoError(t, err)
	defer func() { _ = l.Close() }() //nolint:errcheck // test listener cleanup

	go func() {
		conn, err := l.Accept()
		if err != nil {
			return
		}
		defer func() { _ = conn.Close() }() //nolint:errcheck // test conn cleanup
		if _, writeErr := conn.Write([]byte(`INFO {"server_id":"MOCK","version":"2.0.0","host":"127.0.0.1","port":4222,"auth_required":false}` + "\r\n")); writeErr != nil {
			t.Logf("mock NATS INFO write failed: %v", writeErr)
			return
		}

		reader := bufio.NewReader(conn)
		for {
			line, err := reader.ReadString('\n')
			if err != nil {
				return
			}
			if strings.HasPrefix(line, "PING") {
				if _, writeErr := conn.Write([]byte("PONG\r\n")); writeErr != nil {
					t.Logf("mock NATS PONG write failed: %v", writeErr)
					return
				}
			}
		}
	}()

	cfg := &config.Config{
		NatsURL:      "nats://" + l.Addr().String(),
		NatsUser:     "test-user",
		NatsPassword: "test-password",
	}
	ctx := context.Background()
	logger := slog.New(slog.NewTextHandler(io.Discard, nil))

	nc := initNats(ctx, cfg, logger)
	require.NotNil(t, nc)
	nc.Close()
}

func TestInitNats_ExitOnFailure(t *testing.T) {
	if os.Getenv("RUN_CRASHING_NATS") == "1" {
		cfg := &config.Config{
			NatsURL: "nats://foo\x00bar", // control character causes parsing failure
		}
		logger := slog.New(slog.NewTextHandler(io.Discard, nil))
		initNats(context.Background(), cfg, logger)
		return
	}

	cmd := exec.CommandContext(t.Context(), os.Args[0], "-test.run=TestInitNats_ExitOnFailure") //nolint:gosec // G204: intentional re-exec of test binary
	cmd.Env = append(os.Environ(), "RUN_CRASHING_NATS=1")
	err := cmd.Run()
	if e, ok := err.(*exec.ExitError); ok && !e.Success() {
		assert.Equal(t, 1, e.ExitCode())
		return
	}
	t.Fatalf("process ran without expected exit status 1: %v", err)
}
