//go:build integration

// Package middleware integration tests, gated behind //go:build integration.
//
// Per ADR-022 — exercises the GraphQL middleware chain configured at
// cmd/file-processor/main.go:308:
//
//	MaxQueryDepthMiddleware(10, RequestTimeoutMiddleware(30s, &relay.Handler{...}))
//
// against an httptest.Server with a stub inner handler. No external containers
// are required — depth + timeout middleware is self-contained.
package middleware

import (
	"bytes"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/stretchr/testify/require"
)

// TestIntegration_GraphQLDepthAndTimeout covers RZ-24-05 — the depth limit
// (production: 10, hardcoded at main.go:308) and the request timeout
// (production: 30s, same call site). The test uses a 200ms timeout instead of
// 30s for fast feedback while exercising the SAME middleware functions.
//
// Three sub-tests:
//  1. depth_11_rejected — query nesting depth 11 hits the limit and returns
//     400 Bad Request with a JSON errors body containing "depth".
//  2. depth_5_passes — query nesting depth 5 (well under limit 10) passes
//     through to the inner handler.
//  3. timeout_fires — inner handler that intentionally exceeds the timeout
//     causes the request context to be cancelled. The handler honors
//     ctx.Done() and returns 504; the response is observed within 200ms,
//     not the 2s the handler would have slept.
func TestIntegration_GraphQLDepthAndTimeout(t *testing.T) {
	// Inner handler: echoes "ok" or sleeps based on a special header. When the
	// context is cancelled mid-sleep (timeout middleware fires), returns 504.
	inner := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("X-Test-Sleep") != "" {
			select {
			case <-time.After(2 * time.Second):
				w.WriteHeader(http.StatusOK)
				_, _ = w.Write([]byte(`{"data":"slow"}`))
			case <-r.Context().Done():
				// Production middleware uses context.WithTimeout; downstream
				// handlers honor the deadline by listening on ctx.Done().
				http.Error(w, "context deadline exceeded", http.StatusGatewayTimeout)
			}
			return
		}
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`{"data":"ok"}`))
	})

	// Production wiring (matches cmd/file-processor/main.go:308). Use 200ms
	// timeout instead of 30s to keep the test fast — the middleware function
	// itself is identical.
	handler := MaxQueryDepthMiddleware(10, RequestTimeoutMiddleware(200*time.Millisecond, inner))
	server := httptest.NewServer(handler)
	t.Cleanup(server.Close)

	// Sub-test 1: depth 11 query rejected with HTTP 400.
	t.Run("depth_11_rejected", func(t *testing.T) {
		// Build a GraphQL query with 11 nested selection sets:
		//   { a { b { c { ... { x } ... } } } }
		// estimateQueryDepth counts open braces, so 11 `{` chars yield depth 11.
		nested := strings.Repeat("a {", 11) + "x" + strings.Repeat(" }", 11)
		body := []byte(`{"query":"` + strings.ReplaceAll(nested, `"`, `\"`) + `"}`)

		resp, err := http.Post(server.URL, "application/json", bytes.NewReader(body))
		require.NoError(t, err)
		defer resp.Body.Close()
		respBytes, _ := io.ReadAll(resp.Body)

		// graphql_depth.go:47 explicitly writes StatusBadRequest on rejection.
		require.Equal(t, http.StatusBadRequest, resp.StatusCode,
			"depth-limit middleware must return 400 on rejection")
		require.Contains(t, string(respBytes), "depth",
			"response body must contain 'depth' error: got %s", string(respBytes))
		require.Contains(t, string(respBytes), "exceeds maximum",
			"response body must contain 'exceeds maximum': got %s", string(respBytes))
	})

	// Sub-test 2: depth 5 (well under the limit) passes through.
	t.Run("depth_5_passes", func(t *testing.T) {
		// 5 nested selection sets — well under maxDepth=10.
		body := []byte(`{"query":"{ a { b { c { d { e } } } } }"}`)
		resp, err := http.Post(server.URL, "application/json", bytes.NewReader(body))
		require.NoError(t, err)
		defer resp.Body.Close()
		respBytes, _ := io.ReadAll(resp.Body)

		require.Equal(t, http.StatusOK, resp.StatusCode,
			"depth-5 query must pass through to inner handler")
		require.Contains(t, string(respBytes), `"data":"ok"`,
			"inner handler must produce its OK response: got %s", string(respBytes))
	})

	// Sub-test 3: timeout fires on slow handler.
	t.Run("timeout_fires", func(t *testing.T) {
		body := []byte(`{"query":"{ a }"}`)
		req, err := http.NewRequest(http.MethodPost, server.URL, bytes.NewReader(body))
		require.NoError(t, err)
		req.Header.Set("Content-Type", "application/json")
		req.Header.Set("X-Test-Sleep", "1") // triggers 2s sleep in inner handler

		start := time.Now()
		resp, err := http.DefaultClient.Do(req)
		elapsed := time.Since(start)
		require.NoError(t, err)
		defer resp.Body.Close()

		// Timeout middleware sets ctx deadline = 200ms. Inner handler returns
		// 504 when ctx.Done fires before its 2s sleep completes.
		require.Equal(t, http.StatusGatewayTimeout, resp.StatusCode,
			"timeout must fire within 200ms, returning 504 from the inner handler")
		require.Less(t, elapsed, 1*time.Second,
			"timeout must fire fast (~200ms), not wait the full 2s sleep")
	})
}
