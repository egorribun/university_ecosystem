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
//   - An in-process Redis supplies both rate limiting and revocation checks;
//     startup degradation is covered separately by middleware tests.
//   - grpcConn/fileClient are nil but ProxyOrFileHandler only dereferences them on
//     POST /files/process/sync, which none of these probes hit.

import (
	"context"
	"flag"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/alicebob/miniredis/v2"
	"github.com/gin-gonic/gin"
	"github.com/golang-jwt/jwt/v5"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"github.com/university-ecosystem/gateway/internal/config"
	"github.com/university-ecosystem/gateway/middleware"
)

func TestConfigureGinPrometheus(t *testing.T) {
	oldFlags := flag.CommandLine
	flag.CommandLine = flag.NewFlagSet("gateway-test", flag.ContinueOnError)
	t.Cleanup(func() { flag.CommandLine = oldFlags })
	oldMode := gin.Mode()
	gin.SetMode(gin.ReleaseMode)
	t.Cleanup(func() { gin.SetMode(oldMode) })
	setupGinPrometheusFunc(gin.New())
}

func TestSetupRouter_WiresRoutesAndProbes(t *testing.T) {
	mr := miniredis.RunT(t)
	cfg := &config.Config{ // #nosec G101 -- test-only smoke config placeholders.
		Port:               "8080",
		BackendURL:         "http://127.0.0.1:1", // parseable, never dialed by these probes
		RedisURL:           "redis://" + mr.Addr(),
		RevocationRedisURL: "redis://" + mr.Addr(),
		JWTSecret:          "smoke-test-jwt-secret-at-least-32-chars-long", // ≥32 chars, avoids os.Exit
		RateLimitRPS:       100,
		RateLimitBurst:     200,
		AllowedOrigins:     []string{"http://localhost:3000"},
		InternalHMACSecret: "smoke-internal-hmac-secret",
	}
	logger := slog.New(slog.NewTextHandler(io.Discard, nil))

	var router *gin.Engine
	var err error
	assert.NotPanics(t, func() {
		router, err = setupRouter(cfg, logger, nil, nil, t.Context())
		require.NoError(t, err)
	}, "setupRouter must wire a valid config without panicking or exiting")
	if router == nil {
		t.Fatal("setupRouter returned nil")
	}

	t.Run("health is public", func(t *testing.T) {
		rec := httptest.NewRecorder()
		router.ServeHTTP(rec, httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/health", nil))
		assert.Equal(t, http.StatusOK, rec.Code)
	})

	t.Run("protected v1 route without auth is 401", func(t *testing.T) {
		rec := httptest.NewRecorder()
		router.ServeHTTP(rec, httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/api/v1/users/me", nil))
		assert.Equal(t, http.StatusUnauthorized, rec.Code)
		assert.Contains(t, rec.Body.String(), "missing authorization header")
	})

	t.Run("unknown /api route is 404 JSON", func(t *testing.T) {
		rec := httptest.NewRecorder()
		router.ServeHTTP(rec, httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/api/totally/unknown", nil))
		assert.Equal(t, http.StatusNotFound, rec.Code)
		assert.Contains(t, rec.Body.String(), "endpoint not found")
	})

	t.Run("optional auth route reaches the backend proxy", func(t *testing.T) {
		rec := httptest.NewRecorder()
		router.ServeHTTP(rec, httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/api/v1/auth/csrf-cookie", nil))
		assert.Equal(t, http.StatusBadGateway, rec.Code)
	})

	t.Run("authenticated protected route reaches the backend proxy", func(t *testing.T) {
		rec := httptest.NewRecorder()
		req := httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/api/v1/users/me", nil)
		now := time.Now()
		token, err := jwt.NewWithClaims(jwt.SigningMethodHS256, jwt.MapClaims{
			"sub":       "user-1",
			"aud":       middleware.DefaultJWTAudience,
			"role":      "student",
			"jti":       "jti-1",
			"is_active": true,
			"iat":       now.Unix(),
			"exp":       now.Add(time.Hour).Unix(),
		}).SignedString([]byte("smoke-test-jwt-secret-at-least-32-chars-long"))
		require.NoError(t, err)
		req.Header.Set("Authorization", "Bearer "+token)
		router.ServeHTTP(rec, req)
		assert.Equal(t, http.StatusBadGateway, rec.Code)
	})

	t.Run("admin route aborts without authentication", func(t *testing.T) {
		rec := httptest.NewRecorder()
		router.ServeHTTP(rec, httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/api/admin/users", nil))
		assert.Equal(t, http.StatusUnauthorized, rec.Code)
	})

	t.Run("public and GraphQL optional routes reach the backend proxy", func(t *testing.T) {
		for _, path := range []string{"/api/public/config", "/graphql"} {
			rec := httptest.NewRecorder()
			router.ServeHTTP(rec, httptest.NewRequestWithContext(t.Context(), http.MethodGet, path, nil))
			assert.Equal(t, http.StatusBadGateway, rec.Code, path)
		}
	})

	t.Run("non-API no-route is proxied", func(t *testing.T) {
		rec := httptest.NewRecorder()
		router.ServeHTTP(rec, httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/unknown", nil))
		assert.Equal(t, http.StatusBadGateway, rec.Code)
	})
}

func TestInitLogger(t *testing.T) {
	logger := initLogger()
	assert.NotNil(t, logger)
}

func TestInitSentry(t *testing.T) {
	logger := slog.New(slog.NewTextHandler(io.Discard, nil))

	t.Run("disabled sentry", func(t *testing.T) {
		cfg := &config.Config{SentryDSN: ""}
		assert.NotPanics(t, func() {
			initSentry(cfg, logger)
		})
	})

	t.Run("invalid sentry dsn", func(t *testing.T) {
		cfg := &config.Config{SentryDSN: "invalid-dsn"}
		assert.NotPanics(t, func() {
			initSentry(cfg, logger)
		})
	})
}

func TestInitGRPC(t *testing.T) {
	logger := slog.New(slog.NewTextHandler(io.Discard, nil))
	cfg := &config.Config{
		FileProcessorAddr: "localhost:50051",
		GrpcUseTLS:        false,
	}
	conn, client, err := initGRPC(cfg, logger)
	require.NoError(t, err)
	assert.NotNil(t, conn)
	assert.NotNil(t, client)
	require.NoError(t, conn.Close())
}

func TestInitTracer_Failure(t *testing.T) {
	cfg := &config.Config{
		OtelEndpoint: "http://localhost:4317",
		GrpcUseTLS:   false,
	}
	tp, err := initTracer(context.Background(), cfg)
	if err == nil {
		assert.NotNil(t, tp)
		require.NoError(t, tp.Shutdown(context.Background()))
	}
}

func TestRunServer_Error(t *testing.T) {
	cfg := &config.Config{
		Port: "-1",
	}
	logger := slog.New(slog.NewTextHandler(io.Discard, nil))
	router := gin.New()
	assert.NotPanics(t, func() {
		require.Error(t, runServer(cfg, router, logger))
	})
}
