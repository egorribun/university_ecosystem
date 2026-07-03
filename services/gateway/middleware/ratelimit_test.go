package middleware

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/go-redis/redis_rate/v10"
	"github.com/redis/go-redis/v9"
	"github.com/stretchr/testify/assert"
)

func TestRateLimiter_GetClientKey_ReturnsUserIDWhenAuthenticated(t *testing.T) {
	gin.SetMode(gin.TestMode)

	rateLimiter := &RateLimiter{
		rps: 100,
	}

	router := gin.New()
	var capturedKey string
	router.GET("/test", func(c *gin.Context) {
		c.Set("user_id", "user-123")
		capturedKey = rateLimiter.getClientKey(c)
		c.Status(http.StatusOK)
	})

	request := httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/test", nil)
	recorder := httptest.NewRecorder()
	router.ServeHTTP(recorder, request)

	assert.Equal(t, "user:user-123", capturedKey)
}

func TestRateLimiter_GetClientKey_ReturnsIPWhenNotAuthenticated(t *testing.T) {
	gin.SetMode(gin.TestMode)

	rateLimiter := &RateLimiter{
		rps: 100,
	}

	router := gin.New()
	var capturedKey string
	router.GET("/test", func(c *gin.Context) {
		capturedKey = rateLimiter.getClientKey(c)
		c.Status(http.StatusOK)
	})

	request := httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/test", nil)
	request.RemoteAddr = "192.168.1.100:12345"
	recorder := httptest.NewRecorder()
	router.ServeHTTP(recorder, request)

	assert.Contains(t, capturedKey, "ip:")
}

func TestRateLimiter_GetClientKey_UsesXForwardedFor(t *testing.T) {
	gin.SetMode(gin.TestMode)

	rateLimiter := &RateLimiter{
		rps: 100,
	}

	router := gin.New()
	router.ForwardedByClientIP = true
	if err := router.SetTrustedProxies([]string{"127.0.0.1"}); err != nil {
		t.Fatalf("failed to set trusted proxies: %v", err)
	}

	var capturedKey string
	router.GET("/test", func(c *gin.Context) {
		capturedKey = rateLimiter.getClientKey(c)
		c.Status(http.StatusOK)
	})

	request := httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/test", nil)
	request.RemoteAddr = "127.0.0.1:1234"
	request.Header.Set("X-Forwarded-For", "10.0.0.1")
	recorder := httptest.NewRecorder()
	router.ServeHTTP(recorder, request)

	assert.Equal(t, "ip:10.0.0.1", capturedKey)
}

func TestRateLimiter_GetClientKey_TrimsWhitespaceFromForwardedIP(t *testing.T) {
	gin.SetMode(gin.TestMode)

	rateLimiter := &RateLimiter{
		rps: 100,
	}

	router := gin.New()
	router.ForwardedByClientIP = true
	if err := router.SetTrustedProxies([]string{"127.0.0.1"}); err != nil {
		t.Fatalf("failed to set trusted proxies: %v", err)
	}

	var capturedKey string
	router.GET("/test", func(c *gin.Context) {
		capturedKey = rateLimiter.getClientKey(c)
		c.Status(http.StatusOK)
	})

	request := httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/test", nil)
	request.RemoteAddr = "127.0.0.1:1234"
	request.Header.Set("X-Forwarded-For", " 172.16.0.1 ")
	recorder := httptest.NewRecorder()
	router.ServeHTTP(recorder, request)

	assert.Equal(t, "ip:172.16.0.1", capturedKey)
}

func TestRateLimiter_GetClientKey_PrefersUserIDOverIP(t *testing.T) {
	gin.SetMode(gin.TestMode)

	rateLimiter := &RateLimiter{
		rps: 100,
	}

	router := gin.New()
	var capturedKey string
	router.GET("/test", func(c *gin.Context) {
		c.Set("user_id", "authenticated-user")
		capturedKey = rateLimiter.getClientKey(c)
		c.Status(http.StatusOK)
	})

	request := httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/test", nil)
	request.Header.Set("X-Forwarded-For", "10.0.0.1")
	request.RemoteAddr = "192.168.1.1:12345"
	recorder := httptest.NewRecorder()
	router.ServeHTTP(recorder, request)

	assert.Equal(t, "user:authenticated-user", capturedKey)
}

func TestRateLimiter_StructFields(t *testing.T) {
	rl := &RateLimiter{
		rps: 50,
	}

	assert.Equal(t, 50, rl.rps)
}

func TestRateLimiter_InMemoryAllow_LimitsCorrectly(t *testing.T) {
	rl := &RateLimiter{
		fallbackCounters: make(map[string]*fallbackEntry),
		fallbackLimit:    3,
		fallbackWindow:   60,
	}

	// 1st request
	assert.True(t, rl.inMemoryAllow("client-1"))
	// 2nd request
	assert.True(t, rl.inMemoryAllow("client-1"))
	// 3rd request
	assert.True(t, rl.inMemoryAllow("client-1"))
	// 4th request -> blocked
	assert.False(t, rl.inMemoryAllow("client-1"))
}

func TestRateLimiter_InMemoryAllow_ResetsAfterWindow(t *testing.T) {
	rl := &RateLimiter{
		fallbackCounters: make(map[string]*fallbackEntry),
		fallbackLimit:    2,
		fallbackWindow:   1, // 1 second window
	}

	assert.True(t, rl.inMemoryAllow("client-1"))
	assert.True(t, rl.inMemoryAllow("client-1"))
	assert.False(t, rl.inMemoryAllow("client-1")) // blocked

	// Sleep for 1.1s to cross the 1s window boundary
	time.Sleep(1100 * time.Millisecond)

	// Should be allowed again
	assert.True(t, rl.inMemoryAllow("client-1"))
}

func TestRateLimiter_IsHealthPath(t *testing.T) {
	assert.True(t, isHealthPath("/health"))
	assert.True(t, isHealthPath("/readiness"))
	assert.True(t, isHealthPath("/metrics"))
	assert.False(t, isHealthPath("/api/v1/some-resource"))
}

func TestRateLimiter_Middleware_InMemoryFallbackOnRedisError(t *testing.T) {
	gin.SetMode(gin.TestMode)

	// Setup RateLimiter with invalid Redis client to trigger Redis connection error
	rl := &RateLimiter{
		client:           nil,
		limiter:          redis_rate.NewLimiter(redis.NewClient(&redis.Options{Addr: "localhost:1"})),
		rps:              5,
		fallbackCounters: make(map[string]*fallbackEntry),
		fallbackLimit:    2,
		fallbackWindow:   60,
	}

	router := gin.New()
	router.GET("/test", rl.Middleware(context.Background()), func(c *gin.Context) {
		c.Status(http.StatusOK)
	})

	// Make 1st request -> should pass (Redis fails, fallback allows 1st)
	req1 := httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/test", nil)
	w1 := httptest.NewRecorder()
	router.ServeHTTP(w1, req1)
	assert.Equal(t, http.StatusOK, w1.Code)

	// Make 2nd request -> should pass (fallback allows 2nd)
	req2 := httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/test", nil)
	w2 := httptest.NewRecorder()
	router.ServeHTTP(w2, req2)
	assert.Equal(t, http.StatusOK, w2.Code)

	// Make 3rd request -> should be blocked (Too Many Requests)
	req3 := httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/test", nil)
	w3 := httptest.NewRecorder()
	router.ServeHTTP(w3, req3)
	assert.Equal(t, http.StatusTooManyRequests, w3.Code)
}

func TestNewRateLimiter_InvalidURLReturnsError(t *testing.T) {
	// redis.ParseURL fails immediately on a malformed scheme — no network,
	// covering the early error arm without a live Redis.
	rl, err := NewRateLimiter(context.Background(), "://not-a-valid-url", 10, 20)
	assert.Error(t, err)
	assert.Nil(t, rl)
}

func TestRateLimiter_GetClient_ReturnsUnderlyingClient(t *testing.T) {
	// redis.NewClient does not dial, so a white-box struct literal is enough.
	client := redis.NewClient(&redis.Options{Addr: "localhost:6379"})
	rl := &RateLimiter{client: client}
	assert.Same(t, client, rl.GetClient())
}

func TestRateLimiter_StartFallbackCleanup(t *testing.T) {
	rl := &RateLimiter{
		fallbackCounters: make(map[string]*fallbackEntry),
		fallbackLimit:    2,
		fallbackWindow:   1, // 1 second window
		cleanupInterval:  10 * time.Millisecond,
	}

	rl.fallbackMu.Lock()
	rl.fallbackCounters["expired-client"] = &fallbackEntry{
		count:       1,
		windowStart: time.Now().Unix() - 10, // 10s ago, definitely expired!
	}
	rl.fallbackCounters["fresh-client"] = &fallbackEntry{
		count:       1,
		windowStart: time.Now().Unix(), // fresh
	}
	rl.fallbackMu.Unlock()

	ctx, cancel := context.WithCancel(context.Background())
	rl.startFallbackCleanup(ctx)

	// Sleep to let ticker fire
	time.Sleep(50 * time.Millisecond)
	cancel() // Stop the loop

	rl.fallbackMu.Lock()
	defer rl.fallbackMu.Unlock()

	_, expiredExists := rl.fallbackCounters["expired-client"]
	_, freshExists := rl.fallbackCounters["fresh-client"]

	assert.False(t, expiredExists, "expired entry should be cleaned up")
	assert.True(t, freshExists, "fresh entry should remain")
}
