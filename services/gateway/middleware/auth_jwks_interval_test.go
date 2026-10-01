package middleware

import (
	"context"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"sync/atomic"
	"testing"
	"time"

	"github.com/stretchr/testify/require"
)

func TestStartJWKSRefresher_ZeroIntervalDoesNotBusyLoop(t *testing.T) {
	var requests atomic.Int32
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		requests.Add(1)
		w.Header().Set("Content-Type", "application/json")
		_, _ = io.WriteString(w, `{"keys":[{"kty":"RSA","n":"AQ","e":"AQAB"}]}`)
	}))
	defer server.Close()

	middleware := NewJWTMiddleware("synthetic-test-secret", nil)
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	middleware.StartJWKSRefresher(ctx, server.URL, 0, slog.New(slog.NewTextHandler(io.Discard, nil)))
	require.Eventually(t, func() bool { return requests.Load() >= 1 }, time.Second, time.Millisecond)
	// A zero interval used to reset the timer immediately after the initial
	// successful fetch, issuing unbounded requests until the parent was canceled.
	time.Sleep(50 * time.Millisecond)
	cancel()
	require.EqualValues(t, 1, requests.Load(), "zero interval must use the safe default refresh cadence")
}
