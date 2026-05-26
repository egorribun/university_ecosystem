package middleware

import (
	"bytes"
	"context"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/stretchr/testify/require"
)

// TestGraphQLDepthAndTimeout covers RZ-24-05 — the depth limit and the request timeout.
func TestGraphQLDepthAndTimeout(t *testing.T) {
	inner := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("X-Test-Sleep") != "" {
			select {
			case <-time.After(2 * time.Second):
				w.WriteHeader(http.StatusOK)
				_, _ = w.Write([]byte(`{"data":"slow"}`)) //nolint:errcheck
			case <-r.Context().Done():
				http.Error(w, "context deadline exceeded", http.StatusGatewayTimeout)
			}
			return
		}
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`{"data":"ok"}`)) //nolint:errcheck
	})

	handler := MaxQueryDepthMiddleware(10, RequestTimeoutMiddleware(200*time.Millisecond, inner))
	server := httptest.NewServer(handler)
	t.Cleanup(server.Close)

	t.Run("depth_11_rejected", func(t *testing.T) {
		nested := strings.Repeat("a {", 11) + "x" + strings.Repeat(" }", 11)
		body := []byte(`{"query":"` + strings.ReplaceAll(nested, `"`, `\"`) + `"}`)

		req, err := http.NewRequestWithContext(context.Background(), http.MethodPost, server.URL, bytes.NewReader(body))
		require.NoError(t, err)
		req.Header.Set("Content-Type", "application/json")
		resp, err := http.DefaultClient.Do(req)
		require.NoError(t, err)
		defer func() { _ = resp.Body.Close() }() //nolint:errcheck // test cleanup
		respBytes, err := io.ReadAll(resp.Body)
		require.NoError(t, err)

		require.Equal(t, http.StatusBadRequest, resp.StatusCode)
		require.Contains(t, string(respBytes), "depth")
		require.Contains(t, string(respBytes), "exceeds maximum")
	})

	t.Run("depth_5_passes", func(t *testing.T) {
		body := []byte(`{"query":"{ a { b { c { d { e } } } } }"}`)
		req, err := http.NewRequestWithContext(context.Background(), http.MethodPost, server.URL, bytes.NewReader(body))
		require.NoError(t, err)
		req.Header.Set("Content-Type", "application/json")
		resp, err := http.DefaultClient.Do(req)
		require.NoError(t, err)
		defer func() { _ = resp.Body.Close() }() //nolint:errcheck // test cleanup
		respBytes, err := io.ReadAll(resp.Body)
		require.NoError(t, err)

		require.Equal(t, http.StatusOK, resp.StatusCode)
		require.Contains(t, string(respBytes), `"data":"ok"`)
	})

	t.Run("timeout_fires", func(t *testing.T) {
		body := []byte(`{"query":"{ a }"}`)
		req, err := http.NewRequestWithContext(context.Background(), http.MethodPost, server.URL, bytes.NewReader(body))
		require.NoError(t, err)
		req.Header.Set("Content-Type", "application/json")
		req.Header.Set("X-Test-Sleep", "1")

		start := time.Now()
		resp, err := http.DefaultClient.Do(req)
		elapsed := time.Since(start)
		require.NoError(t, err)
		defer func() { _ = resp.Body.Close() }() //nolint:errcheck // test cleanup

		require.Equal(t, http.StatusGatewayTimeout, resp.StatusCode)
		require.Less(t, elapsed, 1*time.Second)
	})
}
