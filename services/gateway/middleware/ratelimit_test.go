package middleware

import (
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/gin-gonic/gin"
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

	request := httptest.NewRequest(http.MethodGet, "/test", nil)
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

	request := httptest.NewRequest(http.MethodGet, "/test", nil)
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

	request := httptest.NewRequest(http.MethodGet, "/test", nil)
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

	request := httptest.NewRequest(http.MethodGet, "/test", nil)
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

	request := httptest.NewRequest(http.MethodGet, "/test", nil)
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
