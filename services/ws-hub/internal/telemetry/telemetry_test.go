package telemetry

import (
	"context"
	"testing"

	"github.com/stretchr/testify/require"
	"github.com/university-ecosystem/ws-hub/pkg/config"
)

func TestInitSentry(t *testing.T) {
	t.Run("empty sentry dsn", func(t *testing.T) {
		cfg := &config.Config{SentryDSN: ""}
		err := InitSentry(cfg)
		require.NoError(t, err)
	})

	t.Run("invalid sentry dsn", func(t *testing.T) {
		cfg := &config.Config{SentryDSN: "invalid-dsn"}
		err := InitSentry(cfg)
		require.Error(t, err)
	})

	t.Run("valid-looking dummy sentry dsn", func(t *testing.T) {
		cfg := &config.Config{
			SentryDSN:   "http://a1b2c3d4@sentry.example.com/1",
			Environment: "test",
		}
		err := InitSentry(cfg)
		require.NoError(t, err)
	})
}

func TestInitTracer(t *testing.T) {
	ctx := context.Background()
	cfg := &config.Config{
		Environment: "test",
	}

	tp, err := InitTracer(ctx, cfg)
	require.NoError(t, err)
	require.NotNil(t, tp)
	t.Cleanup(func() {
		_ = tp.Shutdown(ctx)
	})
}
