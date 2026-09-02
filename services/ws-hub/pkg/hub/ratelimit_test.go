package hub

import (
	"context"
	"net"
	"net/http"
	"testing"
	"time"
)

func TestWSUpgradeRateLimiter(t *testing.T) {
	// Capacity 2, window 1s -> 2 tokens/sec
	limiter := NewWSUpgradeRateLimiter(2, 1)
	defer limiter.Stop()

	ip1 := "192.168.1.1"
	ip2 := "10.0.0.1"

	// IP1: First two should be allowed
	if !limiter.Allow(ip1) {
		t.Errorf("Expected first request for %s to be allowed", ip1)
	}
	if !limiter.Allow(ip1) {
		t.Errorf("Expected second request for %s to be allowed", ip1)
	}

	// IP1: Third should be blocked (capacity exceeded)
	if limiter.Allow(ip1) {
		t.Errorf("Expected third request for %s to be blocked", ip1)
	}

	// IP2: Completely independent, should be allowed
	if !limiter.Allow(ip2) {
		t.Errorf("Expected first request for %s to be allowed", ip2)
	}

	// Wait ~600ms, bucket for IP1 should replenish >1 token
	time.Sleep(600 * time.Millisecond)

	// IP1: Should be allowed again
	if !limiter.Allow(ip1) {
		t.Errorf("Expected request for %s to be allowed after replenish", ip1)
	}

	// IP1: Another request should be blocked (only ~1.2 tokens were replenished)
	if limiter.Allow(ip1) {
		t.Errorf("Expected request for %s to be blocked after using replenished token", ip1)
	}
}

func TestRealIP(t *testing.T) {
	trustedExact := map[string]struct{}{
		"10.0.0.2": {},
	}

	_, cidr1, err := net.ParseCIDR("192.168.1.0/24")
	if err != nil {
		t.Fatal(err)
	}
	trustedCIDRs := []*net.IPNet{cidr1}

	tests := []struct {
		name       string
		remoteAddr string
		xff        string
		expected   string
	}{
		{
			name:       "No XFF, untrusted remote",
			remoteAddr: "203.0.113.1:1234",
			xff:        "",
			expected:   "203.0.113.1",
		},
		{
			name:       "No XFF, trusted exact remote",
			remoteAddr: "10.0.0.2:1234",
			xff:        "",
			expected:   "10.0.0.2",
		},
		{
			name:       "No XFF, trusted CIDR remote",
			remoteAddr: "192.168.1.50:1234",
			xff:        "",
			expected:   "192.168.1.50",
		},
		{
			name:       "XFF with untrusted remote",
			remoteAddr: "203.0.113.1:1234",
			xff:        "1.1.1.1, 2.2.2.2",
			expected:   "203.0.113.1", // remote is untrusted, XFF ignored
		},
		{
			name:       "XFF with trusted remote, untrusted XFF",
			remoteAddr: "10.0.0.2:1234",
			xff:        "1.1.1.1, 2.2.2.2",
			expected:   "2.2.2.2", // walks right-to-left
		},
		{
			name:       "XFF with trusted remote, mixed XFF",
			remoteAddr: "10.0.0.2:1234",
			xff:        "1.1.1.1, 192.168.1.50",
			expected:   "1.1.1.1", // 192.168.1.50 is trusted, 1.1.1.1 is untrusted
		},
		{
			name:       "XFF with trusted remote, all trusted XFF",
			remoteAddr: "10.0.0.2:1234",
			xff:        "192.168.1.50, 10.0.0.2",
			expected:   "10.0.0.2", // falls back to remote
		},
		{
			name:       "Malformed XFF entry",
			remoteAddr: "10.0.0.2:1234",
			xff:        "1.1.1.1, not-an-ip",
			expected:   "10.0.0.2", // stops at malformed
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			req, err := http.NewRequestWithContext(context.Background(), "GET", "/", nil)
			if err != nil {
				t.Fatal(err)
			}
			req.RemoteAddr = tt.remoteAddr
			if tt.xff != "" {
				req.Header.Set("X-Forwarded-For", tt.xff)
			}

			actual := RealIP(req, trustedExact, trustedCIDRs)
			if actual != tt.expected {
				t.Errorf("RealIP() = %q, expected %q", actual, tt.expected)
			}
		})
	}
}

func TestWSUpgradeRateLimiter_GC(t *testing.T) {
	defaultInterval := &WSUpgradeRateLimiter{
		stopGC: make(chan struct{}),
		gcDone: make(chan struct{}),
	}
	defaultInterval.startGC()
	time.Sleep(5 * time.Millisecond)
	defaultInterval.Stop()

	l := &WSUpgradeRateLimiter{
		capacity:    2,
		ratePerSec:  2,
		idleTimeout: 1 * time.Second,
		stopGC:      make(chan struct{}),
		gcDone:      make(chan struct{}),
		gcInterval:  10 * time.Millisecond,
	}

	l.buckets.Store("1.1.1.1", &wsUpgradeBucket{
		tokens:   2,
		lastRefr: time.Now().Add(-10 * time.Second),
	})
	l.buckets.Store("2.2.2.2", &wsUpgradeBucket{
		tokens:   2,
		lastRefr: time.Now(),
	})

	l.startGC()

	time.Sleep(50 * time.Millisecond)
	l.Stop()

	_, ok1 := l.buckets.Load("1.1.1.1")
	_, ok2 := l.buckets.Load("2.2.2.2")

	if ok1 {
		t.Errorf("Expected 1.1.1.1 to be cleaned up by GC")
	}
	if !ok2 {
		t.Errorf("Expected 2.2.2.2 to remain")
	}
}
