// Gateway router optional-integration contracts.
package main

import (
	"context"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"sync"
	"testing"
	"time"

	"github.com/getsentry/sentry-go"
	"github.com/stretchr/testify/assert"
	"github.com/university-ecosystem/gateway/internal/config"
)

// TestSetupRouterOptionalIntegrations covers Sentry, rate-limit, and JWKS paths.
func TestSetupRouterOptionalIntegrations(t *testing.T) {
	logger := slog.New(slog.NewTextHandler(io.Discard, nil))

	t.Run("sentry dsn non-empty and jwks endpoint configured", func(t *testing.T) {
		cfg := &config.Config{
			Port:                "0",
			BackendURL:          "http://localhost:8080",
			RedisURL:            "redis://invalid-address-to-trigger-ratelimit-error:6379",
			RevocationRedisURL:  "not-a-redis-url",
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
			//nolint:contextcheck
			router, err := setupRouter(cfg, logger, nil, nil, ctx)
			assert.NoError(t, err)
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
		if shutErr := tp.Shutdown(context.Background()); shutErr != nil {
			t.Logf("tracer shutdown: %v", shutErr)
		}
	}
}

// TestInitTracerTLSConfig verifies initTracer with TLS configuration.
func TestInitTracerTLSConfig(t *testing.T) {
	cfg := &config.Config{
		OtelEndpoint: "localhost:4317",
		GrpcUseTLS:   true,
	}

	ctx, cancel := context.WithTimeout(context.Background(), 50*time.Millisecond)
	defer cancel()

	tp, err := initTracer(ctx, cfg)
	if err == nil && tp != nil {
		if shutErr := tp.Shutdown(context.Background()); shutErr != nil {
			t.Logf("tracer shutdown: %v", shutErr)
		}
	}
}

func TestInitSentry_ValidDSN(t *testing.T) {
	logger := slog.New(slog.NewTextHandler(io.Discard, nil))
	initSentry(&config.Config{
		SentryDSN:              "http://public@example.com/1",
		Environment:            "test",
		AppVersion:             "gateway-test",
		SentryTracesSampleRate: 0,
	}, logger)

	assert.True(t, sentry.Flush(100*time.Millisecond))
}

// TestSetupRouterRelaysPublicStaticAndWellKnownToBackend pins the AUD-373 edge
// contract: with the chart routing /static and /.well-known through the gateway,
// the gateway's catch-all relays them unchanged to the backend origin, and an
// anonymous request to them is not answered by the gateway itself.
func TestSetupRouterRelaysPublicStaticAndWellKnownToBackend(t *testing.T) {
	var (
		mu    sync.Mutex
		paths []string
	)
	backend := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		mu.Lock()
		paths = append(paths, r.URL.Path)
		mu.Unlock()
		w.WriteHeader(http.StatusOK)
	}))
	t.Cleanup(backend.Close)

	logger := slog.New(slog.NewTextHandler(io.Discard, nil))
	cfg := &config.Config{
		Port:               "0",
		BackendURL:         backend.URL,
		RedisURL:           "redis://invalid-address-to-trigger-ratelimit-error:6379",
		RevocationRedisURL: "redis://invalid-address-to-trigger-ratelimit-error:6380",
		JWTSecret:          "test-secret-at-least-32-characters-long",
		AllowedOrigins:     []string{"http://localhost:3000"},
		InternalHMACSecret: "test-secret",
	}
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	//nolint:contextcheck
	router, err := setupRouter(cfg, logger, nil, nil, ctx)
	if err != nil {
		t.Fatalf("setupRouter: %v", err)
	}
	for _, route := range []string{"/static/img/logo.png", "/.well-known/jwks.json"} {
		recorder := httptest.NewRecorder()
		request := httptest.NewRequestWithContext(ctx, http.MethodGet, route, nil)
		router.ServeHTTP(recorder, request)
		assert.Equal(t, http.StatusOK, recorder.Code, route)
	}

	mu.Lock()
	defer mu.Unlock()
	assert.Equal(t, []string{"/static/img/logo.png", "/.well-known/jwks.json"}, paths)
}
