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
	"github.com/go-redis/redis_rate/v10"
	"github.com/golang-jwt/jwt/v5"
	"github.com/redis/go-redis/v9"
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

	t.Run("public image reads reach the backend without JWT", func(t *testing.T) {
		for _, method := range []string{http.MethodGet, http.MethodHead} {
			rec := httptest.NewRecorder()
			router.ServeHTTP(rec, httptest.NewRequestWithContext(t.Context(), method, "/api/v1/img/avatars/user.png", nil))
			assert.Equal(t, http.StatusBadGateway, rec.Code, method)
		}
		for _, probe := range []struct {
			method string
			path   string
		}{
			{method: http.MethodPost, path: "/api/v1/img/avatars/user.png"},
			{method: http.MethodGet, path: "/api/v1/images/avatars/user.png"},
		} {
			rec := httptest.NewRecorder()
			router.ServeHTTP(rec, httptest.NewRequestWithContext(t.Context(), probe.method, probe.path, nil))
			assert.Equal(t, http.StatusUnauthorized, rec.Code, probe.path)
		}
	})

	t.Run("CWV export is OIDC-authenticated by backend only", func(t *testing.T) {
		rec := httptest.NewRecorder()
		req := httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/api/v1/cwv/export", nil)
		req.Header.Set("Authorization", "Bearer github-oidc-token")
		router.ServeHTTP(rec, req)
		assert.Equal(t, http.StatusBadGateway, rec.Code)

		for _, probe := range []struct {
			method string
			path   string
		}{
			{method: http.MethodPost, path: "/api/v1/cwv/export"},
			{method: http.MethodPost, path: "/api/v1/cwv/envelope"},
			{method: http.MethodPost, path: "/api/v1/cwv/observations"},
		} {
			rejected := httptest.NewRecorder()
			router.ServeHTTP(
				rejected,
				httptest.NewRequestWithContext(t.Context(), probe.method, probe.path, nil),
			)
			assert.Equal(t, http.StatusUnauthorized, rejected.Code, probe.path)
		}
	})

	t.Run("authenticated protected route reaches the backend proxy", func(t *testing.T) {
		rec := httptest.NewRecorder()
		req := httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/api/v1/users/me", nil)
		now := time.Now()
		token, err := jwt.NewWithClaims(jwt.SigningMethodHS256, jwt.MapClaims{
			"sub":       "user-1",
			"iss":       middleware.DefaultJWTIssuer,
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

	t.Run("public optional route reaches the backend proxy", func(t *testing.T) {
		rec := httptest.NewRecorder()
		router.ServeHTTP(rec, httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/api/public/config", nil))
		assert.Equal(t, http.StatusBadGateway, rec.Code)
	})

	t.Run("retired backend GraphQL paths and URL aliases return local 404", func(t *testing.T) {
		for _, path := range []string{
			"/graphql",
			"/graphql/",
			"/graphql/query",
			"/GraphQL",
			"/GRAPHQL/query",
			"/%47raphql",
			"/gRaPhQl%2Fquery",
		} {
			rec := httptest.NewRecorder()
			router.ServeHTTP(rec, httptest.NewRequestWithContext(t.Context(), http.MethodGet, path, nil))
			assert.Equal(t, http.StatusNotFound, rec.Code, path)
		}
	})

	t.Run("non-API no-route remains proxied", func(t *testing.T) {
		for _, path := range []string{"/unknown", "/graphqlish"} {
			rec := httptest.NewRecorder()
			router.ServeHTTP(rec, httptest.NewRequestWithContext(t.Context(), http.MethodGet, path, nil))
			assert.Equal(t, http.StatusBadGateway, rec.Code, path)
		}
	})

	t.Run("AUD374 authenticated requests use verified per-user buckets behind the IP gate", func(t *testing.T) {
		// The front-door bucket remains per-IP and runs before authentication;
		// verified users also consume per-user buckets after auth.
		mr.FlushAll()
		mr.SetTime(time.Unix(1_700_000_000, 0))
		redisOptions, err := redis.ParseURL(cfg.RedisURL)
		require.NoError(t, err)
		redisClient := redis.NewClient(redisOptions)
		t.Cleanup(func() { require.NoError(t, redisClient.Close()) })
		seedLimiter := redis_rate.NewLimiter(redisClient)
		limit := redis_rate.Limit{
			Rate:   cfg.RateLimitRPS,
			Burst:  cfg.RateLimitBurst,
			Period: time.Second,
		}
		seedBucket := func(key string) {
			t.Helper()
			for requestNumber := 0; requestNumber < cfg.RateLimitBurst; requestNumber++ {
				result, allowErr := seedLimiter.Allow(t.Context(), key, limit)
				require.NoError(t, allowErr)
				require.Equal(t, 1, result.Allowed, "seed request %d for %s", requestNumber+1, key)
			}
			result, allowErr := seedLimiter.Allow(t.Context(), key, limit)
			require.NoError(t, allowErr)
			require.Zero(t, result.Allowed, "seeded bucket %s must reject the next request", key)
		}
		seedUserBucket := func(userID string) { seedBucket("user:" + userID) }
		makeToken := func(userID, tokenID, signingSecret string) string {
			t.Helper()
			now := time.Now()
			token, signErr := jwt.NewWithClaims(jwt.SigningMethodHS256, jwt.MapClaims{
				"sub":       userID,
				"iss":       middleware.DefaultJWTIssuer,
				"aud":       middleware.DefaultJWTAudience,
				"role":      "student",
				"jti":       tokenID,
				"is_active": true,
				"iat":       now.Unix(),
				"exp":       now.Add(time.Hour).Unix(),
			}).SignedString([]byte(signingSecret))
			require.NoError(t, signErr)
			return token
		}
		requestPath := func(path, token string) int {
			t.Helper()
			recorder := httptest.NewRecorder()
			req := httptest.NewRequestWithContext(t.Context(), http.MethodGet, path, nil)
			req.RemoteAddr = "198.51.100.44:45678"
			if token != "" {
				req.Header.Set("Authorization", "Bearer "+token)
			}
			router.ServeHTTP(recorder, req)
			return recorder.Code
		}
		request := func(token string) int { return requestPath("/api/v1/users/me", token) }

		seedUserBucket("aud374-user-a")
		validUserA := makeToken("aud374-user-a", "aud374-jti-a", cfg.JWTSecret)
		validUserB := makeToken("aud374-user-b", "aud374-jti-b", cfg.JWTSecret)
		invalidUserA := makeToken("aud374-user-a", "aud374-jti-forged", "wrong-signing-secret")

		assert.Equal(t, http.StatusTooManyRequests, request(validUserA), "a user's saturated identity bucket must reject that user")
		assert.Equal(t, http.StatusBadGateway, request(validUserB), "another user from the same client IP should pass the identity bucket")
		assert.Equal(t, http.StatusUnauthorized, request(invalidUserA), "an unverified subject must not select a user's bucket")

		mr.FlushAll()
		seedUserBucket("aud374-user-b")
		assert.Equal(t, http.StatusTooManyRequests, request(validUserB), "the second user's own saturated identity bucket must reject that user")

		mr.FlushAll()
		seedBucket("ip:198.51.100.44")
		assert.Equal(t, http.StatusTooManyRequests, request(invalidUserA), "the unchanged pre-auth IP gate must reject before JWT validation")

		mr.FlushAll()
		validAdmin := makeToken("aud374-admin", "aud374-jti-admin", cfg.JWTSecret)
		assert.Equal(t, http.StatusBadGateway, requestPath("/api/admin/users", validAdmin), "a verified admin route request should reach the backend")
		mr.FlushAll()
		seedUserBucket("aud374-admin")
		assert.Equal(t, http.StatusTooManyRequests, requestPath("/api/admin/users", validAdmin), "a saturated verified admin identity should abort at the user limiter")

		mr.FlushAll()
		validPublic := makeToken("aud374-public", "aud374-jti-public", cfg.JWTSecret)
		assert.Equal(t, http.StatusBadGateway, requestPath("/api/public/config", validPublic), "optional public auth should preserve verified identity when a token is present")
		mr.FlushAll()
		seedUserBucket("aud374-public")
		assert.Equal(t, http.StatusTooManyRequests, requestPath("/api/public/config", validPublic), "optional public auth should enforce a saturated verified user bucket")

		mr.FlushAll()
		assert.Equal(t, http.StatusBadGateway, requestPath("/ws/socket", ""), "non-ticket websocket routes remain owned by ws-hub")
		assert.Equal(t, http.StatusUnauthorized, requestPath("/ws/ticket", ""), "the ticket route requires a valid JWT")
		validTicket := makeToken("aud374-ticket", "aud374-jti-ticket", cfg.JWTSecret)
		assert.Equal(t, http.StatusBadGateway, requestPath("/ws/ticket", validTicket), "a verified ticket request should reach the backend")
		mr.FlushAll()
		seedUserBucket("aud374-ticket")
		assert.Equal(t, http.StatusTooManyRequests, requestPath("/ws/ticket", validTicket), "a saturated ticket identity should abort at the user limiter")
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
