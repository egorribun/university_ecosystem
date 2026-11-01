package hub

import (
	"fmt"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/stretchr/testify/require"
	"github.com/university-ecosystem/ws-hub/pkg/config"
)

// aud167UpgradeAttempt sends one WebSocket upgrade attempt without a ticket. A
// missing ticket is rejected only after the per-client upgrade limiter has accepted
// the attempt, so 401 means the attempt was admitted to the limiter and 429 means
// its key was exhausted (AUD-167).
func aud167UpgradeAttempt(t *testing.T, h *Hub, cfg *config.Config, remoteAddr, forwardedFor string) int {
	t.Helper()
	request := httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/ws", nil)
	request.RemoteAddr = remoteAddr
	if forwardedFor != "" {
		request.Header.Set("X-Forwarded-For", forwardedFor)
	}
	recorder := httptest.NewRecorder()
	h.HandleWebSocket(recorder, request, cfg)
	return recorder.Code
}

// TestAUD167TwoClientsBehindTrustedProxyHaveSeparateUpgradeKeys: both clients reach
// the hub through one trusted proxy. Exhausting the first client's upgrade budget
// must leave the second client's budget untouched.
func TestAUD167TwoClientsBehindTrustedProxyHaveSeparateUpgradeKeys(t *testing.T) {
	h := setupTestHub()
	cfg := &config.Config{
		MaxClients:        100,
		TrustedProxiesSet: map[string]struct{}{"10.200.0.12": {}},
	}
	const proxy = "10.200.0.12:45678"

	for i := 0; i < 10; i++ {
		require.Equal(t, http.StatusUnauthorized, aud167UpgradeAttempt(t, h, cfg, proxy, "198.51.100.25"),
			fmt.Sprintf("client A attempt %d is within its upgrade budget", i+1))
	}
	require.Equal(t, http.StatusTooManyRequests, aud167UpgradeAttempt(t, h, cfg, proxy, "198.51.100.25"),
		"client A exceeds its own upgrade budget")
	require.Equal(t, http.StatusUnauthorized, aud167UpgradeAttempt(t, h, cfg, "10.200.0.12:45679", "198.51.100.26"),
		"client B behind the same trusted proxy must have its own upgrade key")
}

// TestAUD167SpoofedForwardedForFromUntrustedPeerIsIgnored: the peer is not a trusted
// proxy, so a rotating X-Forwarded-For header must not change the limiter key. The
// budget is shared across all spoofed values.
func TestAUD167SpoofedForwardedForFromUntrustedPeerIsIgnored(t *testing.T) {
	h := setupTestHub()
	cfg := &config.Config{
		MaxClients:        100,
		TrustedProxiesSet: map[string]struct{}{"10.200.0.12": {}},
	}
	const peer = "198.51.100.99:5000"

	for i := 0; i < 10; i++ {
		require.Equal(t, http.StatusUnauthorized, aud167UpgradeAttempt(t, h, cfg, peer, fmt.Sprintf("203.0.113.%d", i+1)))
	}
	require.Equal(t, http.StatusTooManyRequests, aud167UpgradeAttempt(t, h, cfg, peer, "203.0.113.200"),
		"a spoofed forwarded address from an untrusted peer must not reset its budget")
}
