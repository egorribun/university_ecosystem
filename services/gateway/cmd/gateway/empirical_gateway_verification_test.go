package main

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"

	"github.com/university-ecosystem/gateway/internal/config"
)

// TestEmpirical_Gateway_AltSvcAndIngress verifies HTTP/3 Alt-Svc header injection and route proxying.
func TestEmpirical_Gateway_AltSvcAndIngress(t *testing.T) {
	// 1. Mock ws-hub backend server
	wsHubServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/ws":
			w.WriteHeader(http.StatusOK)
			//nolint:errcheck
			_, _ = w.Write([]byte("ws-upgraded"))
		case "/webtransport":
			w.WriteHeader(http.StatusOK)
			//nolint:errcheck
			_, _ = w.Write([]byte("wt-upgraded"))
		default:
			http.NotFound(w, r)
		}
	}))
	defer wsHubServer.Close()

	// 2. Test Gateway with H3Enabled = true
	t.Run("Alt-Svc Header Present when H3 Enabled", func(t *testing.T) {
		cfg := &config.Config{
			Port:               "8080",
			BackendURL:         wsHubServer.URL,
			WsHubURL:           wsHubServer.URL,
			JWTSecret:          "secret-key-at-least-32-chars-long",
			InternalHMACSecret: "test-internal-secret",
			H3Enabled:          true,
			H3Port:             "8443",
			H3AltSvcMaxAge:     2592000,
			AllowedOrigins:     []string{"*"},
			Environment:        "testing",
		}

		logger := initLogger()
		router, err := setupRouter(cfg, logger, nil, nil, context.Background())
		require.NoError(t, err)
		server := httptest.NewServer(router)
		defer server.Close()

		// Request health endpoint
		req, err := http.NewRequestWithContext(context.Background(), http.MethodGet, server.URL+"/health", nil)
		require.NoError(t, err)
		resp, err := http.DefaultClient.Do(req)
		require.NoError(t, err)
		//nolint:errcheck
		defer resp.Body.Close()

		assert.Equal(t, http.StatusOK, resp.StatusCode)
		assert.Equal(t, `h3=":8443"; ma=2592000`, resp.Header.Get("Alt-Svc"))

		// Request API endpoint
		reqAPI, err := http.NewRequestWithContext(context.Background(), http.MethodGet, server.URL+"/api/v1/health", nil)
		require.NoError(t, err)
		respAPI, err := http.DefaultClient.Do(reqAPI)
		require.NoError(t, err)
		//nolint:errcheck
		defer respAPI.Body.Close()

		assert.Equal(t, `h3=":8443"; ma=2592000`, respAPI.Header.Get("Alt-Svc"))
	})

	t.Run("Alt-Svc Header Absent when H3 Disabled", func(t *testing.T) {
		cfg := &config.Config{
			Port:               "8080",
			BackendURL:         wsHubServer.URL,
			WsHubURL:           wsHubServer.URL,
			JWTSecret:          "secret-key-at-least-32-chars-long",
			InternalHMACSecret: "test-internal-secret",
			H3Enabled:          false,
			AllowedOrigins:     []string{"*"},
			Environment:        "testing",
		}

		logger := initLogger()
		router, err := setupRouter(cfg, logger, nil, nil, context.Background())
		require.NoError(t, err)
		server := httptest.NewServer(router)
		defer server.Close()

		req, err := http.NewRequestWithContext(context.Background(), http.MethodGet, server.URL+"/health", nil)
		require.NoError(t, err)
		resp, err := http.DefaultClient.Do(req)
		require.NoError(t, err)
		//nolint:errcheck
		defer resp.Body.Close()

		assert.Equal(t, http.StatusOK, resp.StatusCode)
		assert.Empty(t, resp.Header.Get("Alt-Svc"))
	})

	t.Run("Proxy /ws and /webtransport to ws-hub", func(t *testing.T) {
		cfg := &config.Config{
			Port:               "8080",
			BackendURL:         wsHubServer.URL,
			WsHubURL:           wsHubServer.URL,
			JWTSecret:          "secret-key-at-least-32-chars-long",
			InternalHMACSecret: "test-internal-secret",
			H3Enabled:          true,
			H3Port:             "8443",
			H3AltSvcMaxAge:     2592000,
			AllowedOrigins:     []string{"*"},
			Environment:        "testing",
		}

		logger := initLogger()
		router, err := setupRouter(cfg, logger, nil, nil, context.Background())
		require.NoError(t, err)
		server := httptest.NewServer(router)
		defer server.Close()

		// /ws route proxy check
		reqWS, err := http.NewRequestWithContext(context.Background(), http.MethodGet, server.URL+"/ws?ticket=aabbcc", nil)
		require.NoError(t, err)
		resWS, err := http.DefaultClient.Do(reqWS)
		require.NoError(t, err)
		//nolint:errcheck
		defer resWS.Body.Close()
		assert.Equal(t, http.StatusOK, resWS.StatusCode)

		// /webtransport route proxy check
		reqWT, err := http.NewRequestWithContext(context.Background(), http.MethodGet, server.URL+"/webtransport?ticket=aabbcc", nil)
		require.NoError(t, err)
		resWT, err := http.DefaultClient.Do(reqWT)
		require.NoError(t, err)
		//nolint:errcheck
		defer resWT.Body.Close()
		assert.Equal(t, http.StatusOK, resWT.StatusCode)
	})
}
