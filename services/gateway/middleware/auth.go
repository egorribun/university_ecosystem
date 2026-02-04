// Package middleware provides HTTP middleware for the API Gateway.
package middleware

import (
	"context"
	"fmt"
	"net/http"
	"strings"
	"sync"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/golang-jwt/jwt/v5"
	"github.com/hashicorp/golang-lru/v2/expirable"
	"github.com/prometheus/client_golang/prometheus"
	"github.com/redis/go-redis/v9"
)

// L1CacheConfig holds configuration for the local cache layer
type L1CacheConfig struct {
	MaxSize int           // Maximum number of entries (default: 10000)
	TTL     time.Duration // Time-to-live for cached entries (default: 30s)
}

// DefaultL1CacheConfig returns sensible defaults for L1 cache
func DefaultL1CacheConfig() L1CacheConfig {
	return L1CacheConfig{
		MaxSize: 10000,
		TTL:     30 * time.Second,
	}
}

// cacheEntry represents a local cache entry
type cacheEntry struct {
	exists bool
}

// JWTMiddleware validates JWT tokens
type JWTMiddleware struct {
	secret  []byte
	redis   *redis.Client
	l1cache *expirable.LRU[string, cacheEntry]
}

var (
	l1Hits = prometheus.NewCounter(prometheus.CounterOpts{
		Name: "gateway_l1_cache_hits_total",
		Help: "Total number of Gateway L1 cache hits",
	})
	l1Misses = prometheus.NewCounter(prometheus.CounterOpts{
		Name: "gateway_l1_cache_misses_total",
		Help: "Total number of Gateway L1 cache misses",
	})
	l1Evictions = prometheus.NewCounter(prometheus.CounterOpts{
		Name: "gateway_l1_cache_evictions_total",
		Help: "Total number of Gateway L1 cache evictions",
	})
	redisErrors = prometheus.NewCounter(prometheus.CounterOpts{
		Name: "gateway_redis_errors_total",
		Help: "Total number of Redis errors during session verification",
	})
	metricsRegistered sync.Once
)

// Claims represents JWT claims
type Claims struct {
	jwt.RegisteredClaims
	UserID   string `json:"sub"`
	Email    string `json:"email,omitempty"`
	Role     string `json:"role,omitempty"`
	IsActive bool   `json:"is_active,omitempty"`
}

// NewJWTMiddleware creates a new JWT middleware with default L1 cache settings
func NewJWTMiddleware(secret string, redisClient *redis.Client) *JWTMiddleware {
	return NewJWTMiddlewareWithConfig(secret, redisClient, DefaultL1CacheConfig())
}

// NewJWTMiddlewareWithConfig creates a new JWT middleware with custom L1 cache settings
func NewJWTMiddlewareWithConfig(secret string, redisClient *redis.Client, config L1CacheConfig) *JWTMiddleware {
	metricsRegistered.Do(func() {
		prometheus.MustRegister(l1Hits, l1Misses, l1Evictions, redisErrors)
	})

	// Create LRU cache with eviction callback for observability
	onEvict := func(key string, _ cacheEntry) {
		l1Evictions.Inc()
	}

	cache := expirable.NewLRU[string, cacheEntry](config.MaxSize, onEvict, config.TTL)

	return &JWTMiddleware{
		secret:  []byte(secret),
		redis:   redisClient,
		l1cache: cache,
	}
}

// ListenForRevocations starts a background goroutine to listen for session revocations
func (m *JWTMiddleware) ListenForRevocations(ctx context.Context) {
	if m.redis == nil {
		return
	}

	pubsub := m.redis.Subscribe(ctx, "session:revocations")
	ch := pubsub.Channel()

	go func() {
		defer pubsub.Close()
		for {
			select {
			case <-ctx.Done():
				return
			case msg := <-ch:
				if msg == nil {
					continue
				}
				key := fmt.Sprintf("session:%s", msg.Payload)
				m.l1cache.Remove(key)
			}
		}
	}()
}

// checkL1Cache checks if a session exists in the L1 cache
// Returns: (exists, found) where found indicates if the key was in cache
func (m *JWTMiddleware) checkL1Cache(key string) (exists bool, found bool) {
	if entry, ok := m.l1cache.Get(key); ok {
		l1Hits.Inc()
		return entry.exists, true
	}
	l1Misses.Inc()
	return false, false
}

// checkSessionInRedis checks session status in Redis and updates L1 cache
// Returns: (exists, error)
func (m *JWTMiddleware) checkSessionInRedis(ctx context.Context, key string) (bool, error) {
	reqCtx, cancel := context.WithTimeout(ctx, 50*time.Millisecond)
	defer cancel()

	exists, err := m.redis.Exists(reqCtx, key).Result()
	if err != nil {
		redisErrors.Inc()
		return false, err
	}

	// Update L1 cache with the result
	m.l1cache.Add(key, cacheEntry{exists: exists > 0})

	return exists > 0, nil
}

// verifySession checks if a session is valid, using L1 cache first, then Redis
// Returns: (isValid, shouldDeny, err) where:
//   - isValid: session exists and is valid
//   - shouldDeny: if true, fail-secure (503); if false, fail-open (continue)
//   - err: any error that occurred
func (m *JWTMiddleware) verifySession(ctx context.Context, sessionID string, failSecure bool) (isValid bool, shouldDeny bool, err error) {
	if m.redis == nil || sessionID == "" {
		return true, false, nil
	}

	key := fmt.Sprintf("session:%s", sessionID)

	// 1. Check L1 Cache
	if exists, found := m.checkL1Cache(key); found {
		return exists, false, nil
	}

	// 2. Check Redis
	exists, err := m.checkSessionInRedis(ctx, key)
	if err != nil {
		if failSecure {
			return false, true, err
		}
		// Fail-open for optional auth: treat as unauthenticated
		return false, false, nil
	}

	return exists, false, nil
}

// Validate returns a Gin middleware that validates JWT tokens
func (m *JWTMiddleware) Validate() gin.HandlerFunc {
	return func(c *gin.Context) {
		// 1. Try to get token from cookie (BFF pattern)
		tokenString, err := c.Cookie("access_token")
		if err != nil || tokenString == "" {
			// 2. Fallback to Authorization header
			authHeader := c.GetHeader("Authorization")
			if authHeader != "" {
				parts := strings.SplitN(authHeader, " ", 2)
				if len(parts) == 2 && strings.ToLower(parts[0]) == "bearer" {
					tokenString = parts[1]
				}
			}
		}

		if tokenString == "" {
			AbortWithProblem(c, http.StatusUnauthorized, "Unauthorized", "missing authorization header", "https://api.university.edu/probs/unauthorized")
			return
		}

		// Parse and validate token
		token, err := jwt.ParseWithClaims(tokenString, &Claims{}, func(token *jwt.Token) (interface{}, error) {
			// Validate signing method
			if _, ok := token.Method.(*jwt.SigningMethodHMAC); !ok {
				return nil, jwt.ErrSignatureInvalid
			}
			return m.secret, nil
		})

		if err != nil {
			AbortWithProblem(c, http.StatusUnauthorized, "Unauthorized", "invalid token", "https://api.university.edu/probs/invalid-token")
			return
		}

		// Extract claims
		claims, ok := token.Claims.(*Claims)
		if !ok || !token.Valid {
			c.AbortWithStatusJSON(http.StatusUnauthorized, gin.H{
				"error": "invalid token claims",
			})
			return
		}

		// Edge-level Session Revocation Check with L1 Cache (fail-secure)
		isValid, shouldDeny, _ := m.verifySession(c.Request.Context(), claims.ID, true)
		if shouldDeny {
			c.AbortWithStatusJSON(http.StatusServiceUnavailable, gin.H{
				"error": "session verification temporarily unavailable",
			})
			return
		}
		if !isValid {
			AbortWithProblem(c, http.StatusUnauthorized, "Unauthorized", "session expired or revoked", "https://api.university.edu/probs/session-revoked")
			return
		}

		// Check if user is active
		if !claims.IsActive {
			c.AbortWithStatusJSON(http.StatusForbidden, gin.H{
				"error": "user account is not active",
			})
			return
		}

		// Set user info in context
		c.Set("user_id", claims.UserID)
		c.Set("user_email", claims.Email)
		c.Set("user_role", claims.Role)
		c.Set("claims", claims)

		c.Next()
	}
}

// Optional returns a middleware that extracts JWT claims but doesn't require auth
func (m *JWTMiddleware) Optional() gin.HandlerFunc {
	return func(c *gin.Context) {
		// 1. Try to get token from cookie
		tokenString, err := c.Cookie("access_token")
		if err != nil || tokenString == "" {
			// 2. Fallback to Authorization header
			authHeader := c.GetHeader("Authorization")
			if authHeader != "" {
				parts := strings.SplitN(authHeader, " ", 2)
				if len(parts) == 2 && strings.ToLower(parts[0]) == "bearer" {
					tokenString = parts[1]
				}
			}
		}

		if tokenString == "" {
			c.Next()
			return
		}

		token, err := jwt.ParseWithClaims(tokenString, &Claims{}, func(token *jwt.Token) (interface{}, error) {
			if _, ok := token.Method.(*jwt.SigningMethodHMAC); !ok {
				return nil, jwt.ErrSignatureInvalid
			}
			return m.secret, nil
		})

		if err != nil {
			// Invalid token for optional auth: continue as unauthenticated
			c.Next()
			return
		}

		claims, ok := token.Claims.(*Claims)
		if !ok || !token.Valid {
			c.Next()
			return
		}

		// Edge-level Session Revocation Check (fail-open for optional auth)
		isValid, _, _ := m.verifySession(c.Request.Context(), claims.ID, false)
		if !isValid {
			// Session revoked or invalid: continue as unauthenticated
			c.Next()
			return
		}

		// Set user info in context only if session is valid
		c.Set("user_id", claims.UserID)
		c.Set("user_email", claims.Email)
		c.Set("user_role", claims.Role)
		c.Set("claims", claims)

		c.Next()
	}
}

// RequireRole returns a middleware that requires a specific role
func RequireRole(roles ...string) gin.HandlerFunc {
	roleSet := make(map[string]bool)
	for _, role := range roles {
		roleSet[role] = true
	}

	return func(c *gin.Context) {
		userRole, exists := c.Get("user_role")
		if !exists {
			c.AbortWithStatusJSON(http.StatusForbidden, gin.H{
				"error": "role not found in token",
			})
			return
		}

		if !roleSet[userRole.(string)] {
			c.AbortWithStatusJSON(http.StatusForbidden, gin.H{
				"error": "insufficient permissions",
			})
			return
		}

		c.Next()
	}
}
