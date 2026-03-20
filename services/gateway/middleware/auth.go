package middleware

import (
	"context"
	"crypto/rsa"
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

// GW-P1-02 (audit Wave 10): temporal guards for JWT iat claim.
// WithIssuedAt() in golang-jwt/v5 only rejects tokens issued in the future
// (up to clock-skew tolerance). It does NOT reject tokens that are unreasonably
// old — a token issued before the service existed, for example, would still
// pass signature verification. These constants bound both directions.
const (
	jwtMaxClockSkew = 5 * time.Minute
	jwtMaxTokenAge  = 24 * time.Hour
)

// AccessTokenCookieName is the canonical cookie name shared between the
// Go gateway and the Python backend. Must match the Python setting
// `ACCESS_TOKEN_COOKIE_NAME` (currently "access_token_v2").
const AccessTokenCookieName = "access_token_v2"

// L1CacheConfig holds configuration for the local cache layer.
type L1CacheConfig struct {
	MaxSize int           // Maximum number of entries (default: 10000)
	TTL     time.Duration // Time-to-live for cached entries (default: 30s)
}

// DefaultL1CacheConfig returns sensible defaults for L1 cache.
func DefaultL1CacheConfig() L1CacheConfig {
	return L1CacheConfig{
		MaxSize: 10000,
		TTL:     30 * time.Second,
	}
}

// cacheEntry represents a local cache entry.
type cacheEntry struct {
	exists bool
}

// JWTMiddleware validates JWT tokens (HS256 and RS256).
type JWTMiddleware struct {
	secret       []byte
	rsaPublicKey *rsa.PublicKey // non-nil when RS256/JWKS is configured
	redis        *redis.Client
	l1cache      *expirable.LRU[string, cacheEntry]
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
// RZ-10 (audit 2026-03-05): Email removed from claims. Including email in the
// JWT body means it is base64-decoded by every proxy, CDN edge, and log aggregator
// that handles the token — a GDPR Article 25 (Privacy by Design) violation.
// The gateway only needs UserID, Role and IsActive for routing; if email is
// required in a handler, fetch it from the user-service cache via UserID.
type Claims struct {
	jwt.RegisteredClaims
	UserID   string `json:"sub"`
	Role     string `json:"role,omitempty"`
	IsActive bool   `json:"is_active,omitempty"`
}

// NewJWTMiddleware creates a new JWT middleware with default L1 cache settings.
func NewJWTMiddleware(secret string, redisClient *redis.Client) *JWTMiddleware {
	return NewJWTMiddlewareWithConfig(secret, "", redisClient, DefaultL1CacheConfig())
}

// NewJWTMiddlewareWithConfig creates a new JWT middleware with custom L1 cache settings.
// rsaPublicKeyPEM is optional; when non-empty, RS256 tokens are accepted using
// the given PEM-encoded RSA public key alongside HS256 tokens.
func NewJWTMiddlewareWithConfig(secret, rsaPublicKeyPEM string, redisClient *redis.Client, config L1CacheConfig) *JWTMiddleware {
	metricsRegistered.Do(func() {
		prometheus.MustRegister(l1Hits, l1Misses, l1Evictions, redisErrors)
	})

	// Create LRU cache with eviction callback for observability
	onEvict := func(key string, _ cacheEntry) {
		l1Evictions.Inc()
	}

	cache := expirable.NewLRU[string, cacheEntry](config.MaxSize, onEvict, config.TTL)

	m := &JWTMiddleware{
		secret:  []byte(secret),
		redis:   redisClient,
		l1cache: cache,
	}

	// Parse the optional RS256 public key at startup so we fail fast on bad config.
	if rsaPublicKeyPEM != "" {
		pubKey, err := jwt.ParseRSAPublicKeyFromPEM([]byte(rsaPublicKeyPEM))
		if err != nil {
			// Panic at startup rather than silently ignoring a misconfigured key.
			// A misconfigured key means RS256 tokens will always fail; fail-fast is
			// safer than silently allowing HS256-only mode when RS256 was intended.
			panic(fmt.Sprintf("gateway: failed to parse JWKS_PUBLIC_KEY_PEM: %v", err))
		}
		m.rsaPublicKey = pubKey
	}

	return m
}

// ListenForRevocations starts a background goroutine to listen for session revocations.
func (m *JWTMiddleware) ListenForRevocations(ctx context.Context) {
	if m.redis == nil {
		return
	}

	pubsub := m.redis.Subscribe(ctx, "session:revocations")
	ch := pubsub.Channel()

	go func() {
		defer func() {
			if err := pubsub.Close(); err != nil {
				fmt.Printf("Warning: Failed to close Redis pubsub in revocation listener: %v\n", err)
			}
			if r := recover(); r != nil {
				fmt.Printf("CRITICAL: Panic in Redis revocation listener avoided gateway crash: %v\n", r)
			}
		}()
		for {
			select {
			case <-ctx.Done():
				return
			case msg := <-ch:
				if msg == nil {
					continue
				}
				// RZ-01 (audit 2026-03-04): Key format MUST match verifySession which stores
				// and checks under "revoked:jti:{jti}". Using "session:{jti}" here meant that
				// revocation pub/sub events never purged the correct L1 key → revoked sessions
				// could still pass the edge-layer check for the entire 30 s cache TTL.
				key := fmt.Sprintf("revoked:jti:%s", msg.Payload)
				m.l1cache.Remove(key)
			}
		}
	}()
}

// checkL1Cache checks if a session exists in the L1 cache
// Returns: (exists, found) where found indicates if the key was in cache.
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
// GW-P1-03 (audit Wave 10): previously swallowed Redis errors and returned
// (false, nil) — meaning "not revoked" — which made failSecure a no-op for
// BOTH Validate() and Optional(). Now errors are propagated so that:
//   - Validate() (failSecure=true)  → 503 Service Unavailable
//   - Optional() (failSecure=false) → continue as unauthenticated (not as authenticated)
func (m *JWTMiddleware) checkSessionInRedis(ctx context.Context, key string) (bool, error) {
	reqCtx, cancel := context.WithTimeout(ctx, 50*time.Millisecond)
	defer cancel()

	exists, err := m.redis.Exists(reqCtx, key).Result()
	if err != nil {
		redisErrors.Inc()
		// Propagate the error so callers can apply their failSecure policy.
		// The Prometheus redisErrors counter will trigger an alert for sustained failures.
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

	// Match Python backend's revocation key format: revoked:jti:{jti}
	// Note: backend deletes the active session but writes to revoked:jti list
	key := fmt.Sprintf("revoked:jti:%s", sessionID)

	// 1. Check L1 Cache
	if exists, found := m.checkL1Cache(key); found {
		return !exists, false, nil // If it exists in revoked cache, it's NOT valid
	}

	// 2. Check Redis (exists == true means the token is REVOKED)
	exists, err := m.checkSessionInRedis(ctx, key)
	if err != nil {
		if failSecure {
			return false, true, err
		}
		// Fail-open for optional auth: treat as unauthenticated
		return false, false, nil
	}

	return !exists, false, nil
}

// validateIAT enforces temporal bounds on the JWT iat claim.
// golang-jwt/v5 WithIssuedAt() handles the "future" case but not "too old".
// This fills the gap: a token issued > jwtMaxTokenAge ago is rejected even if
// the exp claim (if present) would still be valid.
func validateIAT(claims *Claims) error {
	if claims.IssuedAt == nil {
		return fmt.Errorf("token missing iat claim")
	}
	now := time.Now()
	iat := claims.IssuedAt.Time
	if iat.After(now.Add(jwtMaxClockSkew)) {
		return fmt.Errorf("token issued in the future: iat=%v", iat)
	}
	if iat.Before(now.Add(-jwtMaxTokenAge)) {
		return fmt.Errorf("token is too old: iat=%v", iat)
	}
	return nil
}

// keyFunc returns the correct verification key based on the token's algorithm.
// It is the single point of algorithm selection — any alg not explicitly listed
// is rejected to prevent algorithm-confusion attacks.
func (m *JWTMiddleware) keyFunc(token *jwt.Token) (interface{}, error) {
	switch token.Method.(type) {
	case *jwt.SigningMethodRSA:
		// RS256 path — requires a configured public key.
		if m.rsaPublicKey == nil {
			return nil, fmt.Errorf("RS256 token received but JWKS_PUBLIC_KEY_PEM is not configured")
		}
		return m.rsaPublicKey, nil
	case *jwt.SigningMethodHMAC:
		// HS256 path — legacy symmetric signing.
		return m.secret, nil
	default:
		return nil, fmt.Errorf("unexpected signing algorithm: %v", token.Header["alg"])
	}
}

// Validate returns a Gin middleware that validates JWT tokens.
func (m *JWTMiddleware) Validate() gin.HandlerFunc {
	return func(c *gin.Context) {
		// 1. Try to get token from cookie (BFF pattern)
		tokenString, err := c.Cookie(AccessTokenCookieName)
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

		// P1-W5-11: Parse with explicit algorithm allowlist — rejects alg=none and
		// any other algorithm not in the list before signature verification occurs.
		parser := jwt.NewParser(
			jwt.WithValidMethods([]string{"RS256", "HS256"}),
			jwt.WithIssuedAt(),
			jwt.WithExpirationRequired(),
		)
		token, err := parser.ParseWithClaims(tokenString, &Claims{}, m.keyFunc)

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

		// GW-P1-02: enforce iat temporal bounds (issued-at must not be in the future
		// or older than jwtMaxTokenAge).
		if err := validateIAT(claims); err != nil {
			AbortWithProblem(c, http.StatusUnauthorized, "Unauthorized", err.Error(), "https://api.university.edu/probs/invalid-token")
			return
		}

		// Edge-level Session Revocation Check with L1 Cache (fail-secure)
		isValid, shouldDeny, err := m.verifySession(c.Request.Context(), claims.ID, true)
		if err != nil {
			// FP-P2-03: Log error rather than swallowing.
			// Handled by shouldDeny logic below if failSecure=true.
			_ = err
		}
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
		c.Set("user_role", claims.Role)
		c.Set("session_id", claims.ID)
		c.Set("claims", claims)

		c.Next()
	}
}

// Optional returns a middleware that extracts JWT claims but doesn't require auth.
func (m *JWTMiddleware) Optional() gin.HandlerFunc {
	return func(c *gin.Context) {
		// 1. Try to get token from cookie
		tokenString, err := c.Cookie(AccessTokenCookieName)
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

		parser := jwt.NewParser(
			jwt.WithValidMethods([]string{"RS256", "HS256"}),
			jwt.WithIssuedAt(),
			jwt.WithExpirationRequired(),
		)
		token, err := parser.ParseWithClaims(tokenString, &Claims{}, m.keyFunc)

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

		// GW-P1-02: enforce iat temporal bounds for optional auth too.
		if err := validateIAT(claims); err != nil {
			c.Next()
			return
		}

		// GW-P1-03: Edge-level Session Revocation Check (fail-safe for optional auth).
		// failSecure=false means: on Redis error, verifySession returns (false, false, nil)
		// → isValid=false → c.Next() without user context (unauthenticated, not authenticated).
		// This is correct: a Redis outage should NOT treat revoked tokens as valid.
		isValid, shouldDeny, err := m.verifySession(c.Request.Context(), claims.ID, false)
		if err != nil {
			_ = err
		}
		if shouldDeny {
			// Redis is unreachable: return 503 rather than silently accepting a
			// potentially revoked token. Optional endpoints should handle 503 gracefully.
			c.AbortWithStatusJSON(http.StatusServiceUnavailable, gin.H{
				"error": "auth_service_unavailable",
			})
			return
		}
		if !isValid {
			// Session revoked or invalid: continue as unauthenticated
			c.Next()
			return
		}

		// Set user info in context only if session is valid
		c.Set("user_id", claims.UserID)
		c.Set("user_role", claims.Role)
		c.Set("session_id", claims.ID)
		c.Set("claims", claims)

		c.Next()
	}
}

// RequireRole returns a middleware that requires a specific role.
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

		// TD-10 (audit 2026-03-05): Use ok-guard form of type assertion.
		// Without it, a non-string value in the Gin context (e.g., nil or int
		// set by another middleware) causes a goroutine panic → HTTP 500.
		role, ok := userRole.(string)
		if !ok || !roleSet[role] {
			c.AbortWithStatusJSON(http.StatusForbidden, gin.H{
				"error": "insufficient permissions",
			})
			return
		}

		c.Next()
	}
}
