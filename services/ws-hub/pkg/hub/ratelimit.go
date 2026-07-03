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

// wsUpgradeBucket tracks token state for one IP address..
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
	buckets     sync.Map      // map[string]*wsUpgradeBucket
	capacity    float64       // max burst (initial tokens)
	ratePerSec  float64       // steady-state refill rate
	idleTimeout time.Duration // GC: remove buckets idle longer than this
	stopGC      chan struct{}
	gcInterval  time.Duration
}

// NewWSUpgradeRateLimiter creates a limiter.
// capacity:   max burst (e.g. 10 → allow 10 upgrades in a burst)
// windowSec:  replenishment window (e.g. 60 → full refill in 60 s, i.e. 1/6 tok/s).
func NewWSUpgradeRateLimiter(capacity int, windowSec int) *WSUpgradeRateLimiter {
	l := &WSUpgradeRateLimiter{
		capacity:    float64(capacity),
		ratePerSec:  float64(capacity) / float64(windowSec),
		idleTimeout: 5 * time.Minute,
		stopGC:      make(chan struct{}),
		gcInterval:  time.Minute,
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
	interval := l.gcInterval
	if interval == 0 {
		interval = time.Minute
	}
	ticker := time.NewTicker(interval)
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

// isTrustedProxy returns true if ip matches an exact entry in the set or falls
// within any of the CIDR ranges.
func isTrustedProxy(ip net.IP, exact map[string]struct{}, cidrs []*net.IPNet) bool {
	if _, ok := exact[ip.String()]; ok {
		return true
	}
	for _, cidr := range cidrs {
		if cidr.Contains(ip) {
			return true
		}
	}
	return false
}

// RealIP extracts the real client IP from the X-Forwarded-For chain or falls
// back to RemoteAddr.
//
// P-03 (audit 2026-03-08): O(1) map lookup instead of O(N) slice scan.
// PERF-04 (audit Wave 11): proper right-to-left XFF chain traversal for
// CDN → Cloudflare → ingress → pod deployments.  The XFF list is ordered
// oldest→newest (client first, each proxy appends).  We walk right-to-left,
// skipping trusted proxies, and return the first untrusted IP — the real client.
// CIDR-based trust is supported via the cidrs parameter.
//
// Call site: pass cfg.TrustedProxiesSet and cfg.TrustedCIDRs.
func RealIP(r *http.Request, trustedProxies map[string]struct{}, cidrs []*net.IPNet) string {
	remoteIP, _, err := net.SplitHostPort(r.RemoteAddr)
	if err != nil {
		remoteIP = r.RemoteAddr
	}

	parsedRemote := net.ParseIP(remoteIP)
	if parsedRemote == nil || !isTrustedProxy(parsedRemote, trustedProxies, cidrs) {
		// Immediate caller is not a trusted proxy — it IS the client.
		return remoteIP
	}

	xff := r.Header.Get("X-Forwarded-For")
	if xff == "" {
		return remoteIP
	}

	// Split all IPs in the chain (oldest→newest left→right).
	parts := strings.Split(xff, ",")
	ips := make([]string, 0, len(parts))
	for _, p := range parts {
		if trimmed := strings.TrimSpace(p); trimmed != "" {
			ips = append(ips, trimmed)
		}
	}

	// Walk right-to-left: skip trusted proxies; return first untrusted entry.
	for i := len(ips) - 1; i >= 0; i-- {
		ip := net.ParseIP(ips[i])
		if ip == nil {
			// Malformed entry — stop here to avoid spoofing via injection.
			break
		}
		if !isTrustedProxy(ip, trustedProxies, cidrs) {
			return ip.String()
		}
	}

	// All XFF entries were trusted — RemoteAddr is the safe fallback.
	return remoteIP
}

// LOW-W19: custom min() removed — Go 1.21+ provides min() as a builtin that
// works on all ordered types.  Defining it here shadowed the builtin and would
// cause a compile error with Go 1.21 toolchains that treat redeclared builtins
// as errors in some linter configurations.
