package middleware

// Coverage tests (testing session 16) for the Redis-backed rate-limiter SUCCESS
// paths. The existing ratelimit_test.go covers getClientKey / inMemoryAllow /
// isHealthPath / the Redis-error fallback / the bad-URL error, but NewRateLimiter's
// Ping-OK path and Middleware's redis_rate.Allow success+headers+429 branches
// need a live Redis. miniredis runs the redis_rate GCRA Lua script (gopher-lua),
// so these execute without Docker.

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/alicebob/miniredis/v2"
	"github.com/gin-gonic/gin"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestNewRateLimiter_SuccessWithMiniredis(t *testing.T) {
	mr := miniredis.RunT(t)
	rl, err := NewRateLimiter(context.Background(), "redis://"+mr.Addr(), 10, 10)
	require.NoError(t, err)
	require.NotNil(t, rl)
	t.Cleanup(func() { assert.NoError(t, rl.Close()) })
	assert.NotNil(t, rl.GetClient())
}

func TestRateLimiter_Middleware_UsesConfiguredBurstPerClient(t *testing.T) {
	gin.SetMode(gin.TestMode)
	mr := miniredis.RunT(t)
	serverTime := time.Unix(1_700_000_000, 0)
	mr.SetTime(serverTime)
	rl, err := NewRateLimiter(context.Background(), "redis://"+mr.Addr(), 1, 3)
	require.NoError(t, err)
	t.Cleanup(func() { assert.NoError(t, rl.Close()) })

	r := gin.New()
	requestCtx, requestCancel := context.WithCancel(context.Background())
	t.Cleanup(requestCancel)
	r.Use(rl.Middleware(requestCtx))
	r.GET("/api/thing", func(c *gin.Context) { c.Status(http.StatusOK) })

	request := func(ip string) *httptest.ResponseRecorder {
		t.Helper()
		w := httptest.NewRecorder()
		req := httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/api/thing", nil)
		req.RemoteAddr = ip + ":1234"
		r.ServeHTTP(w, req)
		return w
	}

	for i := 0; i < 3; i++ {
		w := request("203.0.113.7")
		require.Equal(t, http.StatusOK, w.Code, "configured burst request %d", i+1)
		assert.Equal(t, "1", w.Header().Get("RateLimit-Limit"), "header remains the steady rate")
	}
	assert.Equal(t, http.StatusTooManyRequests, request("203.0.113.7").Code)
	assert.Equal(t, http.StatusOK, request("203.0.113.8").Code, "client buckets stay separate")

	mr.SetTime(serverTime.Add(time.Second))
	assert.Equal(t, http.StatusOK, request("203.0.113.7").Code, "the steady rate refills the burst")
}

func TestRateLimiter_Middleware_HealthExemptAndLimitEnforced(t *testing.T) {
	gin.SetMode(gin.TestMode)
	mr := miniredis.RunT(t)
	rl, err := NewRateLimiter(context.Background(), "redis://"+mr.Addr(), 1, 1)
	require.NoError(t, err)
	t.Cleanup(func() { assert.NoError(t, rl.Close()) })

	r := gin.New()
	requestCtx, requestCancel := context.WithCancel(context.Background())
	t.Cleanup(requestCancel)
	r.Use(rl.Middleware(requestCtx))
	r.GET("/health", func(c *gin.Context) { c.Status(http.StatusOK) })
	r.GET("/api/thing", func(c *gin.Context) { c.Status(http.StatusOK) })

	// Health path bypasses the limiter entirely — always 200.
	for i := 0; i < 5; i++ {
		w := httptest.NewRecorder()
		req := httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/health", nil)
		r.ServeHTTP(w, req)
		require.Equal(t, http.StatusOK, w.Code)
	}

	// Non-exempt path at rps=1: at least one request passes and the limiter
	// eventually returns 429 (true whether redis_rate or the in-memory fallback
	// does the limiting).
	var got200, got429 bool
	for i := 0; i < 12; i++ {
		w := httptest.NewRecorder()
		req := httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/api/thing", nil)
		req.RemoteAddr = "203.0.113.7:1234"
		r.ServeHTTP(w, req)
		switch w.Code {
		case http.StatusOK:
			got200 = true
		case http.StatusTooManyRequests:
			got429 = true
		}
	}
	assert.True(t, got200, "at least one request must be allowed")
	assert.True(t, got429, "rate limiter must eventually return 429")
}

func TestRateLimiter_StartFallbackCleanup_Cancel(t *testing.T) {
	rl := &RateLimiter{
		fallbackCounters: make(map[string]*fallbackEntry),
		fallbackLimit:    2,
		fallbackWindow:   1,
	}
	ctx, cancel := context.WithCancel(context.Background())
	rl.startFallbackCleanup(ctx)

	// Cancel context to stop the goroutine
	cancel()
	time.Sleep(10 * time.Millisecond)
}

func TestRateLimiter_GetClientKey_NonStringUserID(t *testing.T) {
	gin.SetMode(gin.TestMode)
	rl := &RateLimiter{rps: 100}

	router := gin.New()
	var capturedKey string
	router.GET("/test", func(c *gin.Context) {
		c.Set("user_id", 12345) // int instead of string
		capturedKey = rl.getClientKey(c)
		c.Status(http.StatusOK)
	})

	request := httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/test", nil)
	request.RemoteAddr = "192.168.1.100:12345"
	recorder := httptest.NewRecorder()
	router.ServeHTTP(recorder, request)

	assert.Contains(t, capturedKey, "ip:")
}

func TestRateLimiter_AuthenticatedMiddleware_RequiresVerifiedContext(t *testing.T) {
	gin.SetMode(gin.TestMode)

	t.Run("health stays exempt even for an authenticated identity", func(t *testing.T) {
		rl := &RateLimiter{
			fallbackCounters: map[string]*fallbackEntry{
				"user:alice": {count: 1, windowStart: time.Now().Unix()},
			},
			fallbackLimit:  1,
			fallbackWindow: 60,
		}
		t.Cleanup(func() { assert.NoError(t, rl.Close()) })
		router := gin.New()
		router.Use(func(c *gin.Context) {
			c.Set("user_id", "alice")
			c.Set("claims", &Claims{UserID: "alice"})
		})
		router.Use(rl.AuthenticatedMiddleware(t.Context()))
		router.GET("/health/ready", func(c *gin.Context) { c.Status(http.StatusOK) })

		response := httptest.NewRecorder()
		router.ServeHTTP(response, httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/health/ready", nil))
		assert.Equal(t, http.StatusOK, response.Code, "health probes must bypass even a saturated identity bucket")
		assert.Equal(t, int64(1), rl.fallbackCounters["user:alice"].count, "the health probe must not consume the identity bucket")
	})

	tests := []struct {
		name      string
		setUserID bool
		userID    any
		setClaims bool
		claims    any
	}{
		{name: "anonymous"},
		{name: "malformed user ID", setUserID: true, userID: 42, setClaims: true, claims: &Claims{UserID: "alice"}},
		{name: "empty user ID", setUserID: true, userID: "", setClaims: true, claims: &Claims{}},
		{name: "missing claims", setUserID: true, userID: "alice"},
		{name: "wrong claims type", setUserID: true, userID: "alice", setClaims: true, claims: map[string]string{"user_id": "alice"}},
		{name: "nil claims", setUserID: true, userID: "alice", setClaims: true, claims: (*Claims)(nil)},
		{name: "identity mismatch", setUserID: true, userID: "alice", setClaims: true, claims: &Claims{UserID: "bob"}},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			rl := &RateLimiter{
				fallbackCounters: make(map[string]*fallbackEntry),
				fallbackLimit:    1,
				fallbackWindow:   60,
			}
			t.Cleanup(func() { assert.NoError(t, rl.Close()) })
			router := gin.New()
			router.Use(func(c *gin.Context) {
				if tt.setUserID {
					c.Set("user_id", tt.userID)
				}
				if tt.setClaims {
					c.Set("claims", tt.claims)
				}
			})
			router.Use(rl.AuthenticatedMiddleware(t.Context()))
			router.GET("/api/thing", func(c *gin.Context) { c.Status(http.StatusOK) })

			response := httptest.NewRecorder()
			router.ServeHTTP(response, httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/api/thing", nil))
			assert.Equal(t, http.StatusOK, response.Code, "unverified context should continue under the pre-auth IP gate only")
			assert.Empty(t, rl.fallbackCounters, "unverified context must not create a user bucket")
		})
	}
}

func TestRateLimiter_AuthenticatedMiddleware_UsesVerifiedIdentityFallback(t *testing.T) {
	gin.SetMode(gin.TestMode)
	rl := &RateLimiter{
		fallbackCounters: make(map[string]*fallbackEntry),
		fallbackLimit:    1,
		fallbackWindow:   60,
	}
	t.Cleanup(func() { assert.NoError(t, rl.Close()) })
	router := gin.New()
	router.Use(func(c *gin.Context) {
		c.Set("user_id", "alice")
		c.Set("claims", &Claims{UserID: "alice"})
	})
	router.Use(rl.AuthenticatedMiddleware(t.Context()))
	router.GET("/api/thing", func(c *gin.Context) { c.Status(http.StatusOK) })

	request := func() *httptest.ResponseRecorder {
		t.Helper()
		response := httptest.NewRecorder()
		router.ServeHTTP(response, httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/api/thing", nil))
		return response
	}

	assert.Equal(t, http.StatusOK, request().Code, "first request for a verified identity should pass the existing fallback")
	blocked := request()
	assert.Equal(t, http.StatusTooManyRequests, blocked.Code, "the existing fallback should reject after the configured per-user allowance")
	assert.Equal(t, "60", blocked.Header().Get("Retry-After"))
	assert.Contains(t, rl.fallbackCounters, "user:alice")
	assert.NotContains(t, rl.fallbackCounters, "ip:", "the verified identity fallback should not create an IP-keyed second bucket")
}

func TestRateLimiter_AuthenticatedMiddleware_UsesRedisIdentityBucket(t *testing.T) {
	gin.SetMode(gin.TestMode)
	mr := miniredis.RunT(t)
	mr.SetTime(time.Unix(1_700_000_000, 0))
	rl, err := NewRateLimiter(context.Background(), "redis://"+mr.Addr(), 1, 1)
	require.NoError(t, err)
	t.Cleanup(func() { assert.NoError(t, rl.Close()) })

	requestCtx, cancel := context.WithCancel(context.Background())
	t.Cleanup(cancel)
	router := gin.New()
	router.Use(func(c *gin.Context) {
		c.Set("user_id", "alice")
		c.Set("claims", &Claims{UserID: "alice"})
	})
	router.Use(rl.AuthenticatedMiddleware(requestCtx))
	router.GET("/api/thing", func(c *gin.Context) { c.Status(http.StatusOK) })

	request := func() *httptest.ResponseRecorder {
		t.Helper()
		response := httptest.NewRecorder()
		router.ServeHTTP(response, httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/api/thing", nil))
		return response
	}

	assert.Equal(t, http.StatusOK, request().Code, "a verified identity should get the configured Redis burst")
	blocked := request()
	assert.Equal(t, http.StatusTooManyRequests, blocked.Code, "the verified identity Redis bucket must enforce 429")
	assert.Equal(t, "1", blocked.Header().Get("RateLimit-Limit"))
}
