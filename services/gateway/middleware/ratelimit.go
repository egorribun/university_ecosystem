// Package middleware provides HTTP middleware for the API Gateway.
package middleware

import (
	"context"
	"fmt"
	"net/http"
	"strconv"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/go-redis/redis_rate/v10"
	"github.com/redis/go-redis/v9"
)

// RateLimiter provides Redis-backed rate limiting
type RateLimiter struct {
	client  *redis.Client
	limiter *redis_rate.Limiter
	rps     int
	burst   int
}

// NewRateLimiter creates a new rate limiter with Redis backend
func NewRateLimiter(redisURL string, rps, burst int) (*RateLimiter, error) {
	opt, err := redis.ParseURL(redisURL)
	if err != nil {
		return nil, err
	}

	client := redis.NewClient(opt)

	// Test connection
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	if err := client.Ping(ctx).Err(); err != nil {
		return nil, err
	}

	limiter := redis_rate.NewLimiter(client)

	return &RateLimiter{
		client:  client,
		limiter: limiter,
		rps:     rps,
		burst:   burst,
	}, nil
}

// GetClient returns the underlying redis client
func (rl *RateLimiter) GetClient() *redis.Client {
	return rl.client
}

// Middleware returns a Gin middleware for rate limiting
func (rl *RateLimiter) Middleware() gin.HandlerFunc {
	return func(c *gin.Context) {
		// Get client identifier (IP or User ID)
		key := rl.getClientKey(c)

		// PERF-06 (audit 2026-03-04): Apply a tight deadline on the Redis call.
		// Without a timeout a slow/overloaded Redis server blocks the Gin goroutine
		// indefinitely, cascading into a connection exhaustion outage.
		// On timeout we fail-open (allow the request) to maintain availability,
		// consistent with the existing Redis-error behaviour below.
		rCtx, cancel := context.WithTimeout(c.Request.Context(), 50*time.Millisecond)
		defer cancel()

		// Apply rate limit
		res, err := rl.limiter.Allow(rCtx, key, redis_rate.PerSecond(rl.rps))
		if err != nil {
			// If Redis fails or times out, allow the request but log it
			c.Next()
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


// getClientKey returns a unique key for rate limiting based on IP or user
func (rl *RateLimiter) getClientKey(c *gin.Context) string {
	// Prefer user ID if authenticated
	if userID, exists := c.Get("user_id"); exists {
		return "user:" + userID.(string)
	}

	// Fall back to IP address.
	// We rely on Gin's ClientIP() which is safer and respects TrustedProxies.
	// Manual parsing of X-Forwarded-For is insecure as it's easily spoofable.
	return "ip:" + c.ClientIP()
}
