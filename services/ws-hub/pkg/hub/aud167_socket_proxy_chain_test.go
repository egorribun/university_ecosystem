package hub

import (
	"net"
	"net/http"
	"net/http/httptest"
	"net/http/httputil"
	"net/url"
	"testing"
	"time"

	"github.com/stretchr/testify/require"
	"github.com/university-ecosystem/ws-hub/pkg/config"
)

// The real hub admission handler is reached through a socket reverse-proxy
// fixture, not Caddy or a deployed Compose topology. The fixture discards
// client-supplied X-Forwarded-For and forwards the observed socket address.
func TestAUD167WebSocketAdmissionThroughSocketProxy(t *testing.T) {
	h := setupTestHub()
	h.UpgradeLimiter.Stop()
	// Keep the production burst of 10 while avoiding a refill during slow CI.
	h.UpgradeLimiter = NewWSUpgradeRateLimiter(10, 3600)
	t.Cleanup(h.Stop)
	cfg := &config.Config{
		MaxClients:        100,
		TrustedProxiesSet: map[string]struct{}{"127.0.0.1": {}},
	}
	type hubObservation struct {
		peer      string
		forwarded string
		path      string
	}
	observed := make(chan hubObservation, 32)
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		peer, _, err := net.SplitHostPort(r.RemoteAddr)
		if err != nil {
			t.Errorf("hub peer: %v", err)
			w.WriteHeader(http.StatusInternalServerError)
			return
		}
		observed <- hubObservation{peer: peer, forwarded: r.Header.Get("X-Forwarded-For"), path: r.URL.Path}
		h.HandleWebSocket(w, r, cfg)
	}))
	t.Cleanup(upstream.Close)

	target, err := url.Parse(upstream.URL)
	require.NoError(t, err)
	proxy := &httputil.ReverseProxy{
		Rewrite: func(r *httputil.ProxyRequest) {
			r.SetURL(target)
			r.Out.URL.Path = "/ws"
			r.SetXForwarded()
			r.Out.Header.Set("X-Real-IP", r.In.RemoteAddr)
			if forwarded := r.In.Header.Get("Forwarded"); forwarded != "" {
				r.Out.Header.Set("Forwarded", forwarded)
			}
		},
		Transport: &http.Transport{DisableKeepAlives: true},
	}
	edgePeers := make(chan string, 32)
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

	request := func(source, destination, path string, headers map[string]string) int {
		t.Helper()
		transport := &http.Transport{
			DialContext:       (&net.Dialer{LocalAddr: &net.TCPAddr{IP: net.ParseIP(source)}}).DialContext,
			DisableKeepAlives: true,
		}
		defer transport.CloseIdleConnections()
		client := &http.Client{Transport: transport, Timeout: 5 * time.Second}
		req, requestErr := http.NewRequestWithContext(t.Context(), http.MethodGet, destination+path, nil)
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
	for i := 0; i < 10; i++ {
		require.Equal(t, http.StatusUnauthorized, request(clientA, edge.URL, "/ws/chat", spoofs[i%len(spoofs)]))
		require.Equal(t, clientA, <-edgePeers)
		got := <-observed
		require.Equal(t, "127.0.0.1", got.peer)
		require.Equal(t, clientA, got.forwarded)
		require.Equal(t, "/ws", got.path)
	}
	require.Equal(t, http.StatusTooManyRequests, request(clientA, edge.URL, "/ws/chat", nil))
	require.Equal(t, clientA, <-edgePeers)
	<-observed
	require.Equal(t, http.StatusUnauthorized, request(clientB, edge.URL, "/ws/chat", nil))
	require.Equal(t, clientB, <-edgePeers)
	got := <-observed
	require.Equal(t, "127.0.0.1", got.peer)
	require.Equal(t, clientB, got.forwarded)

	for _, spoof := range spoofs {
		require.Equal(t, http.StatusTooManyRequests, request(clientA, edge.URL, "/ws/chat", spoof))
		require.Equal(t, clientA, <-edgePeers)
		<-observed
		require.Equal(t, http.StatusTooManyRequests, request(clientA, upstream.URL, "/ws", spoof))
		got := <-observed
		require.Equal(t, clientA, got.peer)
	}
	require.Less(t, time.Since(started), 360*time.Second, "requests must not refill a token")
}
