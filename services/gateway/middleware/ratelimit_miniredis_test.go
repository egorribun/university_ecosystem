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
	assert.NotNil(t, rl.GetClient())
}

func TestRateLimiter_Middleware_HealthExemptAndLimitEnforced(t *testing.T) {
	gin.SetMode(gin.TestMode)
	mr := miniredis.RunT(t)
	rl, err := NewRateLimiter(context.Background(), "redis://"+mr.Addr(), 1, 1)
	require.NoError(t, err)

	r := gin.New()
	r.Use(rl.Middleware(context.Background()))
	r.GET("/health", func(c *gin.Context) { c.Status(http.StatusOK) })
	r.GET("/api/thing", func(c *gin.Context) { c.Status(http.StatusOK) })

	// Health path bypasses the limiter entirely — always 200.
	for i := 0; i < 5; i++ {
		w := httptest.NewRecorder()
		req := httptest.NewRequest(http.MethodGet, "/health", nil)
		r.ServeHTTP(w, req)
		require.Equal(t, http.StatusOK, w.Code)
	}

	// Non-exempt path at rps=1: at least one request passes and the limiter
	// eventually returns 429 (true whether redis_rate or the in-memory fallback
	// does the limiting).
	var got200, got429 bool
	for i := 0; i < 12; i++ {
		w := httptest.NewRecorder()
		req := httptest.NewRequest(http.MethodGet, "/api/thing", nil)
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
