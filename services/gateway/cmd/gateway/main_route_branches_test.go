package main

import (
	"context"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/golang-jwt/jwt/v5"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"github.com/university-ecosystem/gateway/internal/config"
)

const routeBranchJWTSecret = "route-branch-test-secret-at-least-32-chars-long" // #nosec G101 -- test-only JWT signing secret // pragma: allowlist secret

func newRouteBranchRouter(t *testing.T, wsHubURL string) (*gin.Engine, context.CancelFunc) {
	t.Helper()
	ctx, cancel := context.WithCancel(context.Background())
	cfg := &config.Config{
		BackendURL:         "http://127.0.0.1:1",
		WsHubURL:           wsHubURL,
		JWTSecret:          routeBranchJWTSecret,
		AllowedOrigins:     []string{"http://localhost"},
		InternalHMACSecret: "route-branch-internal-secret",
	}
	router, err := setupRouter(cfg, slog.New(slog.NewTextHandler(io.Discard, nil)), nil, nil, ctx)
	require.NoError(t, err)
	return router, cancel
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
