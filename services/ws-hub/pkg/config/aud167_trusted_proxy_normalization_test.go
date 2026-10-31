package config_test

import (
	"io"
	"log/slog"
	"net"
	"net/http"
	"net/http/httptest"
	"os"
	"testing"
	"time"

	"github.com/university-ecosystem/ws-hub/pkg/config"
	"github.com/university-ecosystem/ws-hub/pkg/hub"
)

func aud167Config(t *testing.T, trustedPeers string) *config.Config {
	t.Helper()
	for _, name := range []string{
		"NATS_URL_FILE", "NATS_USER_FILE", "NATS_PASSWORD_FILE", "NATS_AUTH_TOKEN_FILE",
		"JWT_SECRETS_FILE", "JWT_SECRET_FILE", "WS_HUB_INTERNAL_SECRET_FILE",
		"INTERNAL_AUTH_TOKEN_FILE", "REDIS_URL_FILE", "REDIS_PASSWORD_FILE",
		"REVOCATION_REDIS_URL_FILE",
	} {
		t.Setenv(name, "")
		if err := os.Unsetenv(name); err != nil {
			t.Fatal(err)
		}
	}
	t.Setenv("TRUSTED_PROXIES", trustedPeers)
	cfg, err := config.LoadConfig()
	if err != nil {
		t.Fatalf("load configuration: %v", err)
	}
	return cfg
}

func TestAUD167EquivalentTrustedProxyAddressesResolveClient(t *testing.T) {
	tests := []struct {
		name       string
		configured string
		peer       string
		forwarded  string
		want       string
	}{
		{"expanded IPv6", "2001:0DB8:0:0:0:0:0:1", "[2001:db8::1]:4000", "198.51.100.10", "198.51.100.10"},
		{"mapped IPv4", "::ffff:192.0.2.10", "192.0.2.10:4000", "198.51.100.10", "198.51.100.10"},
		{"expanded IPv6 forwarded hop", "10.0.0.2,2001:0DB8:0:0:0:0:0:1", "10.0.0.2:4000", "198.51.100.10, 2001:db8::1", "198.51.100.10"},
		{"untrusted IPv6", "2001:0DB8:0:0:0:0:0:1", "[2001:db8::2]:4000", "198.51.100.10", "2001:db8::2"},
		{"untrusted IPv4 neighbor", "::ffff:192.0.2.10", "192.0.2.11:4000", "198.51.100.10", "192.0.2.11"},
		{"IPv6 CIDR", "2001:db8:1::/48", "[2001:db8:1::2]:4000", "198.51.100.10", "198.51.100.10"},
		{"invalid exact peer", "not-an-ip", "192.0.2.10:4000", "198.51.100.10", "192.0.2.10"},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			cfg := aud167Config(t, tc.configured)
			req := httptest.NewRequest(http.MethodGet, "/ws", nil)
			req.RemoteAddr = tc.peer
			req.Header.Set("X-Forwarded-For", tc.forwarded)
			if got := hub.RealIP(req, cfg.TrustedProxiesSet, cfg.TrustedCIDRs); got != tc.want {
				t.Errorf("client IP = %q, want %q", got, tc.want)
			}
		})
	}
}

func TestAUD167MappedLoopbackPeerKeepsClientBucketsSeparate(t *testing.T) {
	cfg := aud167Config(t, "::ffff:127.0.0.1")
	logger := slog.New(slog.NewTextHandler(io.Discard, nil))
	h := hub.NewHub(nil, logger, nil, cfg, nil)
	h.UpgradeLimiter.Stop()
	h.UpgradeLimiter = hub.NewWSUpgradeRateLimiter(2, 3600)
	t.Cleanup(h.Stop)

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		peer, _, err := net.SplitHostPort(r.RemoteAddr)
		if err != nil || peer != "127.0.0.1" {
			t.Errorf("socket peer = %q, want loopback IPv4", r.RemoteAddr)
		}
		h.HandleWebSocket(w, r, cfg)
	}))
	t.Cleanup(server.Close)
	client := server.Client()
	client.Timeout = 5 * time.Second

	request := func(forwarded string) int {
		t.Helper()
		req, err := http.NewRequestWithContext(t.Context(), http.MethodGet, server.URL+"/ws", nil)
		if err != nil {
			t.Fatal(err)
		}
		req.Header.Set("X-Forwarded-For", forwarded)
		resp, err := client.Do(req)
		if err != nil {
			t.Fatal(err)
		}
		if err := resp.Body.Close(); err != nil {
			t.Fatalf("close response: %v", err)
		}
		return resp.StatusCode
	}

	clientA := "198.51.100.10"
	clientB := "198.51.100.20"
	for i := 0; i < 2; i++ {
		if got := request(clientA); got != http.StatusUnauthorized {
			t.Fatalf("client A attempt %d: status %d, want 401", i+1, got)
		}
	}
	if got := request(clientA); got != http.StatusTooManyRequests {
		t.Errorf("exhausted client A: status %d, want 429", got)
	}
	if got := request(clientB); got != http.StatusUnauthorized {
		t.Errorf("client B after A is exhausted: status %d, want 401", got)
	}
	if got := request(clientB + ", " + clientA); got != http.StatusTooManyRequests {
		t.Errorf("spoofed header from client A: status %d, want 429", got)
	}
}
