package main

// Coverage tests (testing session 16) for the no-network bootstrap helpers in
// main.go (initLogger + initRedis). The integration-shaped helpers (initNats /
// setupHub / setupHandlers / runServer — live NATS, os.Exit, global ServeMux)
// stay out of the default run.

import (
	"context"
	"io"
	"log/slog"
	"net/http"
	"testing"

	"github.com/alicebob/miniredis/v2"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
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
