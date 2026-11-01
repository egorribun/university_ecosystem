package main

import (
	"io"
	"log/slog"
	"net"
	"net/http"
	"testing"
	"time"

	"github.com/stretchr/testify/require"
	"github.com/university-ecosystem/ws-hub/pkg/config"
	"github.com/university-ecosystem/ws-hub/pkg/hub"
)

// aud438Status fetches url and returns the HTTP status code.
func aud438Status(t *testing.T, url string) int {
	t.Helper()
	request, err := http.NewRequestWithContext(t.Context(), http.MethodGet, url, nil)
	require.NoError(t, err)
	response, err := http.DefaultClient.Do(request)
	require.NoError(t, err)
	defer func() { require.NoError(t, response.Body.Close()) }()
	return response.StatusCode
}

// TestAUD438MetricsListenerIsolatedOnSocket serves the public WebSocket mux and the
// metrics listener on separate real sockets, as runServer does. The unauthenticated
// scrape endpoint must be reachable only on the metrics socket (AUD-438).
func TestAUD438MetricsListenerIsolatedOnSocket(t *testing.T) {
	logger := slog.New(slog.NewTextHandler(io.Discard, nil))
	cfg := &config.Config{}
	h := hub.NewHub(nil, logger, nil, cfg, nil, nil)
	mux := http.NewServeMux()
	setupHandlers(mux, h, cfg, logger, nil, nil)

	publicListener, err := net.Listen("tcp", "127.0.0.1:0")
	require.NoError(t, err)
	public := &http.Server{Handler: mux, ReadHeaderTimeout: 5 * time.Second}
	go func() { _ = public.Serve(publicListener) }()
	t.Cleanup(func() { _ = public.Close() })

	metricsListener, err := net.Listen("tcp", "127.0.0.1:0")
	require.NoError(t, err)
	metrics := newMetricsServer(metricsListener.Addr().String())
	go func() { _ = metrics.Serve(metricsListener) }()
	t.Cleanup(func() { _ = metrics.Close() })

	publicBase := "http://" + publicListener.Addr().String()
	metricsBase := "http://" + metricsListener.Addr().String()
	require.Equal(t, http.StatusNotFound, aud438Status(t, publicBase+"/metrics"),
		"the public listener must not serve unauthenticated metrics")
	require.Equal(t, http.StatusOK, aud438Status(t, metricsBase+"/metrics"),
		"the metrics listener serves the scrape endpoint")
	for _, path := range []string{"/ws", "/ws/chat", "/health/live", "/health/ready"} {
		require.Equal(t, http.StatusNotFound, aud438Status(t, metricsBase+path),
			"the metrics listener must not expose "+path)
	}
}
