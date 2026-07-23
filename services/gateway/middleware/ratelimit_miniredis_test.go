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
	t.Cleanup(func() { _ = rl.Close() })
	assert.NotNil(t, rl.GetClient())
}

func TestRateLimiter_Middleware_HealthExemptAndLimitEnforced(t *testing.T) {
	gin.SetMode(gin.TestMode)
	mr := miniredis.RunT(t)
	rl, err := NewRateLimiter(context.Background(), "redis://"+mr.Addr(), 1, 1)
	require.NoError(t, err)
	t.Cleanup(func() { _ = rl.Close() })

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
