// Package middleware provides HTTP middleware for the API Gateway.
package middleware

import (
	"context"
	"net/http"
	"strings"
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

		ctx := c.Request.Context()

		// Apply rate limit
		res, err := rl.limiter.Allow(ctx, key, redis_rate.PerSecond(rl.rps))
		if err != nil {
			// If Redis fails, allow the request but log it
			c.Next()
			return
		}

		// Set rate limit headers
		c.Header("X-RateLimit-Limit", string(rune(rl.rps)))
		c.Header("X-RateLimit-Remaining", string(rune(res.Remaining)))
		c.Header("X-RateLimit-Reset", res.ResetAfter.String())

		if res.Allowed == 0 {
			c.Header("Retry-After", res.RetryAfter.String())
			c.AbortWithStatusJSON(http.StatusTooManyRequests, gin.H{
				"error":       "rate limit exceeded",
				"retry_after": res.RetryAfter.Seconds(),
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

	// Fall back to IP address
	ip := c.ClientIP()

	// Check for forwarded IP
	if forwarded := c.GetHeader("X-Forwarded-For"); forwarded != "" {
		parts := strings.Split(forwarded, ",")
		if len(parts) > 0 {
			ip = strings.TrimSpace(parts[0])
		}
	}

	return "ip:" + ip
}
