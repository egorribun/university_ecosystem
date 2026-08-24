//go:build integration

// Package middleware integration tests, gated behind //go:build integration.
//
// Per ADR-022 — exercises real Redis containers via testcontainers-go to cover
// behavior the in-process fakes do not. Run via:
//
//	make test-integration
//
// or directly:
//
//	go test -tags integration -timeout 5m ./middleware/...
//
// Docker daemon must be reachable.
package middleware

import (
	"context"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"sync/atomic"
	"testing"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/stretchr/testify/require"
	"github.com/testcontainers/testcontainers-go"
	tclog "github.com/testcontainers/testcontainers-go/log"
	tcredis "github.com/testcontainers/testcontainers-go/modules/redis"
)

// startRedisContainerForRateLimit spins up a real redis:7.4.2-alpine container
// (exact prod docker-compose pin) and returns the connection URL plus a
// Terminate function. Mirrors the ws-hub helper pattern. The Terminate
// function is idempotent — safe to call from t.Cleanup AND mid-test.
//
// Per ADR-022 §"ownership stays with service code", this helper lives in the
// gateway test code and is NOT shared with other services. Each service owns
// only its specific test infrastructure.
func startRedisContainerForRateLimit(t *testing.T) (connStr string, terminate func()) {
	t.Helper()
	ctx := context.Background()

	rc, err := tcredis.Run(ctx, "redis:7.4.2-alpine@sha256:02419de7eddf55aa5bcf49efb74e88fa8d931b4d77c07eff8a6b2144472b6952",
		testcontainers.WithLogger(tclog.TestLogger(t)),
	)
	require.NoError(t, err)

	connStr, err = rc.ConnectionString(ctx)
	require.NoError(t, err)

	var terminated atomic.Bool
	terminate = func() {
		if terminated.Swap(true) {
			return // idempotent
		}
		_ = rc.Terminate(context.Background()) //nolint:errcheck // best-effort cleanup
	}
	t.Cleanup(terminate)
	return connStr, terminate
}

// TestIntegration_RateLimiterRedisInMemoryFallback verifies P0-W5-04 / RZ-22-06:
// when Redis becomes unavailable, the rate limiter falls back to a 3 req/60s
// in-memory limiter (NOT fail-open, NOT 503). The 4th fallback request gets
// 429 Too Many Requests with Retry-After: 60.
//
// This replaces the originally-planned RedisCircuitBreaker test, which doesn't
// apply to the Go gateway — CLAUDE.md PERF-30-01 references the Python backend's
// circuit_breaker.py, not the Go service. The gateway's resilience-pattern is
// the in-memory fallback, which this test now covers (per AskUserQuestion
// 2026-05-04 user-confirmed scope adjustment).
//
// Two-phase test:
//
//	Phase A: with Redis up, 5 requests succeed (rps=100, well under limit).
//	Phase B: terminate Redis, 4 requests — first 3 succeed via in-memory
//	         fallback (fallbackLimit=3 hardcoded at ratelimit.go:64), 4th
//	         gets 429 with Retry-After header set to fallbackWindow=60.
func TestIntegration_RateLimiterRedisInMemoryFallback(t *testing.T) {
	connStr, terminate := startRedisContainerForRateLimit(t)

	ctx, cancel := context.WithCancel(context.Background())
	t.Cleanup(cancel)

	// rps=100 keeps Phase A from hitting the Redis-side rate limit. The
	// fallback parameters (3 req/60s) are hardcoded in NewRateLimiter at
	// ratelimit.go:64-65 and not configurable.
	rl, err := NewRateLimiter(ctx, connStr, 100, 100)
	require.NoError(t, err, "NewRateLimiter must connect successfully on container start")
	t.Cleanup(func() { _ = rl.Close() })

	gin.SetMode(gin.TestMode)
	r := gin.New()
	r.Use(rl.Middleware(ctx))
	r.GET("/echo", func(c *gin.Context) {
		c.String(http.StatusOK, "ok")
	})

	server := httptest.NewServer(r)
	t.Cleanup(server.Close)

	doRequest := func(t *testing.T) (statusCode int, retryAfter string, body []byte) {
		t.Helper()
		// Use unique IP-equivalent header to ensure consistent client key.
		// Gin's ClientIP() will return the test server's loopback by default.
		req, err := http.NewRequestWithContext(ctx, http.MethodGet, server.URL+"/echo", nil) //nolint:gosec // G107 — variable URL is httptest.Server local URL
		require.NoError(t, err)
		resp, err := http.DefaultClient.Do(req)
		require.NoError(t, err)
		defer func() { _ = resp.Body.Close() }() //nolint:errcheck // best-effort body close
		body, _ = io.ReadAll(resp.Body)          //nolint:errcheck // body fully drained on next line
		return resp.StatusCode, resp.Header.Get("Retry-After"), body
	}

	// === Phase A: normal Redis-backed rate limiting works ===
	// 5 requests in fast succession — all should pass (rps=100 leaves plenty
	// of headroom on a single test client).
	for i := 0; i < 5; i++ {
		status, _, _ := doRequest(t)
		require.Equal(t, http.StatusOK, status,
			"phase A request %d under healthy Redis must pass with 200", i+1)
	}

	// === Phase B: terminate Redis to force the fallback path ===
	// After Terminate, the RateLimiter's internal client.Ping/Allow hits the
	// err != nil branch at ratelimit.go:146 and routes to inMemoryAllow.
	// fallbackLimit=3 (RZ-22-06), fallbackWindow=60s. First 3 from a fresh
	// in-memory window pass; 4th gets 429.
	terminate()

	// Give the rate limiter's internal client a moment to observe the
	// connection break (the next Allow() call will hit a Redis error and
	// fall through to inMemoryAllow). Empirically not strictly necessary —
	// the connection is severed at TCP level — but adds robustness.
	time.Sleep(50 * time.Millisecond)

	for i := 1; i <= 4; i++ {
		status, retryAfter, body := doRequest(t)
		if i <= 3 {
			require.Equal(t, http.StatusOK, status,
				"fallback request %d must pass via in-memory limiter", i)
		} else {
			require.Equal(t, http.StatusTooManyRequests, status,
				"4th fallback request must hit in-memory limit (3 req/60s)")
			require.Equal(t, "60", retryAfter,
				"Retry-After header must be 60 (fallbackWindow=60s) on fallback rejection")
			// Body shape per ratelimit.go:152-156:
			//   {"error":"rate_limit_exceeded","retry_after":60}
			var parsed map[string]any
			require.NoError(t, json.Unmarshal(body, &parsed),
				"response body must be valid JSON: got %s", string(body))
			require.Equal(t, "rate_limit_exceeded", parsed["error"])
			require.Equal(t, float64(60), parsed["retry_after"])
		}
	}
}
