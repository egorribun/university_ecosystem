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

// A missing hop is malformed just like a non-IP hop. Once the trusted suffix
// reaches it, the hub must not use a potentially forged earlier address.
func TestAUD167EmptyForwardedHopFailsClosed(t *testing.T) {
	trusted := map[string]struct{}{"10.200.0.12": {}, "10.200.0.13": {}}
	for _, test := range []struct {
		name string
		xff  string
		want string
	}{
		{"empty hop", "203.0.113.1,,10.200.0.13", "10.200.0.12"},
		{"whitespace hop", "203.0.113.1, \t , 10.200.0.13", "10.200.0.12"},
		{"trailing empty hop", "203.0.113.1, 10.200.0.13,", "10.200.0.12"},
		{"empty prefix beyond real client", ", 198.51.100.25, 10.200.0.13", "198.51.100.25"},
	} {
		t.Run(test.name, func(t *testing.T) {
			request := httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/ws", nil)
			request.RemoteAddr = "10.200.0.12:45678"
			request.Header.Set("X-Forwarded-For", test.xff)
			require.Equal(t, test.want, RealIP(request, trusted, nil))
		})
	}
}

func TestAUD167RotatingSpoofsAcrossEmptyHopCannotEscapeUpgradeLimit(t *testing.T) {
	h := setupTestHub()
	h.UpgradeLimiter.Stop()
	// Preserve the production burst while preventing a refill during slow CI.
	h.UpgradeLimiter = NewWSUpgradeRateLimiter(10, 3600)
	t.Cleanup(h.Stop)
	cfg := &config.Config{
		MaxClients: 100,
		TrustedProxiesSet: map[string]struct{}{
			"10.200.0.12": {},
			"10.200.0.13": {},
		},
	}
	const proxy = "10.200.0.12:45678"
	for i := 1; i <= 10; i++ {
		xff := fmt.Sprintf("203.0.113.%d, , 10.200.0.13", i)
		require.Equal(t, http.StatusUnauthorized, aud167UpgradeAttempt(t, h, cfg, proxy, xff))
	}
	require.Equal(t, http.StatusTooManyRequests,
		aud167UpgradeAttempt(t, h, cfg, proxy, "203.0.113.11, , 10.200.0.13"))
	require.Equal(t, http.StatusUnauthorized,
		aud167UpgradeAttempt(t, h, cfg, proxy, "198.51.100.25, 10.200.0.13"))
}

func TestAUD167ForwardedHeaderFieldsFormOneOrderedChain(t *testing.T) {
	trusted := map[string]struct{}{"10.200.0.12": {}, "10.200.0.13": {}}
	for _, test := range []struct {
		name   string
		fields []string
		want   string
	}{
		{"rightmost client wins", []string{"203.0.113.1", "198.51.100.25, 10.200.0.13"}, "198.51.100.25"},
		{"empty field fails closed", []string{"203.0.113.1", "", "10.200.0.13"}, "10.200.0.12"},
		{"empty field beyond client", []string{"", "198.51.100.25"}, "198.51.100.25"},
	} {
		t.Run(test.name, func(t *testing.T) {
			request := httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/ws", nil)
			request.RemoteAddr = "10.200.0.12:45678"
			for _, field := range test.fields {
				request.Header.Add("X-Forwarded-For", field)
			}
			require.Equal(t, test.want, RealIP(request, trusted, nil))
		})
	}
}

func TestAUD167RotatingFirstForwardedFieldCannotEscapeUpgradeLimit(t *testing.T) {
	h := setupTestHub()
	h.UpgradeLimiter.Stop()
	h.UpgradeLimiter = NewWSUpgradeRateLimiter(10, 3600)
	t.Cleanup(h.Stop)
	cfg := &config.Config{MaxClients: 100, TrustedProxiesSet: map[string]struct{}{"10.200.0.12": {}}}
	attempt := func(forged, client string) int {
		request := httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/ws", nil)
		request.RemoteAddr = "10.200.0.12:45678"
		request.Header.Add("X-Forwarded-For", forged)
		request.Header.Add("X-Forwarded-For", client)
		recorder := httptest.NewRecorder()
		h.HandleWebSocket(recorder, request, cfg)
		return recorder.Code
	}
	for i := 1; i <= 10; i++ {
		require.Equal(t, http.StatusUnauthorized, attempt(fmt.Sprintf("203.0.113.%d", i), "198.51.100.25"))
	}
	require.Equal(t, http.StatusTooManyRequests, attempt("203.0.113.11", "198.51.100.25"))
	require.Equal(t, http.StatusUnauthorized, attempt("203.0.113.12", "198.51.100.26"))
}
