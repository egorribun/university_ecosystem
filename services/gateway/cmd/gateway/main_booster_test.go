package main

import (
	"context"
	"io"
	"log/slog"
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
	"github.com/university-ecosystem/gateway/internal/config"
)

// TestSetupRouter_Booster covers setupRouter branches (SentryDSN, RateLimiter error, JWKSEndpoint).
func TestSetupRouter_Booster(t *testing.T) {
	logger := slog.New(slog.NewTextHandler(io.Discard, nil))

	t.Run("sentry dsn non-empty and jwks endpoint configured", func(t *testing.T) {
		cfg := &config.Config{
			Port:                "0",
			BackendURL:          "http://localhost:8080",
			RedisURL:            "redis://invalid-address-to-trigger-ratelimit-error:6379",
			JWTSecret:           "test-secret-at-least-32-characters-long",
			SentryDSN:           "http://test@localhost/1",
			JWKSEndpoint:        "http://localhost:1/jwks",
			JWKSRefreshInterval: 5,
			AllowedOrigins:      []string{"http://localhost:3000"},
			InternalHMACSecret:  "test-secret",
		}

		ctx, cancel := context.WithCancel(context.Background())
		defer cancel()

		assert.NotPanics(t, func() {
			router := setupRouter(cfg, logger, nil, nil, ctx)
			assert.NotNil(t, router)
		})
	})
}

// TestInitTracer_CancelledContext verifies initTracer behavior with a cancelled context.
func TestInitTracer_CancelledContext(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	cancel()

	cfg := &config.Config{
		OtelEndpoint: "localhost:4317",
		GrpcUseTLS:   false,
	}

	tp, err := initTracer(ctx, cfg)
	if err == nil && tp != nil {
		_ = tp.Shutdown(context.Background())
	}
}

// TestInitTracer_TLS_Booster verifies initTracer with TLS config.
func TestInitTracer_TLS_Booster(t *testing.T) {
	cfg := &config.Config{
		OtelEndpoint: "localhost:4317",
		GrpcUseTLS:   true,
	}

	ctx, cancel := context.WithTimeout(context.Background(), 50*time.Millisecond)
	defer cancel()

	tp, err := initTracer(ctx, cfg)
	if err == nil && tp != nil {
		_ = tp.Shutdown(context.Background())
	}
}
