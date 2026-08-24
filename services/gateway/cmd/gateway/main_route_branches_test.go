package main

import (
	"context"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/alicebob/miniredis/v2"
	"github.com/gin-gonic/gin"
	"github.com/golang-jwt/jwt/v5"
	"github.com/redis/go-redis/v9"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"github.com/university-ecosystem/gateway/internal/config"
	"github.com/university-ecosystem/gateway/middleware"
)

const routeBranchJWTSecret = "route-branch-test-secret-at-least-32-chars-long" // #nosec G101 -- test-only JWT signing secret // pragma: allowlist secret

func TestNewHealthyRedisClient(t *testing.T) {
	t.Run("connected", func(t *testing.T) {
		server := miniredis.RunT(t)
		client, err := newHealthyRedisClient(t.Context(), " redis://"+server.Addr()+" ")
		require.NoError(t, err)
		require.NotNil(t, client)
		require.NoError(t, client.Close())
	})

	t.Run("invalid URL", func(t *testing.T) {
		client, err := newHealthyRedisClient(t.Context(), "not-a-redis-url")
		assert.ErrorContains(t, err, "parse revocation Redis URL")
		assert.Nil(t, client)
	})

	t.Run("unreachable", func(t *testing.T) {
		client, err := newHealthyRedisClient(t.Context(), "redis://127.0.0.1:1")
		assert.ErrorContains(t, err, "connect to revocation Redis")
		assert.Nil(t, client)
	})
}

func TestSetupRouter_RejectsBlankRevocationRedisURL(t *testing.T) {
	redisServer := miniredis.RunT(t)
	cfg := &config.Config{
		BackendURL:         "http://127.0.0.1:1",
		WsHubURL:           "http://127.0.0.1:1",
		RedisURL:           "redis://" + redisServer.Addr() + "/3",
		RevocationRedisURL: "   ",
		JWTSecret:          routeBranchJWTSecret,
		AllowedOrigins:     []string{"http://localhost"},
		RateLimitRPS:       100,
		RateLimitBurst:     200,
	}

	router, err := setupRouter(
		cfg,
		slog.New(slog.NewTextHandler(io.Discard, nil)),
		nil,
		nil,
		t.Context(),
	)

	assert.Nil(t, router)
	assert.ErrorContains(t, err, "REVOCATION_REDIS_URL")
}

func TestSetupRouter_ClosesDedicatedRevocationRedisClientOnContextCancellation(t *testing.T) {
	redisServer := miniredis.RunT(t)
	ctx, cancel := context.WithCancel(context.Background())
	cfg := &config.Config{
		BackendURL:         "http://127.0.0.1:1",
		WsHubURL:           "http://127.0.0.1:1",
		RedisURL:           "redis://" + redisServer.Addr() + "/3",
		RevocationRedisURL: "redis://" + redisServer.Addr() + "/0",
		JWTSecret:          routeBranchJWTSecret,
		AllowedOrigins:     []string{"http://localhost"},
		RateLimitRPS:       100,
		RateLimitBurst:     200,
	}

	var revocationClient *redis.Client
	hooksMu.Lock()
	originalFactory := newRevocationRedisClientFunc
	newRevocationRedisClientFunc = func(ctx context.Context, redisURL string) (*redis.Client, error) {
		client, err := newHealthyRedisClient(ctx, redisURL)
		revocationClient = client
		return client, err
	}
	hooksMu.Unlock()
	t.Cleanup(func() {
		hooksMu.Lock()
		newRevocationRedisClientFunc = originalFactory
		hooksMu.Unlock()
	})

	router, err := setupRouter(
		cfg,
		slog.New(slog.NewTextHandler(io.Discard, nil)),
		nil,
		nil,
		ctx,
	)
	require.NoError(t, err)
	require.NotNil(t, router)
	require.NotNil(t, revocationClient)

	cancel()
	require.Eventually(t, func() bool {
		return revocationClient.Ping(t.Context()).Err() != nil
	}, time.Second, 10*time.Millisecond)
}

func TestRouterLifecycle_CloseIsSynchronousAndIdempotent(t *testing.T) {
	redisServer := miniredis.RunT(t)
	ctx, cancel := context.WithCancel(context.Background())
	lifecycle := &routerLifecycle{}
	cfg := &config.Config{
		BackendURL:         "http://127.0.0.1:1",
		WsHubURL:           "http://127.0.0.1:1",
		RedisURL:           "redis://" + redisServer.Addr() + "/3",
		RevocationRedisURL: "redis://" + redisServer.Addr() + "/0",
		JWTSecret:          routeBranchJWTSecret,
		AllowedOrigins:     []string{"http://localhost"},
		RateLimitRPS:       100,
		RateLimitBurst:     200,
	}

	router, err := setupRouter(
		cfg,
		slog.New(slog.NewTextHandler(io.Discard, nil)),
		nil,
		nil,
		ctx,
		lifecycle,
	)
	require.NoError(t, err)
	require.NotNil(t, router)
	require.NotNil(t, lifecycle.rateLimiter)
	require.NotNil(t, lifecycle.revocationRedisClient)

	cancel()
	require.NoError(t, lifecycle.Close())
	require.Error(t, lifecycle.rateLimiter.GetClient().Ping(t.Context()).Err())
	require.Error(t, lifecycle.revocationRedisClient.Ping(t.Context()).Err())
	require.NoError(t, lifecycle.Close())
}

func TestRouterLifecycle_CloseJoinsResourceErrors(t *testing.T) {
	hooksMu.Lock()
	originalRateLimiterClose := closeRateLimiterFunc
	originalRevocationClose := closeRevocationRedisClientFunc
	t.Cleanup(func() {
		hooksMu.Lock()
		closeRateLimiterFunc = originalRateLimiterClose
		closeRevocationRedisClientFunc = originalRevocationClose
		hooksMu.Unlock()
	})
	closeCalls := 0
	closeRateLimiterFunc = func(*middleware.RateLimiter) error {
		closeCalls++
		return errors.New("rate close failed")
	}
	closeRevocationRedisClientFunc = func(*redis.Client) error {
		closeCalls++
		return errors.New("revocation close failed")
	}
	hooksMu.Unlock()
	lifecycle := &routerLifecycle{
		rateLimiter:           &middleware.RateLimiter{},
		revocationRedisClient: redis.NewClient(&redis.Options{Addr: "127.0.0.1:1"}),
	}

	err := lifecycle.Close()
	require.ErrorContains(t, err, "rate close failed")
	require.ErrorContains(t, err, "revocation close failed")
	require.Equal(t, 2, closeCalls)
	require.EqualError(t, lifecycle.Close(), err.Error())
	require.Equal(t, 2, closeCalls, "idempotent close must not retry resources")
}

func newRouteBranchRouter(t *testing.T, wsHubURL string) (*gin.Engine, context.CancelFunc) {
	t.Helper()
	mr := miniredis.RunT(t)
	ctx, cancel := context.WithCancel(context.Background())
	cfg := &config.Config{
		BackendURL:         "http://127.0.0.1:1",
		WsHubURL:           wsHubURL,
		JWTSecret:          routeBranchJWTSecret,
		AllowedOrigins:     []string{"http://localhost"},
		InternalHMACSecret: "route-branch-internal-secret",
		RedisURL:           "redis://" + mr.Addr(),
		RevocationRedisURL: "redis://" + mr.Addr(),
		RateLimitRPS:       100,
		RateLimitBurst:     200,
	}
	router, err := setupRouter(cfg, slog.New(slog.NewTextHandler(io.Discard, nil)), nil, nil, ctx)
	require.NoError(t, err)
	return router, cancel
}

func newRouteBranchRouterWithUpstreams(t *testing.T, backendURL, wsHubURL string) (*gin.Engine, context.CancelFunc) {
	t.Helper()
	mr := miniredis.RunT(t)
	ctx, cancel := context.WithCancel(context.Background())
	cfg := &config.Config{
		BackendURL:         backendURL,
		WsHubURL:           wsHubURL,
		JWTSecret:          routeBranchJWTSecret,
		AllowedOrigins:     []string{"http://localhost"},
		InternalHMACSecret: "route-branch-internal-secret",
		RedisURL:           "redis://" + mr.Addr(),
		RevocationRedisURL: "redis://" + mr.Addr(),
		RateLimitRPS:       100,
		RateLimitBurst:     200,
	}
	router, err := setupRouter(cfg, slog.New(slog.NewTextHandler(io.Discard, nil)), nil, nil, ctx)
	require.NoError(t, err)
	return router, cancel
}

func signRouteBranchToken(t *testing.T, userID, jti string, isActive bool) string {
	t.Helper()
	now := time.Now()
	token, err := jwt.NewWithClaims(jwt.SigningMethodHS256, jwt.MapClaims{
		"sub":       userID,
		"aud":       middleware.DefaultJWTAudience,
		"role":      "student",
		"jti":       jti,
		"is_active": isActive,
		"iat":       now.Unix(),
		"exp":       now.Add(time.Hour).Unix(),
	}).SignedString([]byte(routeBranchJWTSecret))
	require.NoError(t, err)
	return token
}

func TestSetupRouter_AuthenticatedAdminRouteReachesProxy(t *testing.T) {
	router, cancel := newRouteBranchRouter(t, "http://127.0.0.1:1")
	t.Cleanup(cancel)

	server := httptest.NewServer(router)
	t.Cleanup(server.Close)
	req, err := http.NewRequestWithContext(
		context.Background(), http.MethodGet, server.URL+"/api/admin/users", nil,
	)
	require.NoError(t, err)
	token, err := jwt.NewWithClaims(jwt.SigningMethodHS256, jwt.MapClaims{
		"sub":       "user-1",
		"aud":       middleware.DefaultJWTAudience,
		"role":      "admin",
		"jti":       "route-jti-1",
		"is_active": true,
		"iat":       time.Now().Unix(),
		"exp":       time.Now().Add(time.Hour).Unix(),
	}).SignedString([]byte(routeBranchJWTSecret))
	require.NoError(t, err)
	req.Header.Set("Authorization", "Bearer "+token)
	response, err := server.Client().Do(req)
	require.NoError(t, err)
	if response == nil {
		t.Fatal("expected a response from the test server")
	}
	t.Cleanup(func() {
		if closeErr := response.Body.Close(); closeErr != nil {
			t.Errorf("close response body: %v", closeErr)
		}
	})

	assert.Equal(t, http.StatusBadGateway, response.StatusCode)
}

func TestSetupRouter_WSProxyErrorHandlerReturnsBadGateway(t *testing.T) {
	router, cancel := newRouteBranchRouter(t, "http://127.0.0.1:1")
	t.Cleanup(cancel)

	server := httptest.NewServer(router)
	t.Cleanup(server.Close)
	req, err := http.NewRequestWithContext(context.Background(), http.MethodGet, server.URL+"/ws", nil)
	require.NoError(t, err)
	response, err := server.Client().Do(req)
	require.NoError(t, err)
	if response == nil {
		t.Fatal("expected a response from the test server")
	}
	t.Cleanup(func() {
		if closeErr := response.Body.Close(); closeErr != nil {
			t.Errorf("close response body: %v", closeErr)
		}
	})

	assert.Equal(t, http.StatusBadGateway, response.StatusCode)
}

func TestSetupRouter_WSTicketUsesAuthenticatedBackendRoute(t *testing.T) {
	const (
		userID = "7c6e7d35-d8f8-4d89-bc93-41195151ab9f"
		jti    = "14e7c925-3b78-4f60-8f43-350c3a07f710"
	)

	type capturedRequest struct {
		authorization string
		cookie        string
		csrf          string
		userID        string
		sessionID     string
		tenantID      string
		signature     string
	}
	var captured capturedRequest
	backendHits := 0
	backend := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		backendHits++
		if r.URL.Path != "/ws/ticket" {
			http.NotFound(w, r)
			return
		}
		if r.Method != http.MethodPost {
			w.WriteHeader(http.StatusMethodNotAllowed)
			return
		}
		captured = capturedRequest{
			authorization: r.Header.Get("Authorization"),
			cookie:        r.Header.Get("Cookie"),
			csrf:          r.Header.Get("X-CSRF-Token"),
			userID:        r.Header.Get("X-User-ID"),
			sessionID:     r.Header.Get("X-Session-ID"),
			tenantID:      r.Header.Get("X-Tenant-ID"),
			signature:     r.Header.Get("X-Internal-Signature"),
		}
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusCreated)
		_, writeErr := w.Write([]byte(`{"ticket":"ticket-value","expires_in":15}`))
		assert.NoError(t, writeErr)
	}))
	t.Cleanup(backend.Close)

	wsHubHits := 0
	wsHub := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		wsHubHits++
		w.WriteHeader(http.StatusTeapot)
	}))
	t.Cleanup(wsHub.Close)

	router, cancel := newRouteBranchRouterWithUpstreams(t, backend.URL, wsHub.URL)
	t.Cleanup(cancel)
	server := httptest.NewServer(router)
	t.Cleanup(server.Close)

	token := signRouteBranchToken(t, userID, jti, true)
	req, err := http.NewRequestWithContext(t.Context(), http.MethodPost, server.URL+"/ws/ticket", nil)
	require.NoError(t, err)
	req.Header.Set("Authorization", "Bearer "+token)
	req.Header.Set("Cookie", "csrf_token=csrf-cookie; preference=dark")
	req.Header.Set("X-CSRF-Token", "csrf-cookie")
	req.Header.Set("X-User-ID", "spoofed-user")
	req.Header.Set("X-Session-ID", "spoofed-session")
	req.Header.Set("X-Tenant-ID", "00000000-0000-0000-0000-000000000999")
	req.Header.Set("X-Internal-Signature", "spoofed-signature")
	response, err := server.Client().Do(req)
	require.NoError(t, err)
	require.NotNil(t, response)
	t.Cleanup(func() { require.NoError(t, response.Body.Close()) })
	assert.Equal(t, http.StatusCreated, response.StatusCode)
	assert.Equal(t, 1, backendHits)
	assert.Zero(t, wsHubHits)
	assert.Equal(t, "Bearer "+token, captured.authorization)
	assert.Equal(t, "csrf_token=csrf-cookie; preference=dark", captured.cookie)
	assert.Equal(t, "csrf-cookie", captured.csrf)
	assert.Equal(t, userID, captured.userID)
	assert.Equal(t, jti, captured.sessionID)
	assert.Empty(t, captured.tenantID)
	mac := hmac.New(sha256.New, []byte("route-branch-internal-secret"))
	_, err = mac.Write([]byte(userID + ":" + jti))
	require.NoError(t, err)
	assert.Equal(t, hex.EncodeToString(mac.Sum(nil)), captured.signature)

	unauthReq, err := http.NewRequestWithContext(t.Context(), http.MethodPost, server.URL+"/ws/ticket", nil)
	require.NoError(t, err)
	unauthReq.Header.Set("Content-Type", "application/json")
	unauthenticated, err := server.Client().Do(unauthReq)
	require.NoError(t, err)
	require.NotNil(t, unauthenticated)
	t.Cleanup(func() { require.NoError(t, unauthenticated.Body.Close()) })
	assert.Equal(t, http.StatusUnauthorized, unauthenticated.StatusCode)
	assert.Equal(t, 1, backendHits)
	assert.Zero(t, wsHubHits)

	inactiveReq, err := http.NewRequestWithContext(t.Context(), http.MethodPost, server.URL+"/ws/ticket", nil)
	require.NoError(t, err)
	inactiveReq.Header.Set("Authorization", "Bearer "+signRouteBranchToken(t, userID, jti, false))
	inactiveResponse, err := server.Client().Do(inactiveReq)
	require.NoError(t, err)
	require.NotNil(t, inactiveResponse)
	t.Cleanup(func() { require.NoError(t, inactiveResponse.Body.Close()) })
	assert.Equal(t, http.StatusForbidden, inactiveResponse.StatusCode)
	assert.Equal(t, 1, backendHits)
	assert.Zero(t, wsHubHits)

	getReq, err := http.NewRequestWithContext(t.Context(), http.MethodGet, server.URL+"/ws/ticket", nil)
	require.NoError(t, err)
	getReq.Header.Set("Authorization", "Bearer "+token)
	getResponse, err := server.Client().Do(getReq)
	require.NoError(t, err)
	require.NotNil(t, getResponse)
	t.Cleanup(func() { require.NoError(t, getResponse.Body.Close()) })
	assert.Equal(t, http.StatusMethodNotAllowed, getResponse.StatusCode)
	assert.Equal(t, 2, backendHits)
	assert.Zero(t, wsHubHits)

	wsReq, err := http.NewRequestWithContext(t.Context(), http.MethodGet, server.URL+"/ws/chat", nil)
	require.NoError(t, err)
	wsResponse, err := server.Client().Do(wsReq)
	require.NoError(t, err)
	require.NotNil(t, wsResponse)
	t.Cleanup(func() { require.NoError(t, wsResponse.Body.Close()) })
	assert.Equal(t, http.StatusTeapot, wsResponse.StatusCode)
	assert.Equal(t, 1, wsHubHits)

	preflight, err := http.NewRequestWithContext(t.Context(), http.MethodOptions, server.URL+"/ws/ticket", nil)
	require.NoError(t, err)
	preflight.Header.Set("Origin", "http://localhost")
	preflight.Header.Set("Access-Control-Request-Method", http.MethodPost)
	preflight.Header.Set("Access-Control-Request-Headers", "x-csrf-token,x-requested-with")
	preflightResponse, err := server.Client().Do(preflight)
	require.NoError(t, err)
	require.NotNil(t, preflightResponse)
	t.Cleanup(func() { require.NoError(t, preflightResponse.Body.Close()) })
	assert.Equal(t, http.StatusNoContent, preflightResponse.StatusCode)
	allowedHeaders := strings.ToLower(preflightResponse.Header.Get("Access-Control-Allow-Headers"))
	assert.Contains(t, allowedHeaders, "x-csrf-token")
	assert.Contains(t, allowedHeaders, "x-requested-with")
	assert.Equal(t, 2, backendHits)
	assert.Equal(t, 1, wsHubHits)
}

func TestSetupRouter_RedisStartupFailureFailsAuthClosedAndKeepsRateLimit(t *testing.T) {
	backendHits := 0
	backend := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		backendHits++
		w.WriteHeader(http.StatusNoContent)
	}))
	t.Cleanup(backend.Close)

	ctx, cancel := context.WithCancel(context.Background())
	t.Cleanup(cancel)
	cfg := &config.Config{
		BackendURL:         backend.URL,
		WsHubURL:           backend.URL,
		RedisURL:           "",
		RevocationRedisURL: "not-a-redis-url",
		JWTSecret:          routeBranchJWTSecret,
		AllowedOrigins:     []string{"http://localhost"},
		InternalHMACSecret: "route-branch-internal-secret",
	}
	router, err := setupRouter(cfg, slog.New(slog.NewTextHandler(io.Discard, nil)), nil, nil, ctx)
	require.NoError(t, err)

	protected := httptest.NewRequestWithContext(t.Context(), http.MethodPost, "/ws/ticket", nil)
	protected.Header.Set(
		"Authorization",
		"Bearer "+signRouteBranchToken(t, "user-redis-down", "jti-redis-down", true),
	)
	protectedRecorder := httptest.NewRecorder()
	router.ServeHTTP(protectedRecorder, protected)
	assert.Equal(t, http.StatusServiceUnavailable, protectedRecorder.Code)
	assert.Zero(t, backendHits)

	for requestNumber := 1; requestNumber <= 3; requestNumber++ {
		recorder := httptest.NewRecorder()
		request := httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/public-fallback", nil)
		router.ServeHTTP(recorder, request)
		if requestNumber <= 2 {
			assert.Equal(t, http.StatusNoContent, recorder.Code)
			continue
		}
		assert.Equal(t, http.StatusTooManyRequests, recorder.Code)
		assert.Equal(t, "60", recorder.Header().Get("Retry-After"))
	}
	assert.Equal(t, 2, backendHits)
}

func TestSetupRouter_RateLimitOutageDoesNotDisableIndependentRevocationStore(t *testing.T) {
	backendHits := 0
	backend := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		backendHits++
		w.WriteHeader(http.StatusNoContent)
	}))
	t.Cleanup(backend.Close)

	revocationRedis := miniredis.RunT(t)
	ctx, cancel := context.WithCancel(context.Background())
	t.Cleanup(cancel)
	cfg := &config.Config{
		BackendURL:         backend.URL,
		WsHubURL:           backend.URL,
		RedisURL:           "redis://127.0.0.1:1",
		RevocationRedisURL: "redis://" + revocationRedis.Addr(),
		JWTSecret:          routeBranchJWTSecret,
		AllowedOrigins:     []string{"http://localhost"},
		InternalHMACSecret: "route-branch-internal-secret",
		RateLimitRPS:       100,
		RateLimitBurst:     200,
	}

	router, err := setupRouter(
		cfg,
		slog.New(slog.NewTextHandler(io.Discard, nil)),
		nil,
		nil,
		ctx,
	)
	require.NoError(t, err)

	request := httptest.NewRequestWithContext(t.Context(), http.MethodPost, "/ws/ticket", nil)
	request.Header.Set(
		"Authorization",
		"Bearer "+signRouteBranchToken(t, "user-rate-limit-down", "jti-rate-limit-down", true),
	)
	recorder := httptest.NewRecorder()
	router.ServeHTTP(recorder, request)

	assert.Equal(t, http.StatusNoContent, recorder.Code)
	assert.Equal(t, 1, backendHits)
}

func TestSetupRouter_RevocationStoreFailureRemainsFailClosed(t *testing.T) {
	rateLimitRedis := miniredis.RunT(t)
	ctx, cancel := context.WithCancel(context.Background())
	t.Cleanup(cancel)
	cfg := &config.Config{
		BackendURL:         "http://127.0.0.1:1",
		WsHubURL:           "http://127.0.0.1:1",
		RedisURL:           "redis://" + rateLimitRedis.Addr(),
		RevocationRedisURL: "not-a-redis-url",
		JWTSecret:          routeBranchJWTSecret,
		AllowedOrigins:     []string{"http://localhost"},
		InternalHMACSecret: "route-branch-internal-secret",
		RateLimitRPS:       100,
		RateLimitBurst:     200,
	}

	router, err := setupRouter(
		cfg,
		slog.New(slog.NewTextHandler(io.Discard, nil)),
		nil,
		nil,
		ctx,
	)
	require.NoError(t, err)

	request := httptest.NewRequestWithContext(t.Context(), http.MethodPost, "/ws/ticket", nil)
	request.Header.Set(
		"Authorization",
		"Bearer "+signRouteBranchToken(t, "user-revocation-down", "jti-revocation-down", true),
	)
	recorder := httptest.NewRecorder()
	router.ServeHTTP(recorder, request)

	assert.Equal(t, http.StatusServiceUnavailable, recorder.Code)
}

func TestSetupRouter_RevocationDBIsIndependentFromRateLimitDB(t *testing.T) {
	backendHits := 0
	backend := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		backendHits++
		w.WriteHeader(http.StatusNoContent)
	}))
	t.Cleanup(backend.Close)

	redisServer := miniredis.RunT(t)
	seedClient := redis.NewClient(&redis.Options{Addr: redisServer.Addr(), DB: 0})
	t.Cleanup(func() { require.NoError(t, seedClient.Close()) })
	const revokedJTI = "jti-in-canonical-db-zero"
	require.NoError(
		t,
		seedClient.Set(t.Context(), "revoked:jti:"+revokedJTI, "1", time.Hour).Err(),
	)

	ctx, cancel := context.WithCancel(context.Background())
	t.Cleanup(cancel)
	cfg := &config.Config{
		BackendURL:         backend.URL,
		WsHubURL:           backend.URL,
		RedisURL:           "redis://" + redisServer.Addr() + "/3",
		RevocationRedisURL: "redis://" + redisServer.Addr() + "/0",
		JWTSecret:          routeBranchJWTSecret,
		AllowedOrigins:     []string{"http://localhost"},
		InternalHMACSecret: "route-branch-internal-secret",
		RateLimitRPS:       100,
		RateLimitBurst:     200,
	}

	router, err := setupRouter(
		cfg,
		slog.New(slog.NewTextHandler(io.Discard, nil)),
		nil,
		nil,
		ctx,
	)
	require.NoError(t, err)

	request := httptest.NewRequestWithContext(t.Context(), http.MethodPost, "/ws/ticket", nil)
	request.Header.Set(
		"Authorization",
		"Bearer "+signRouteBranchToken(t, "user-revoked-db-zero", revokedJTI, true),
	)
	recorder := httptest.NewRecorder()
	router.ServeHTTP(recorder, request)

	assert.Equal(t, http.StatusUnauthorized, recorder.Code)
	assert.Zero(t, backendHits)
}
