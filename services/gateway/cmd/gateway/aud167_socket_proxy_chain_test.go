package main

import (
	"io"
	"log/slog"
	"net"
	"net/http"
	"net/http/httptest"
	"net/http/httputil"
	"net/url"
	"testing"
	"time"

	"github.com/stretchr/testify/require"
)

// This exercises the production gateway router over sockets. The edge is a
// small reverse-proxy fixture that drops untrusted X-Forwarded-For and adds the
// observed socket peer; it is not a deployed Caddy or Compose topology.
func TestAUD167GatewaySocketProxySeparatesClientsAndRejectsSpoofs(t *testing.T) {
	type backendObservation struct {
		peer      string
		forwarded string
	}
	observed := make(chan backendObservation, 8)
	backend := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		peer, _, err := net.SplitHostPort(r.RemoteAddr)
		if err != nil {
			t.Errorf("backend peer: %v", err)
			w.WriteHeader(http.StatusInternalServerError)
			return
		}
		observed <- backendObservation{peer: peer, forwarded: r.Header.Get("X-Forwarded-For")}
		w.WriteHeader(http.StatusNoContent)
	}))
	t.Cleanup(backend.Close)

	cfg := minimalRouterConfig()
	cfg.BackendURL = backend.URL
	cfg.TrustedProxies = []string{"127.0.0.1"}
	// Invalid URLs select the production bounded fallback without external Redis.
	lifecycle := &routerLifecycle{}
	router, err := setupRouter(cfg, slog.New(slog.NewTextHandler(io.Discard, nil)), nil, nil, t.Context(), lifecycle)
	require.NoError(t, err)
	t.Cleanup(func() { require.NoError(t, lifecycle.Close()) })
	gatewayPeers := make(chan string, 16)
	gateway := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		peer, _, splitErr := net.SplitHostPort(r.RemoteAddr)
		if splitErr != nil {
			t.Errorf("gateway peer: %v", splitErr)
			w.WriteHeader(http.StatusInternalServerError)
			return
		}
		gatewayPeers <- peer
		router.ServeHTTP(w, r)
	}))
	t.Cleanup(gateway.Close)

	target, err := url.Parse(gateway.URL)
	require.NoError(t, err)
	proxy := &httputil.ReverseProxy{
		Rewrite: func(r *httputil.ProxyRequest) {
			r.SetURL(target)
			r.SetXForwarded()
			r.Out.Header.Set("X-Real-IP", r.In.RemoteAddr)
			if forwarded := r.In.Header.Get("Forwarded"); forwarded != "" {
				r.Out.Header.Set("Forwarded", forwarded)
			}
		},
		Transport: &http.Transport{DisableKeepAlives: true},
	}
	edgePeers := make(chan string, 16)
	edge := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		peer, _, splitErr := net.SplitHostPort(r.RemoteAddr)
		if splitErr != nil {
			t.Errorf("edge peer: %v", splitErr)
			w.WriteHeader(http.StatusInternalServerError)
			return
		}
		edgePeers <- peer
		proxy.ServeHTTP(w, r)
	}))
	t.Cleanup(edge.Close)

	request := func(source, destination string, headers map[string]string) int {
		t.Helper()
		transport := &http.Transport{
			DialContext:       (&net.Dialer{LocalAddr: &net.TCPAddr{IP: net.ParseIP(source)}}).DialContext,
			DisableKeepAlives: true,
		}
		defer transport.CloseIdleConnections()
		client := &http.Client{Transport: transport, Timeout: 5 * time.Second}
		req, requestErr := http.NewRequestWithContext(t.Context(), http.MethodGet, destination+"/api/v1/auth/login/json", nil)
		require.NoError(t, requestErr)
		for name, value := range headers {
			req.Header.Set(name, value)
		}
		resp, requestErr := client.Do(req)
		require.NoError(t, requestErr)
		require.NoError(t, resp.Body.Close())
		return resp.StatusCode
	}

	clientA, clientB := "127.0.0.2", "127.0.0.3"
	spoofs := []map[string]string{
		{"X-Forwarded-For": clientB},
		{"X-Real-IP": clientB},
		{"Forwarded": "for=" + clientB},
	}
	started := time.Now()
	for _, spoof := range spoofs {
		require.Equal(t, http.StatusNoContent, request(clientA, edge.URL, spoof))
		require.Equal(t, clientA, <-edgePeers)
		require.Equal(t, "127.0.0.1", <-gatewayPeers)
		got := <-observed
		require.Equal(t, "127.0.0.1", got.peer)
		require.Equal(t, clientA+", 127.0.0.1", got.forwarded)
	}
	require.Equal(t, http.StatusTooManyRequests, request(clientA, edge.URL, spoofs[0]))
	require.Equal(t, clientA, <-edgePeers)
	require.Equal(t, "127.0.0.1", <-gatewayPeers)
	require.Equal(t, http.StatusNoContent, request(clientB, edge.URL, nil))
	require.Equal(t, clientB, <-edgePeers)
	require.Equal(t, "127.0.0.1", <-gatewayPeers)
	got := <-observed
	require.Equal(t, "127.0.0.1", got.peer)
	require.Equal(t, clientB+", 127.0.0.1", got.forwarded)

	for _, spoof := range spoofs {
		require.Equal(t, http.StatusTooManyRequests, request(clientA, edge.URL, spoof))
		require.Equal(t, clientA, <-edgePeers)
		require.Equal(t, "127.0.0.1", <-gatewayPeers)
		require.Equal(t, http.StatusTooManyRequests, request(clientA, gateway.URL, spoof))
		require.Equal(t, clientA, <-gatewayPeers)
	}
	require.Less(t, time.Since(started), 60*time.Second, "requests must remain in the fallback window")
	require.Empty(t, observed, "blocked requests must not reach the backend")
}
