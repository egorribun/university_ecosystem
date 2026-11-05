package main

import (
	"context"
	"fmt"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/gin-gonic/gin"
	"github.com/stretchr/testify/require"
	"github.com/university-ecosystem/gateway/internal/config"
	"github.com/university-ecosystem/gateway/middleware"
)

// gatewayRateLimitedRouter composes the production trusted-proxy configuration with
// the production pre-auth IP limiter, so the proof covers the whole edge chain
// rather than the key helper alone (AUD-167).
func gatewayRateLimitedRouter(t *testing.T, trustedProxies []string) *gin.Engine {
	t.Helper()
	gin.SetMode(gin.TestMode)
	ctx, cancel := context.WithCancel(context.Background())
	t.Cleanup(cancel)
	router := gin.New()
	require.NoError(t, configureTrustedProxies(router, &config.Config{TrustedProxies: trustedProxies}))
	limiter := middleware.NewFallbackRateLimiter()
	t.Cleanup(func() { require.NoError(t, limiter.Close()) })
	router.Use(limiter.Middleware(ctx))
	router.GET("/api/v1/resource", func(c *gin.Context) { c.Status(http.StatusNoContent) })
	return router
}

func gatewayRequestStatus(t *testing.T, router *gin.Engine, remoteAddr, forwardedFor string) int {
	t.Helper()
	request := httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/api/v1/resource", nil)
	request.RemoteAddr = remoteAddr
	if forwardedFor != "" {
		request.Header.Set("X-Forwarded-For", forwardedFor)
	}
	recorder := httptest.NewRecorder()
	router.ServeHTTP(recorder, request)
	return recorder.Code
}

// TestAUD167TwoClientsBehindTrustedProxyHaveSeparateRateLimitKeys: both clients
// reach the gateway through the same trusted proxy. Exhausting the first client's
// budget must not throttle the second, because each is keyed by its forwarded
// client address rather than the proxy address.
func TestAUD167TwoClientsBehindTrustedProxyHaveSeparateRateLimitKeys(t *testing.T) {
	router := gatewayRateLimitedRouter(t, []string{"10.200.0.0/24"})
	const proxy = "10.200.0.12:45678"

	for i := 0; i < 3; i++ {
		require.Equal(t, http.StatusNoContent, gatewayRequestStatus(t, router, proxy, "198.51.100.25"),
			fmt.Sprintf("client A request %d is within its budget", i+1))
	}
	require.Equal(t, http.StatusTooManyRequests, gatewayRequestStatus(t, router, proxy, "198.51.100.25"),
		"client A exceeds its own budget")
	require.Equal(t, http.StatusNoContent, gatewayRequestStatus(t, router, "10.200.0.12:45679", "198.51.100.26"),
		"client B behind the same proxy must have its own rate-limit key")
}

// TestAUD167SpoofedForwardedForFromUntrustedPeerDoesNotEscapeLimit: with no trusted
// proxies, a client that rotates X-Forwarded-For values is still one peer. Each
// spoofed value must not create a fresh key.
func TestAUD167SpoofedForwardedForFromUntrustedPeerDoesNotEscapeLimit(t *testing.T) {
	router := gatewayRateLimitedRouter(t, nil)
	const peer = "10.41.2.7:51234"

	for i := 0; i < 3; i++ {
		require.Equal(t, http.StatusNoContent, gatewayRequestStatus(t, router, peer, fmt.Sprintf("203.0.113.%d", i+1)))
	}
	require.Equal(t, http.StatusTooManyRequests, gatewayRequestStatus(t, router, peer, "203.0.113.99"),
		"a spoofed forwarded address from an untrusted peer must not reset its budget")
}

// TestAUD167RotatingSpoofedLeftmostHopBehindTrustedProxyCannotEscapeLimit: a
// client behind a trusted proxy controls only the leftmost X-Forwarded-For
// entries. The proxy appends the real client address on the right, so rotating
// the forged prefix must keep the same rate-limit key.
func TestAUD167RotatingSpoofedLeftmostHopBehindTrustedProxyCannotEscapeLimit(t *testing.T) {
	router := gatewayRateLimitedRouter(t, []string{"10.200.0.0/24"})
	const proxy = "10.200.0.12:45690"

	for i := 0; i < 3; i++ {
		forwarded := fmt.Sprintf("203.0.113.%d, 198.51.100.77", i+1)
		require.Equal(t, http.StatusNoContent, gatewayRequestStatus(t, router, proxy, forwarded),
			fmt.Sprintf("request %d is within the real client's budget", i+1))
	}
	require.Equal(t, http.StatusTooManyRequests,
		gatewayRequestStatus(t, router, proxy, "203.0.113.99, 198.51.100.77"),
		"a rotated forged prefix must not reset the real client's budget")
}

// A trusted hop may append a separate header field. The gateway must use the
// resulting complete chain, not a client-controlled first field.
func TestAUD167RotatingFirstForwardedFieldCannotEscapeLimit(t *testing.T) {
	router := gatewayRateLimitedRouter(t, []string{"10.200.0.12"})
	attempt := func(forged, client string) int {
		request := httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/api/v1/resource", nil)
		request.RemoteAddr = "10.200.0.12:45678"
		request.Header.Add("X-Forwarded-For", forged)
		request.Header.Add("X-Forwarded-For", client)
		recorder := httptest.NewRecorder()
		router.ServeHTTP(recorder, request)
		return recorder.Code
	}
	for i := 1; i <= 3; i++ {
		require.Equal(t, http.StatusNoContent, attempt(fmt.Sprintf("203.0.113.%d", i), "198.51.100.25"))
	}
	require.Equal(t, http.StatusTooManyRequests, attempt("203.0.113.4", "198.51.100.25"))
	require.Equal(t, http.StatusNoContent, attempt("203.0.113.5", "198.51.100.26"))
}
