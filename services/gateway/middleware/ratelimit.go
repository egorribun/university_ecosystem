// Package middleware provides HTTP middleware for the API Gateway.
package middleware

import (
	"context"
	"fmt"
	"net/http"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/go-redis/redis_rate/v10"
	"github.com/redis/go-redis/v9"
)

// fallbackEntry tracks in-memory request counts during Redis outages.
type fallbackEntry struct {
	count       int64
	windowStart int64 // Unix timestamp in seconds
}

const (
	defaultFallbackLimit           = 3
	defaultFallbackWindow          = int64(60)
	defaultFallbackMaxEntries      = 10_000
	defaultFallbackCleanupInterval = 5 * time.Minute
)

// RateLimiter provides Redis-backed rate limiting with an in-memory fallback.
type RateLimiter struct {
	client  *redis.Client
	limiter *redis_rate.Limiter
	rps     int

	// P0-W5-04: In-memory fallback for Redis outages.
	// Conservative limits prevent brute-force even when Redis is unavailable.
	fallbackMu       sync.Mutex
	fallbackCounters map[string]*fallbackEntry
	fallbackLimit    int   // max requests per fallbackWindowSecs
	fallbackWindow   int64 // window length in seconds
	// fallbackMaxEntries caps attacker-controlled IP/user cardinality while
	// Redis is unavailable. New keys fail closed once the cap is reached.
	fallbackMaxEntries int
	cleanupInterval    time.Duration
	// RZ-W18-03 (audit 2026-03-23 Wave 18): ensure cleanup goroutine starts once.
	cleanupOnce     sync.Once
	cleanupStopOnce sync.Once
	cleanupCancel   context.CancelFunc
	cleanupDone     chan struct{}
}

var closeRedisClientFunc = func(client *redis.Client) error {
	return client.Close()
}

// NewRateLimiter creates a new rate limiter with Redis backend.
// Fallback defaults: 3 requests / 60 s per client key.
func NewRateLimiter(ctx context.Context, redisURL string, rps, burst int) (*RateLimiter, error) {
	opt, err := redis.ParseURL(redisURL)
	if err != nil {
		return nil, err
	}

	client := redis.NewClient(opt)

	// Test connection
	pingCtx, cancel := context.WithTimeout(ctx, 5*time.Second)
	defer cancel()

	if err := client.Ping(pingCtx).Err(); err != nil {
		if closeErr := closeRedisClientFunc(client); closeErr != nil {
			return nil, fmt.Errorf("%w; failed to close Redis client: %v", err, closeErr)
		}
		return nil, err
	}

	limiter := redis_rate.NewLimiter(client)

	rateLimiter := NewFallbackRateLimiter()
	rateLimiter.client = client
	rateLimiter.limiter = limiter
	rateLimiter.rps = rps
	return rateLimiter, nil
}

// NewFallbackRateLimiter creates a bounded, per-instance limiter for startup
// degradation when Redis is unavailable. It deliberately uses the same
// conservative policy as the runtime Redis-error fallback.
func NewFallbackRateLimiter() *RateLimiter {
	return &RateLimiter{
		fallbackCounters:   make(map[string]*fallbackEntry),
		fallbackLimit:      defaultFallbackLimit,
		fallbackWindow:     defaultFallbackWindow,
		fallbackMaxEntries: defaultFallbackMaxEntries,
		cleanupInterval:    defaultFallbackCleanupInterval,
	}
}

// GetClient returns the underlying redis client.
func (rl *RateLimiter) GetClient() *redis.Client {
	return rl.client
}

// inMemoryAllow checks the in-memory fallback counter.
// Returns true if the request is allowed, false if the client is over the limit.
// Stale windows are reset on access — no background goroutine required.
func (rl *RateLimiter) inMemoryAllow(key string) bool {
	now := time.Now().Unix()
	rl.fallbackMu.Lock()
	defer rl.fallbackMu.Unlock()
	if rl.fallbackCounters == nil {
		rl.fallbackCounters = make(map[string]*fallbackEntry)
	}

	entry, ok := rl.fallbackCounters[key]
	if !ok {
		maxEntries := rl.fallbackMaxEntries
		if maxEntries <= 0 {
			maxEntries = defaultFallbackMaxEntries
		}
		if len(rl.fallbackCounters) >= maxEntries {
			return false
		}
		rl.fallbackCounters[key] = &fallbackEntry{count: 1, windowStart: now}
		return true
	}
	if (now - entry.windowStart) >= rl.fallbackWindow {
		// Existing expired window — reset without increasing cardinality.
		rl.fallbackCounters[key] = &fallbackEntry{count: 1, windowStart: now}
		return true
	}
	entry.count++
	return entry.count <= int64(rl.fallbackLimit)
}

func (rl *RateLimiter) applyInMemoryFallback(c *gin.Context, key string) bool {
	if rl.inMemoryAllow(key) {
		return true
	}
	c.Header("Retry-After", strconv.FormatInt(rl.fallbackWindow, 10))
	c.AbortWithStatusJSON(http.StatusTooManyRequests, gin.H{
		"error":       "rate_limit_exceeded",
		"retry_after": rl.fallbackWindow,
	})
	return false
}

// startFallbackCleanup launches a background goroutine that periodically
// removes expired entries from fallbackCounters, preventing unbounded map growth
// during sustained Redis outages with rotating client IPs.
// RZ-W18-03 (audit 2026-03-23 Wave 18): without this, the map grows without bound
// because inMemoryAllow() only resets entries on access — entries for clients that
// stop sending requests are never removed.
func (rl *RateLimiter) startFallbackCleanup(ctx context.Context) {
	rl.cleanupOnce.Do(func() {
		cleanupCtx, cancel := context.WithCancel(ctx)
		rl.cleanupCancel = cancel
		rl.cleanupDone = make(chan struct{})
		go func() {
			defer close(rl.cleanupDone)
			interval := rl.cleanupInterval
			if interval == 0 {
				interval = 5 * time.Minute
			}
			ticker := time.NewTicker(interval)
			defer ticker.Stop()
			for {
				select {
				case <-cleanupCtx.Done():
					return
				case <-ticker.C:
					rl.fallbackMu.Lock()
					now := time.Now().Unix()
					for key, entry := range rl.fallbackCounters {
						if now-entry.windowStart >= rl.fallbackWindow*2 {
							delete(rl.fallbackCounters, key)
						}
					}
					rl.fallbackMu.Unlock()
				}
			}
		}()
	})
}

// Close stops the fallback cleanup worker and releases the Redis client.
// Callers should invoke it during service shutdown; tests use it to make the
// lifecycle contract observable to goleak.
func (rl *RateLimiter) Close() error {
	rl.cleanupStopOnce.Do(func() {
		if rl.cleanupCancel != nil {
			rl.cleanupCancel()
		}
	})
	if rl.cleanupDone != nil {
		<-rl.cleanupDone
	}
	if rl.client != nil {
		return rl.client.Close()
	}
	return nil
}

// Middleware returns a Gin middleware for rate limiting.
func (rl *RateLimiter) Middleware(ctx context.Context) gin.HandlerFunc {
	// RZ-W18-03: start the fallback map cleanup goroutine.
	rl.startFallbackCleanup(ctx)
	return func(c *gin.Context) {
		// PERF-23-02 (audit 2026-03-25 Wave 23): Exempt health/readiness probes
		// from rate limiting. During Redis outage the 3 req/60s fallback would
		// block Kubernetes liveness probes → pod restarts → cascading failure.
		if isHealthPath(c.Request.URL.Path) {
			c.Next()
			return
		}

		// Get client identifier (IP or User ID)
		key := rl.getClientKey(c)
		if rl.limiter == nil {
			if rl.applyInMemoryFallback(c, key) {
				c.Next()
			}
			return
		}

		// PERF-06 (audit 2026-03-04): Apply a tight deadline on the Redis call.
		// Without a timeout a slow/overloaded Redis server blocks the Gin goroutine
		// indefinitely, cascading into a connection exhaustion outage.
		rCtx, cancel := context.WithTimeout(ctx, 50*time.Millisecond)
		defer cancel()

		// Apply rate limit
		res, err := rl.limiter.Allow(rCtx, key, redis_rate.PerSecond(rl.rps))
		if err != nil {
			// P0-W5-04: Redis failure — apply in-memory fallback instead of fail-open.
			// Without this, any Redis outage completely disables rate limiting and
			// enables unlimited brute-force on auth endpoints.
			if rl.applyInMemoryFallback(c, key) {
				c.Next()
			}
			return
		}

		// Set standard IETF draft RateLimit headers (MOD-8)
		c.Header("RateLimit-Limit", strconv.Itoa(rl.rps))
		c.Header("RateLimit-Remaining", strconv.Itoa(res.Remaining))
		// ResetAfter is a time.Duration, we need to add it to current time for Reset header
		resetAt := time.Now().Add(res.ResetAfter)
		c.Header("RateLimit-Reset", strconv.FormatInt(resetAt.Unix(), 10))
		c.Header("RateLimit-Policy", fmt.Sprintf("%d;w=1", rl.rps)) // Assuming 1 second window based on PerSecond(rl.rps)

		if res.Allowed == 0 {
			// RFC 7231 requires Retry-After to be an HTTP-date or an integer number of seconds
			c.Header("Retry-After", strconv.FormatInt(int64(res.RetryAfter.Seconds()), 10))
			c.AbortWithStatusJSON(http.StatusTooManyRequests, gin.H{
				"error":       "rate limit exceeded",
				"retry_after": int(res.RetryAfter.Seconds()),
			})
			return
		}

		c.Next()
	}
}

// isHealthPath returns true for Kubernetes probe and monitoring paths that must
// bypass rate limiting to prevent cascading failures during Redis outages.
func isHealthPath(path string) bool {
	// Kubernetes probes use the canonical /health/{ready,live} endpoints.  Keep
	// every health sub-route exempt: probes must continue to work when Redis is
	// unavailable and the limiter is operating in its bounded in-memory fallback.
	return path == "/health" ||
		path == "/health/ready" ||
		path == "/health/live" ||
		strings.HasPrefix(path, "/health/") ||
		path == "/readiness" ||
		path == "/metrics"
}

// getClientKey returns a unique key for rate limiting based on IP or user.
func (rl *RateLimiter) getClientKey(c *gin.Context) string {
	// TD-W5-04: Safe type assertion — avoid panic if context value has unexpected type.
	if userIDRaw, exists := c.Get("user_id"); exists {
		if userID, ok := userIDRaw.(string); ok && userID != "" {
			return "user:" + userID
		}
	}

	// Fall back to IP address.
	// We rely on Gin's ClientIP() which is safer and respects TrustedProxies.
	// Manual parsing of X-Forwarded-For is insecure as it's easily spoofable.
	return "ip:" + c.ClientIP()
}
