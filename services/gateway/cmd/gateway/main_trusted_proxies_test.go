package main

import (
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/gin-gonic/gin"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"github.com/university-ecosystem/gateway/internal/config"
)

func clientIPForTest(t *testing.T, cfg *config.Config, remoteAddr, forwardedFor string) string {
	t.Helper()
	gin.SetMode(gin.TestMode)
	router := gin.New()
	require.NoError(t, configureTrustedProxies(router, cfg))

	var clientIP string
	router.GET("/test", func(c *gin.Context) {
		clientIP = c.ClientIP()
		c.Status(http.StatusNoContent)
	})

	request := httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/test", nil)
	request.RemoteAddr = remoteAddr
	if forwardedFor != "" {
		request.Header.Set("X-Forwarded-For", forwardedFor)
	}
	recorder := httptest.NewRecorder()
	router.ServeHTTP(recorder, request)
	require.Equal(t, http.StatusNoContent, recorder.Code)
	return clientIP
}

func TestConfigureTrustedProxies_DoesNotTrustForwardedIPFromPrivatePeerByDefault(t *testing.T) {
	got := clientIPForTest(t, &config.Config{}, "10.41.2.7:45678", "198.51.100.77")

	assert.Equal(t, "10.41.2.7", got)
}

func TestConfigureTrustedProxies_PreservesClientIPThroughExplicitTrustedProxyChain(t *testing.T) {
	cfg := &config.Config{TrustedProxies: []string{"10.200.0.0/24"}}
	got := clientIPForTest(t, cfg, "10.200.0.12:45678", "198.51.100.25, 10.200.0.8")

	assert.Equal(t, "198.51.100.25", got)
}

func TestConfigureTrustedProxies_RejectsInvalidProxyRange(t *testing.T) {
	cfg := &config.Config{TrustedProxies: []string{"10.200.0.0/not-a-prefix"}}
	router := gin.New()

	err := configureTrustedProxies(router, cfg)

	require.Error(t, err)
}
