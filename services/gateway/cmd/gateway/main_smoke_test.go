package main

// Coverage smoke (testing session 9) for setupRouter — the single largest 0%
// block in the gateway (main.go is ~86 statements that Go 1.20+ already counts
// in the ./... denominator at 0%). One test wires the full router and probes
// only the routes that need neither a live backend nor the file-processor gRPC
// client.
//
// ⚠ Invariants that keep this safe:
//   - setupRouter is called EXACTLY ONCE in this package: ginprometheus.NewPrometheus
//     registers gin metrics on the global registry and panics on a second call,
//     and SetListenAddress(":9102") spawns a real (leaked-until-exit) listener.
//   - cfg must be valid or setupRouter calls os.Exit(1): BackendURL must parse and
//     JWTSecret must be ≥32 chars.
//   - RedisURL="" → NewRateLimiter errors → rate-limiter-absent branch → nil redis
//     client → WarmL1Cache/ListenForRevocations early-return (no goroutines, no
//     Redis dependency).
//   - grpcConn/fileClient are nil but ProxyOrFileHandler only dereferences them on
//     POST /files/process/sync, which none of these probes hit.

import (
	"context"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/gin-gonic/gin"
	"github.com/stretchr/testify/assert"
	"github.com/university-ecosystem/gateway/internal/config"
)

func TestSetupRouter_WiresRoutesAndProbes(t *testing.T) {
	cfg := &config.Config{
		Port:               "8080",
		BackendURL:         "http://127.0.0.1:1",                           // parseable, never dialed by these probes
		RedisURL:           "",                                             // → rate-limiter-absent branch → nil redis client
		JWTSecret:          "smoke-test-jwt-secret-at-least-32-chars-long", // ≥32 chars, avoids os.Exit
		RateLimitRPS:       100,
		RateLimitBurst:     200,
		AllowedOrigins:     []string{"http://localhost:3000"},
		InternalHMACSecret: "smoke-internal-hmac-secret",
	}
	logger := slog.New(slog.NewTextHandler(io.Discard, nil))

	var router *gin.Engine
	assert.NotPanics(t, func() {
		router = setupRouter(cfg, logger, nil, nil, context.Background())
	}, "setupRouter must wire a valid config without panicking or exiting")
	if router == nil {
		t.Fatal("setupRouter returned nil")
	}

	t.Run("health is public", func(t *testing.T) {
		rec := httptest.NewRecorder()
		router.ServeHTTP(rec, httptest.NewRequest(http.MethodGet, "/health", nil))
		assert.Equal(t, http.StatusOK, rec.Code)
	})

	t.Run("protected v1 route without auth is 401", func(t *testing.T) {
		rec := httptest.NewRecorder()
		router.ServeHTTP(rec, httptest.NewRequest(http.MethodGet, "/api/v1/users/me", nil))
		assert.Equal(t, http.StatusUnauthorized, rec.Code)
		assert.Contains(t, rec.Body.String(), "missing authorization header")
	})

	t.Run("unknown /api route is 404 JSON", func(t *testing.T) {
		rec := httptest.NewRecorder()
		router.ServeHTTP(rec, httptest.NewRequest(http.MethodGet, "/api/totally/unknown", nil))
		assert.Equal(t, http.StatusNotFound, rec.Code)
		assert.Contains(t, rec.Body.String(), "endpoint not found")
	})
}
