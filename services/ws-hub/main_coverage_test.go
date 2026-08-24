package main

// Coverage tests (testing session 16) for the no-network bootstrap helpers in
// main.go (initLogger + initRedis). The integration-shaped helpers (initNats /
// setupHub / setupHandlers / runServer — live NATS, os.Exit, global ServeMux)
// stay out of the default run.

import (
	"context"
	"errors"
	"io"
	"log/slog"
	"net/http"
	"testing"

	"github.com/alicebob/miniredis/v2"
	"github.com/nats-io/nats.go"
	"github.com/redis/go-redis/v9"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"github.com/university-ecosystem/services/pkg/spiffe"
	"github.com/university-ecosystem/ws-hub/pkg/config"
)

func discardLogger() *slog.Logger {
	return slog.New(slog.NewTextHandler(io.Discard, nil))
}

func TestInitLogger_ReturnsLogger(t *testing.T) {
	logger := initLogger()
	require.NotNil(t, logger)
	logger.InfoContext(context.Background(), "init-logger-smoke")
}

func TestInitRedis_SuccessWithMiniredis(t *testing.T) {
	mr := miniredis.RunT(t)
	cfg := &config.Config{RedisURL: mr.Addr()}
	rdb := initRedis(context.Background(), cfg, discardLogger())
	require.NotNil(t, rdb, "Ping must succeed against miniredis → L2 enabled")
	t.Cleanup(func() { _ = rdb.Close() }) //nolint:errcheck // best-effort cleanup
	require.NoError(t, rdb.Ping(context.Background()).Err())
}

func TestInitRedis_PingFailureReturnsNil(t *testing.T) {
	// Nothing listening on :1 → Ping fails → initRedis degrades to nil (no L2).
	cfg := &config.Config{RedisURL: "127.0.0.1:1"}
	rdb := initRedis(context.Background(), cfg, discardLogger())
	assert.Nil(t, rdb)
}

func TestInitRevocationRedis_ValidatesConfigurationAndConnectivity(t *testing.T) {
	logger := discardLogger()

	t.Run("missing URL", func(t *testing.T) {
		client, err := initRevocationRedis(context.Background(), &config.Config{}, logger)
		assert.Nil(t, client)
		assert.EqualError(t, err, "REVOCATION_REDIS_URL is not set")
	})

	t.Run("invalid URL", func(t *testing.T) {
		client, err := initRevocationRedis(
			context.Background(),
			&config.Config{RevocationRedisURL: "not-a-redis-url"},
			logger,
		)
		assert.Nil(t, client)
		require.ErrorContains(t, err, "parse REVOCATION_REDIS_URL")
	})

	t.Run("ping failure", func(t *testing.T) {
		client, err := initRevocationRedis(
			context.Background(),
			&config.Config{RevocationRedisURL: "redis://127.0.0.1:1/0"},
			logger,
		)
		assert.Nil(t, client)
		require.ErrorContains(t, err, "connect revocation Redis")
	})

	t.Run("ping and close failure", func(t *testing.T) {
		oldClose := closeRedisFunc
		t.Cleanup(func() { closeRedisFunc = oldClose })
		closeRedisFunc = func(*redis.Client) error { return errors.New("synthetic close failure") }
		client, err := initRevocationRedis(
			context.Background(),
			&config.Config{RevocationRedisURL: "redis://127.0.0.1:1/0"},
			logger,
		)
		assert.Nil(t, client)
		require.ErrorContains(t, err, "close client: synthetic close failure")
	})

	t.Run("success", func(t *testing.T) {
		mr := miniredis.RunT(t)
		client, err := initRevocationRedis(
			context.Background(),
			&config.Config{RevocationRedisURL: "redis://" + mr.Addr() + "/0"},
			logger,
		)
		require.NoError(t, err)
		require.NotNil(t, client)
		t.Cleanup(func() { require.NoError(t, client.Close()) })
	})
}

func TestInitSpiffeClient_DisabledReturnsNil(t *testing.T) {
	cfg := &config.Config{SpiffeEnabled: false}
	client, err := initSpiffeClient(context.Background(), cfg, discardLogger())
	require.NoError(t, err)
	assert.Nil(t, client)
}

func TestInitSpiffeClient_InvalidTrustDomainFailsBeforeSocketDial(t *testing.T) {
	cfg := &config.Config{
		SpiffeEnabled:     true,
		SpiffeTrustDomain: "not a trust domain",
	}
	client, err := initSpiffeClient(context.Background(), cfg, discardLogger())
	assert.Nil(t, client)
	require.Error(t, err)
	assert.ErrorContains(t, err, "invalid SPIFFE trust domain")
}

func TestSetupHub_EnabledSpiffeRequiresClient(t *testing.T) {
	cfg := &config.Config{
		BackendURL:      "http://localhost:1",
		SpiffeEnabled:   true,
		BackendSpiffeID: "spiffe://university.ecosystem/ns/default/sa/backend",
	}
	h, err := setupHub(context.Background(), cfg, discardLogger(), nil, nil)
	assert.Nil(t, h)
	assert.ErrorIs(t, err, http.ErrServerClosed)
}

func TestDefaultInitNats_RejectsMalformedURL(t *testing.T) {
	cfg := &config.Config{NatsURL: "://not-a-url"}
	nc, err := defaultInitNats(context.Background(), cfg, discardLogger())
	assert.Nil(t, nc)
	assert.Error(t, err)
}

func TestCleanupHelpersAreNilSafe(t *testing.T) {
	assert.NotPanics(t, func() {
		closeNATSConnection(nil)
		closeRedisConnection(context.Background(), nil, discardLogger())
		closeSPIFFEClient(context.Background(), nil, discardLogger())
	})
}

func TestDefaultCloseSpiffeAdapterDelegates(t *testing.T) {
	assert.NoError(t, closeSpiffeClientFunc(&spiffe.Client{}))
}

func TestRun_PropagatesNATSInitializationFailure(t *testing.T) {
	t.Setenv("WS_HUB_INTERNAL_SECRET", "test-secret-at-least-32-characters-long")
	t.Setenv("SENTRY_DSN", "not-a-valid-dsn")
	t.Setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "127.0.0.1:4317")
	t.Setenv("OTEL_EXPORTER_OTLP_INSECURE", "true")

	initNatsMu.Lock()
	oldInitNats := initNats
	initNats = func(context.Context, *config.Config, *slog.Logger) (*nats.Conn, error) {
		return nil, errors.New("nats initialization failed")
	}
	initNatsMu.Unlock()
	t.Cleanup(func() {
		initNatsMu.Lock()
		initNats = oldInitNats
		initNatsMu.Unlock()
	})

	err := run()
	require.EqualError(t, err, "nats initialization failed")
}

func TestInitializeTracerShutdown_CancelledContextIsSafe(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	cancel()

	cleanup := initializeTracerShutdown(ctx, &config.Config{Environment: "test"}, discardLogger())
	assert.NotPanics(t, cleanup)
}

func TestInitializeTracerShutdown_SuccessPathCleansUp(t *testing.T) {
	t.Setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "127.0.0.1:4317")
	t.Setenv("OTEL_EXPORTER_OTLP_INSECURE", "true")

	cleanup := initializeTracerShutdown(context.Background(), &config.Config{Environment: "test"}, discardLogger())
	assert.NotPanics(t, cleanup)
}
