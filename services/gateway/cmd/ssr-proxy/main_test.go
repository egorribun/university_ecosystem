package main

import (
	"context"
	"net"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"testing"
	"time"

	"github.com/spiffe/go-spiffe/v2/workloadapi"
	"github.com/stretchr/testify/require"
)

func proxyEnvironment() map[string]string {
	return map[string]string{
		"SSR_MTLS_ENABLED":        "true",
		"SSR_BACKEND_ORIGIN":      "https://backend:8000",
		"SPIFFE_ENDPOINT_SOCKET":  "unix:///run/spire/agent.sock",
		"SSR_SPIFFE_TRUST_DOMAIN": "university.ecosystem",
		"SSR_SPIFFE_ID":           "spiffe://university.ecosystem/frontend",
		"SSR_BACKEND_SPIFFE_ID":   "spiffe://university.ecosystem/backend",
	}
}

func TestProxyConfig(t *testing.T) {
	values := proxyEnvironment()
	cfg, err := readConfig(func(key string) string { return values[key] })
	require.NoError(t, err)
	require.Equal(t, "https://backend:8000", cfg.origin.String())
	require.Equal(t, "127.0.0.1:18000", listenAddress)
	for _, tc := range []struct{ key, value string }{
		{"SSR_MTLS_ENABLED", ""},
		{"SSR_MTLS_ENABLED", "TRUE"},
		{"SSR_BACKEND_ORIGIN", "http://backend:8000"},
		{"SSR_BACKEND_ORIGIN", "https://"},
		{"SSR_BACKEND_ORIGIN", "https://user:pass@backend"},
		{"SSR_BACKEND_ORIGIN", "https://backend/path"},
		{"SSR_BACKEND_ORIGIN", "https://backend?query"},
		{"SSR_BACKEND_ORIGIN", "https://backend?"},
		{"SSR_BACKEND_ORIGIN", "https://backend#fragment"},
		{"SSR_BACKEND_ORIGIN", "https://backend:invalid"},
		{"SPIFFE_ENDPOINT_SOCKET", ""},
		{"SPIFFE_ENDPOINT_SOCKET", "tcp://agent:8081"},
		{"SPIFFE_ENDPOINT_SOCKET", "unix://remote/run/agent.sock"},
		{"SPIFFE_ENDPOINT_SOCKET", "unix:///"},
		{"SPIFFE_ENDPOINT_SOCKET", "unix:///run/agent.sock?query"},
		{"SPIFFE_ENDPOINT_SOCKET", "unix:///%zz"},
		{"SSR_SPIFFE_TRUST_DOMAIN", ""},
		{"SSR_SPIFFE_ID", "invalid"},
		{"SSR_SPIFFE_ID", "spiffe://other.example/frontend"},
		{"SSR_SPIFFE_ID", "spiffe://university.ecosystem"},
		{"SSR_BACKEND_SPIFFE_ID", ""},
		{"SSR_BACKEND_SPIFFE_ID", "spiffe://other.example/backend"},
		{"SSR_BACKEND_SPIFFE_ID", "spiffe://university.ecosystem"},
		{"SSR_BACKEND_SPIFFE_ID", "spiffe://university.ecosystem/frontend"},
	} {
		t.Run(tc.key+"/"+tc.value, func(t *testing.T) {
			env := proxyEnvironment()
			env[tc.key] = tc.value
			_, err := readConfig(func(key string) string { return env[key] })
			require.Error(t, err)
		})
	}
}

func TestProxyLocalControlsDoNotDispatch(t *testing.T) {
	handler := newProxy(proxyConfig{}, func(context.Context) (*workloadapi.X509Context, error) {
		t.Fatal("local control must not fetch backend credentials")
		return nil, nil
	})
	for _, method := range []string{http.MethodConnect, http.MethodTrace} {
		response := httptest.NewRecorder()
		handler.ServeHTTP(response, httptest.NewRequest(method, "/", nil))
		require.Equal(t, http.StatusMethodNotAllowed, response.Code)
	}
	request := httptest.NewRequest(http.MethodGet, "/", nil)
	request.Header.Set("Upgrade", "websocket")
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, request)
	require.Equal(t, http.StatusMethodNotAllowed, response.Code)
	response = httptest.NewRecorder()
	handler.ServeHTTP(response, httptest.NewRequest(http.MethodGet, "/_ssr_proxy/live", nil))
	require.Equal(t, http.StatusOK, response.Code)
}

func TestProxyProbe(t *testing.T) {
	for _, status := range []int{http.StatusOK, http.StatusServiceUnavailable, http.StatusFound} {
		t.Run(http.StatusText(status), func(t *testing.T) {
			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				require.Equal(t, http.MethodGet, r.Method)
				require.Equal(t, "/health/ready", r.URL.Path)
				w.Header().Set("Location", "/must-not-follow")
				w.WriteHeader(status)
			}))
			defer server.Close()
			err := probe(context.Background(), server.URL+"/health/ready")
			if status == http.StatusOK {
				require.NoError(t, err)
			} else {
				require.Error(t, err)
			}
		})
	}
	require.Error(t, probe(context.Background(), "://invalid"))
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	require.Error(t, probe(ctx, "http://127.0.0.1:1"))
}

func TestProxyServeLifecycle(t *testing.T) {
	listener, err := net.Listen("tcp4", "127.0.0.1:0")
	require.NoError(t, err)
	ctx, cancel := context.WithCancel(context.Background())
	results := make(chan error, 1)
	go func() { results <- serve(ctx, listener, http.NotFoundHandler()) }()
	cancel()
	select {
	case err := <-results:
		require.NoError(t, err)
	case <-time.After(3 * time.Second):
		t.Fatal("server shutdown did not finish")
	}
	closed, err := net.Listen("tcp4", "127.0.0.1:0")
	require.NoError(t, err)
	require.NoError(t, closed.Close())
	require.Error(t, serve(context.Background(), closed, http.NotFoundHandler()))
}

func TestProxyExecuteRejectsInvalidInvocation(t *testing.T) {
	empty := func(string) string { return "" }
	require.ErrorContains(t, execute(context.Background(), []string{"unexpected"}, empty), "usage")
	require.ErrorContains(t, execute(context.Background(), nil, empty), "SSR_MTLS_ENABLED")
	cfg := proxyConfig{socket: "invalid://socket"}
	require.Error(t, run(context.Background(), cfg))
	values := proxyEnvironment()
	values["SPIFFE_ENDPOINT_SOCKET"] = "unix:///nonexistent/ssr-test.sock"
	cfg, err := readConfig(func(key string) string { return values[key] })
	require.NoError(t, err)
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	require.Error(t, run(ctx, cfg))
}

func TestProxyProbeCommandsStayOnLoopback(t *testing.T) {
	listener, err := net.Listen("tcp4", listenAddress)
	require.NoError(t, err)
	server := &http.Server{ReadHeaderTimeout: time.Second, Handler: http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		require.True(t, strings.HasPrefix(r.RemoteAddr, "127.0.0.1:"))
		if r.URL.Path != "/health/ready" && r.URL.Path != "/_ssr_proxy/live" {
			t.Errorf("unexpected probe path %s", r.URL.Path)
		}
		w.WriteHeader(http.StatusOK)
	})}
	done := make(chan error, 1)
	go func() { done <- server.Serve(listener) }()
	defer func() {
		require.NoError(t, server.Close())
		require.ErrorIs(t, <-done, http.ErrServerClosed)
	}()
	oldArgs, oldExit := os.Args, exitProcess
	t.Cleanup(func() { os.Args, exitProcess = oldArgs, oldExit })
	exitProcess = func(code int) { t.Errorf("unexpected exit %d", code) }
	os.Args = []string{"ssr-proxy", "probe"}
	main()
	for _, command := range []string{"probe", "live"} {
		require.NoError(t, execute(context.Background(), []string{command}, func(string) string {
			t.Fatal("probe must not inspect process configuration")
			return ""
		}))
	}
}

func TestProxyMainFailure(t *testing.T) {
	oldArgs, oldExit := os.Args, exitProcess
	t.Cleanup(func() { os.Args, exitProcess = oldArgs, oldExit })
	os.Args = []string{"ssr-proxy", "invalid"}
	exited := false
	exitProcess = func(code int) {
		exited = true
		require.Equal(t, 1, code)
	}
	main()
	require.True(t, exited)
}
