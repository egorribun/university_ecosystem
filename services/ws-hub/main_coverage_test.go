package main

// Coverage tests (testing session 16) for the no-network bootstrap helpers in
// main.go (initLogger + initRedis). The integration-shaped helpers (initNats /
// setupHub / setupHandlers / runServer — live NATS, os.Exit, global ServeMux)
// stay out of the default run.

import (
	"context"
	"io"
	"log/slog"
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
	logger.Info("init-logger-smoke")
}

func TestInitRedis_SuccessWithMiniredis(t *testing.T) {
	mr := miniredis.RunT(t)
	cfg := &config.Config{RedisURL: mr.Addr()}
	rdb := initRedis(context.Background(), cfg, discardLogger())
	require.NotNil(t, rdb, "Ping must succeed against miniredis → L2 enabled")
	t.Cleanup(func() { _ = rdb.Close() })
	require.NoError(t, rdb.Ping(context.Background()).Err())
}

func TestInitRedis_PingFailureReturnsNil(t *testing.T) {
	// Nothing listening on :1 → Ping fails → initRedis degrades to nil (no L2).
	cfg := &config.Config{RedisURL: "127.0.0.1:1"}
	rdb := initRedis(context.Background(), cfg, discardLogger())
	assert.Nil(t, rdb)
}
