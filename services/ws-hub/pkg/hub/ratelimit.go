package hub

// ratelimit.go — per-IP token-bucket rate limiter for WebSocket upgrades.
//
// Why token-bucket and not a simple counter?
// A counter-per-window allows an attacker to burst window_size requests at the
// _boundary_ of each window (classic boundary-burst attack).  Token-bucket
// refills continuously, so the effective burst is bounded to the bucket
// capacity regardless of timing.  This is the same algorithm used by
// iptables/nftables LIMIT and nginx limit_req.
//
// Zero external dependencies — uses only sync.Map and time.

import (
	"net"
	"net/http"
	"strings"
	"sync"
	"time"
)

// wsUpgradeBucket tracks token state for one IP address.
type wsUpgradeBucket struct {
	mu       sync.Mutex
	tokens   float64
	lastRefr time.Time
}

// allow returns true if a token is available and consumes it.
// capacity is the max burst; ratePerSec is tokens added per second.
func (b *wsUpgradeBucket) allow(capacity, ratePerSec float64) bool {
	b.mu.Lock()
	defer b.mu.Unlock()

	now := time.Now()
	// Refill tokens proportional to elapsed time.
	elapsed := now.Sub(b.lastRefr).Seconds()
	b.lastRefr = now
	b.tokens = min(capacity, b.tokens+elapsed*ratePerSec)

	if b.tokens < 1 {
		return false
	}
	b.tokens--
	return true
}

// WSUpgradeRateLimiter holds per-IP buckets and runs periodic GC.
type WSUpgradeRateLimiter struct {
	buckets     sync.Map        // map[string]*wsUpgradeBucket
	capacity    float64         // max burst (initial tokens)
	ratePerSec  float64         // steady-state refill rate
	idleTimeout time.Duration   // GC: remove buckets idle longer than this
	stopGC      chan struct{}
}

// NewWSUpgradeRateLimiter creates a limiter.
// capacity:   max burst (e.g. 10 → allow 10 upgrades in a burst)
// windowSec:  replenishment window (e.g. 60 → full refill in 60 s, i.e. 1/6 tok/s)
func NewWSUpgradeRateLimiter(capacity int, windowSec int) *WSUpgradeRateLimiter {
	l := &WSUpgradeRateLimiter{
		capacity:    float64(capacity),
		ratePerSec:  float64(capacity) / float64(windowSec),
		idleTimeout: 5 * time.Minute,
		stopGC:      make(chan struct{}),
	}
	go l.gcLoop()
	return l
}

// Allow returns true if the request from ip should be permitted.
func (l *WSUpgradeRateLimiter) Allow(ip string) bool {
	raw, _ := l.buckets.LoadOrStore(ip, &wsUpgradeBucket{
		tokens:   l.capacity, // new IPs start with a full bucket
		lastRefr: time.Now(),
	})
	return raw.(*wsUpgradeBucket).allow(l.capacity, l.ratePerSec)
}

// Stop terminates the GC goroutine.  Call this during hub shutdown.
func (l *WSUpgradeRateLimiter) Stop() {
	close(l.stopGC)
}

// gcLoop removes stale buckets every minute to prevent unbounded memory growth.
func (l *WSUpgradeRateLimiter) gcLoop() {
	ticker := time.NewTicker(time.Minute)
	defer ticker.Stop()
	for {
		select {
		case <-ticker.C:
			now := time.Now()
			l.buckets.Range(func(k, v any) bool {
				b := v.(*wsUpgradeBucket)
				b.mu.Lock()
				idle := now.Sub(b.lastRefr)
				b.mu.Unlock()
				if idle > l.idleTimeout {
					l.buckets.Delete(k)
				}
				return true
			})
		case <-l.stopGC:
			return
		}
	}
}

// RealIP extracts the real client IP from X-Forwarded-For (first hop) or
// falls back to the RemoteAddr. Relies on the reverse proxy being trusted
// (configured via ProxyHeadersMiddleware upstream).
// RealIP extracts the real client IP.
// It only trusts X-Forwarded-For if the immediate RemoteAddr is in trustedProxies.
func RealIP(r *http.Request, trustedProxies []string) string {
	remoteIP, _, err := net.SplitHostPort(r.RemoteAddr)
	if err != nil {
		remoteIP = r.RemoteAddr
	}

	isTrusted := false
	for _, trusted := range trustedProxies {
		if remoteIP == trusted {
			isTrusted = true
			break
		}
	}

	if isTrusted {
		if xff := r.Header.Get("X-Forwarded-For"); xff != "" {
			// X-Forwarded-For may be a comma-separated list; take the leftmost entry.
			for i := 0; i < len(xff); i++ {
				if xff[i] == ',' {
					return strings.TrimSpace(xff[:i])
				}
			}
			return strings.TrimSpace(xff)
		}
	}

	return remoteIP
}

// min is a helper because Go 1.21+ provides it as a builtin,
// but we keep it explicit for clarity.
func min(a, b float64) float64 {
	if a < b {
		return a
	}
	return b
}
