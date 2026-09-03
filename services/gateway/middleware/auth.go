package middleware

import (
	"context"
	cryptorand "crypto/rand"
	"crypto/rsa"
	"crypto/x509"
	"encoding/base64"
	"encoding/binary"
	"encoding/json"
	"encoding/pem"
	"errors"
	"fmt"
	"io"
	"log/slog"
	"math"
	"math/big"
	"net/http"
	"sort"
	"strings"
	"sync"
	"sync/atomic"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/golang-jwt/jwt/v5"
	lru "github.com/hashicorp/golang-lru/v2"
	"github.com/prometheus/client_golang/prometheus"
	"github.com/redis/go-redis/v9"
)

var errRevocationStoreUnavailable = errors.New("session revocation store unavailable")

// GW-P1-02 (audit Wave 10): temporal guards for JWT iat claim.
// WithIssuedAt() in golang-jwt/v5 only rejects tokens issued in the future
// (up to clock-skew tolerance). It does NOT reject tokens that are unreasonably
// old — a token issued before the service existed, for example, would still
// pass signature verification. These constants bound both directions.
const (
	// DefaultJWTAudience must match app/core/config/mixins/jwt_settings.py.
	DefaultJWTAudience            = "university-ecosystem-api"
	jwtMaxClockSkew               = 5 * time.Minute
	jwtMaxTokenAge                = 24 * time.Hour
	revocationHealthCheckInterval = 500 * time.Millisecond
	revocationHealthCheckTimeout  = 100 * time.Millisecond
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

// cacheEntry represents a local cache entry with creation time for XFetch jitter.
type cacheEntry struct {
	exists   bool
	storedAt time.Time // PERF-31-02: timestamp for probabilistic early refresh
}

// rsaKeySet is an immutable snapshot of the keys published by the backend
// JWKS endpoint. The map is replaced atomically on refresh; readers never
// mutate it, so tokens signed by either side of a rotation window can be
// verified concurrently without taking a lock.
type rsaKeySet map[string]*rsa.PublicKey

// JWTMiddleware validates JWT tokens (HS256 and RS256).
type JWTMiddleware struct {
	secret   []byte
	audience string
	// rsaKeys retains every JWKS key by its JOSE kid for dual-key rotation.
	rsaKeys atomic.Pointer[rsaKeySet]
	// rsaPublicKey is a compatibility fallback for callers/tests that configure
	// a single PEM key directly. New JWKS snapshots update it to a representative
	// key, while verification prefers rsaKeys + kid lookup.
	rsaPublicKey atomic.Pointer[rsa.PublicKey] // RZ-33-19: atomic for JWKS hot-reload safety
	redis        *redis.Client
	l1cache      *lru.Cache[string, cacheEntry]
	l1TTL        time.Duration // PERF-31-02: TTL for XFetch jitter calculation
	// listenOnceFunc is an internal seam for deterministic goroutine-failure
	// testing. Production instances leave it nil and call listenOnce directly.
	listenOnceFunc func(context.Context)
}

var (
	httpDoFunc = func(client *http.Client, request *http.Request) (*http.Response, error) {
		return client.Do(request)
	}
	cryptoRandReadFunc = cryptorand.Read
	xfetchRandFunc     = secureRandomFloat64
	parseJWTClaimsFunc = func(
		parser *jwt.Parser,
		tokenString string,
		claims jwt.Claims,
		keyFunc jwt.Keyfunc,
	) (*jwt.Token, error) {
		return parser.ParseWithClaims(tokenString, claims, keyFunc)
	}
	closePubSubFunc = func(pubsub *redis.PubSub) error {
		return pubsub.Close()
	}
	pubSubChannelFunc = func(pubsub *redis.PubSub) <-chan *redis.Message {
		return pubsub.Channel()
	}
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
	// RZ-W17-02: Track revocation listener disconnects for alerting.
	revocationListenerDisconnects = prometheus.NewCounter(prometheus.CounterOpts{
		Name: "gateway_revocation_listener_disconnects_total",
		Help: "Total number of Redis pubsub disconnects in revocation listener",
	})
	// PERF-31-02: Track XFetch probabilistic cache refreshes.
	l1ProbRefreshes = prometheus.NewCounter(prometheus.CounterOpts{
		Name: "gateway_l1_cache_probabilistic_refreshes_total",
		Help: "Total number of L1 cache entries refreshed early via XFetch algorithm",
	})
	metricsRegistered sync.Once
)

// secureRandomFloat64 supplies jitter without the weak PRNG flagged by SAST.
// Jitter is not a security token; the deterministic midpoint fallback only
// preserves bounded backoff behavior if the OS entropy source is unavailable.
func secureRandomFloat64() float64 {
	var randomBytes [8]byte
	if _, err := cryptoRandReadFunc(randomBytes[:]); err != nil {
		return 0.5
	}
	const mantissaBits = 53
	const mantissaScale = float64(uint64(1) << mantissaBits)
	return float64(binary.BigEndian.Uint64(randomBytes[:])>>(64-mantissaBits)) / mantissaScale
}

var verifySessionFunc = func(
	middleware *JWTMiddleware,
	ctx context.Context,
	sessionID string,
	failSecure bool,
) (bool, bool, error) {
	return middleware.verifySession(ctx, sessionID, failSecure)
}

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
	TenantID string `json:"tenant_id,omitempty"`
}

// NewJWTMiddleware creates a new JWT middleware with default L1 cache settings.
func NewJWTMiddleware(secret string, redisClient *redis.Client) *JWTMiddleware {
	return NewJWTMiddlewareWithConfig(secret, "", redisClient, DefaultL1CacheConfig())
}

// storeRSAKeys publishes a complete JWKS snapshot atomically.  The legacy
// rsaPublicKey pointer is updated as well so older direct-PEM integrations keep
// their existing observability/test seam; authentication itself uses the map.
func (m *JWTMiddleware) storeRSAKeys(keys rsaKeySet) {
	if len(keys) == 0 {
		return
	}
	snapshot := make(rsaKeySet, len(keys))
	for kid, key := range keys {
		snapshot[kid] = key
	}
	m.rsaKeys.Store(&snapshot)
	if key, ok := snapshot[""]; ok {
		m.rsaPublicKey.Store(key)
		return
	}
	for _, key := range snapshot {
		m.rsaPublicKey.Store(key)
		break
	}
}

func (m *JWTMiddleware) rsaConfigured() bool {
	return m.rsaKeys.Load() != nil || m.rsaPublicKey.Load() != nil
}

func rsaKeySetsEqual(left, right rsaKeySet) bool {
	if len(left) != len(right) {
		return false
	}
	for kid, leftKey := range left {
		rightKey, ok := right[kid]
		if !ok || leftKey == nil || rightKey == nil || !leftKey.Equal(rightKey) {
			return false
		}
	}
	return true
}

// NewJWTMiddlewareWithConfig creates a new JWT middleware with custom L1 cache settings.
// rsaPublicKeyPEM is optional; when non-empty, RS256 tokens are accepted using
// the given PEM-encoded RSA public key alongside HS256 tokens.
func NewJWTMiddlewareWithConfig(secret, rsaPublicKeyPEM string, redisClient *redis.Client, config L1CacheConfig, audiences ...string) *JWTMiddleware {
	metricsRegistered.Do(func() {
		prometheus.MustRegister(l1Hits, l1Misses, l1Evictions, redisErrors, revocationListenerDisconnects, l1ProbRefreshes)
	})

	// Create LRU cache with eviction callback for observability
	onEvict := func(key string, _ cacheEntry) {
		l1Evictions.Inc()
	}

	cache, err := lru.NewWithEvict[string, cacheEntry](config.MaxSize, onEvict)
	if err != nil {
		panic(fmt.Sprintf("gateway: invalid L1 cache configuration: %v", err))
	}

	audience := DefaultJWTAudience
	if len(audiences) > 1 {
		panic("gateway: at most one JWT audience may be configured")
	}
	if len(audiences) == 1 {
		audience = strings.TrimSpace(audiences[0])
		if audience == "" {
			panic("gateway: JWT audience must not be blank")
		}
	}

	m := &JWTMiddleware{
		secret:   []byte(secret),
		audience: audience,
		redis:    redisClient,
		l1cache:  cache,
		l1TTL:    config.TTL, // PERF-31-02: store TTL for XFetch calculation
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
		m.storeRSAKeys(rsaKeySet{"": pubKey})
	}

	return m
}

// ---------------------------------------------------------------------------
// MOD-W17-03: JWKS hot-reload — periodic background refresh of RSA public key
// ---------------------------------------------------------------------------

var (
	jwksRefreshWG sync.WaitGroup
	jwksRefreshes = prometheus.NewCounter(prometheus.CounterOpts{
		Name: "gateway_jwks_refreshes_total",
		Help: "Total JWKS fetch attempts",
	})
	jwksRefreshErrors = prometheus.NewCounter(prometheus.CounterOpts{
		Name: "gateway_jwks_refresh_errors_total",
		Help: "Total JWKS fetch failures",
	})
	jwksKeyRotations = prometheus.NewCounter(prometheus.CounterOpts{
		Name: "gateway_jwks_key_rotations_total",
		Help: "Total RSA public key rotations via JWKS refresh",
	})
	jwksMetricsOnce sync.Once
)

// StartJWKSRefresher starts a background goroutine that periodically fetches
// the JWKS from endpoint and atomically swaps the RSA public key.  The caller
// must cancel ctx to stop the goroutine on shutdown.
func (m *JWTMiddleware) StartJWKSRefresher(ctx context.Context, endpoint string, interval time.Duration, logger *slog.Logger) {
	jwksMetricsOnce.Do(func() {
		prometheus.MustRegister(jwksRefreshes, jwksRefreshErrors, jwksKeyRotations)
	})

	httpClient := &http.Client{Timeout: 10 * time.Second}

	minRetryInterval := 2 * time.Second
	if interval < minRetryInterval {
		minRetryInterval = interval
	}
	maxRetryInterval := 30 * time.Second
	if interval < maxRetryInterval {
		maxRetryInterval = interval
	}

	jwksRefreshWG.Add(1)
	go func() {
		defer jwksRefreshWG.Done()
		var nextInterval time.Duration
		var retryCount int

		jwksRefreshes.Inc()
		newKeys, err := fetchJWKSKeySet(ctx, httpClient, endpoint)
		if err != nil {
			jwksRefreshErrors.Inc()
			retryCount = 1
			nextInterval = minRetryInterval
			logger.WarnContext(ctx, "Initial JWKS fetch failed, retrying soon", "err", err, "next_retry_in", nextInterval)
		} else {
			m.storeRSAKeys(newKeys)
			nextInterval = interval
			logger.InfoContext(ctx, "Initial JWKS fetch succeeded")
		}

		timer := time.NewTimer(nextInterval)
		defer timer.Stop()

		for {
			select {
			case <-ctx.Done():
				return
			case <-timer.C:
				jwksRefreshes.Inc()
				newKeys, err := fetchJWKSKeySet(ctx, httpClient, endpoint)
				if err != nil {
					jwksRefreshErrors.Inc()
					retryCount++
					// Exponential backoff starting at minRetryInterval, doubling on each failure.
					nextInterval = minRetryInterval * (1 << (retryCount - 1))
					if nextInterval > maxRetryInterval || nextInterval <= 0 { // overflow check
						nextInterval = maxRetryInterval
					}
					logger.WarnContext(ctx, "JWKS refresh failed, retrying", "err", err, "attempt", retryCount, "next_retry_in", nextInterval)
					timer.Reset(nextInterval)
					continue
				}

				// Reset retry count and interval on success.
				retryCount = 0
				nextInterval = interval
				timer.Reset(nextInterval)

				// Atomic swap — RZ-33-19: hot path reads via m.rsaPublicKey.Load().
				old := m.rsaKeys.Load()
				if old == nil || !rsaKeySetsEqual(*old, newKeys) {
					m.storeRSAKeys(newKeys)
					jwksKeyRotations.Inc()
					logger.InfoContext(ctx, "JWKS key rotated successfully")
				}
			}
		}
	}()
}

// fetchJWKSKeySet fetches a JWKS JSON from the given endpoint and returns every
// RSA key indexed by its JOSE key id. Supporting the complete set is required
// during dual-key rotation: tokens carrying either the retiring or current
// “kid“ remain verifiable until the old key is removed by the issuer.
func fetchJWKSKeySet(ctx context.Context, client *http.Client, endpoint string) (rsaKeySet, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, endpoint, nil)
	if err != nil {
		return nil, fmt.Errorf("jwks: create request: %w", err)
	}
	resp, err := httpDoFunc(client, req)
	if err != nil {
		return nil, fmt.Errorf("jwks: fetch: %w", err)
	}
	if resp == nil {
		return nil, fmt.Errorf("jwks: fetch: nil response")
	}
	defer resp.Body.Close() //nolint:errcheck // HTTP response body close

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("jwks: unexpected status %d", resp.StatusCode)
	}

	body, err := io.ReadAll(io.LimitReader(resp.Body, 64*1024)) // 64 KB limit
	if err != nil {
		return nil, fmt.Errorf("jwks: read body: %w", err)
	}

	// Try standard JWKS format first.
	var jwks struct {
		Keys []json.RawMessage `json:"keys"`
	}
	if err := json.Unmarshal(body, &jwks); err != nil {
		// Fallback: try parsing as raw PEM.
		key, pemErr := parseRSAPublicKeyFromPEM(body)
		if pemErr != nil {
			return nil, pemErr
		}
		return rsaKeySet{"": key}, nil
	}

	keys := make(rsaKeySet, len(jwks.Keys))
	for _, keyJSON := range jwks.Keys {
		var kty struct {
			Kty string `json:"kty"`
			N   string `json:"n"`
			E   string `json:"e"`
			Kid string `json:"kid"`
		}
		if err := json.Unmarshal(keyJSON, &kty); err != nil {
			continue
		}
		if kty.Kty == "RSA" && kty.N != "" && kty.E != "" {
			key, keyErr := jwkToRSAPublicKey(kty.N, kty.E)
			if keyErr != nil {
				return nil, keyErr
			}
			if _, duplicate := keys[kty.Kid]; duplicate {
				return nil, fmt.Errorf("jwks: duplicate RSA key id %q", kty.Kid)
			}
			keys[kty.Kid] = key
		}
	}

	if len(keys) == 0 {
		return nil, fmt.Errorf("jwks: no RSA key found in JWKS response")
	}
	return keys, nil
}

// fetchJWKSPublicKey is retained for existing single-key callers and tests.
// Authentication and refresh use fetchJWKSKeySet; this compatibility helper
// returns the sole key or a deterministic representative when multiple keys
// are present.
func fetchJWKSPublicKey(ctx context.Context, client *http.Client, endpoint string) (*rsa.PublicKey, error) {
	keys, err := fetchJWKSKeySet(ctx, client, endpoint)
	if err != nil {
		return nil, err
	}
	return selectJWKSRepresentative(keys)
}

// selectJWKSRepresentative returns the compatibility key used by callers that
// predate dual-key JWKS support.  A blank kid is the legacy single-key form;
// otherwise choose the lexicographically first kid so the result is stable
// across map iterations.  fetchJWKSKeySet normally guarantees a non-empty set,
// but keeping the invariant check here makes this helper safe for all callers.
func selectJWKSRepresentative(keys rsaKeySet) (*rsa.PublicKey, error) {
	if key, ok := keys[""]; ok {
		return key, nil
	}
	if len(keys) == 0 {
		return nil, fmt.Errorf("jwks: no RSA key found in JWKS response")
	}
	kids := make([]string, 0, len(keys))
	for kid := range keys {
		kids = append(kids, kid)
	}
	sort.Strings(kids)
	return keys[kids[0]], nil
}

func jwkToRSAPublicKey(nB64, eB64 string) (*rsa.PublicKey, error) {
	nBytes, err := base64.RawURLEncoding.DecodeString(nB64)
	if err != nil {
		return nil, fmt.Errorf("jwks: decode n: %w", err)
	}
	eBytes, err := base64.RawURLEncoding.DecodeString(eB64)
	if err != nil {
		return nil, fmt.Errorf("jwks: decode e: %w", err)
	}

	// Convert e bytes to int (big-endian).
	var eInt int
	for _, b := range eBytes {
		eInt = eInt<<8 + int(b)
	}

	n := new(big.Int).SetBytes(nBytes)
	return &rsa.PublicKey{
		N: n,
		E: eInt,
	}, nil
}

func parseRSAPublicKeyFromPEM(data []byte) (*rsa.PublicKey, error) {
	block, _ := pem.Decode(data)
	if block == nil {
		return nil, fmt.Errorf("jwks: no PEM block found")
	}
	pub, err := x509.ParsePKIXPublicKey(block.Bytes)
	if err != nil {
		return nil, fmt.Errorf("jwks: parse public key: %w", err)
	}
	rsaPub, ok := pub.(*rsa.PublicKey)
	if !ok {
		return nil, fmt.Errorf("jwks: key is not RSA")
	}
	return rsaPub, nil
}

// WarmL1Cache pre-populates the L1 cache by scanning Redis for currently
// revoked JTIs. This avoids the cold-start penalty after a deploy where every
// request would require a Redis round-trip until the L1 TTL fills naturally.
//
// PERF-W17-02 (Wave 17): Bounded to 10,000 keys and 5s timeout to prevent
// startup stalls. If Redis is unavailable, warmup is silently skipped.
func (m *JWTMiddleware) WarmL1Cache(ctx context.Context) {
	if m.redis == nil {
		return
	}
	warmCtx, cancel := context.WithTimeout(ctx, 5*time.Second)
	defer cancel()

	const maxWarmupKeys = 10000
	var cursor uint64
	var count int

	for count < maxWarmupKeys {
		keys, nextCursor, err := m.redis.Scan(warmCtx, cursor, "revoked:jti:*", 500).Result()
		if err != nil {
			slog.WarnContext(ctx, "L1 cache warmup: Redis scan failed, skipping",
				"err", err, "warmed", count)
			return
		}
		for _, key := range keys {
			m.l1cache.Add(key, cacheEntry{exists: true, storedAt: time.Now()})
			count++
			if count >= maxWarmupKeys {
				break
			}
		}
		cursor = nextCursor
		if cursor == 0 {
			break
		}
	}
	slog.InfoContext(ctx, "L1 cache warmed from Redis", "entries", count)
}

// ListenForRevocations starts a background goroutine to listen for session revocations.
//
// The listener actively health-checks Redis because go-redis Pub/Sub channels
// reconnect transparently and therefore do not reliably close on a network
// outage. On a failed health check, the listener returns, purges L1, and
// reconnects with jittered exponential backoff.
func (m *JWTMiddleware) ListenForRevocations(ctx context.Context) {
	if m.redis == nil {
		return
	}

	go func() {
		defer func() {
			if r := recover(); r != nil {
				slog.ErrorContext(ctx, "panic in Redis revocation listener recovered",
					"panic", r, "event", "revocation_listener_panic")
			}
		}()

		const (
			baseDelay = 1 * time.Second
			maxDelay  = 30 * time.Second
		)
		attempt := 0

		for {
			if ctx.Err() != nil {
				return
			}

			if m.listenOnceFunc != nil {
				m.listenOnceFunc(ctx)
			} else {
				m.listenOnce(ctx)
			}
			if ctx.Err() != nil {
				return
			}

			// Channel closed — Redis disconnected.
			revocationListenerDisconnects.Inc()
			// RZ-W17-02: Purge L1 cache so every check hits Redis directly.
			// This is fail-safe: if Redis is down, checkSessionInRedis returns
			// an error and failSecure logic kicks in (503 for Validate, unauth
			// for Optional).
			m.l1cache.Purge()

			attempt++
			delay := time.Duration(math.Min(
				float64(baseDelay)*math.Pow(2, float64(attempt-1)),
				float64(maxDelay),
			))
			// Jitter: 75%-125% of computed delay.
			jitter := 0.75 + secureRandomFloat64()*0.5
			delay = time.Duration(float64(delay) * jitter)

			slog.ErrorContext(ctx, "Redis pubsub disconnected — revocation listener lost, reconnecting",
				"attempt", attempt, "backoff", delay.String(),
				"event", "revocation_listener_disconnect")

			select {
			case <-ctx.Done():
				return
			case <-time.After(delay):
			}
		}
	}()
}

// listenOnce subscribes to revocation events and processes them until the
// channel closes, an explicit Redis health check fails, or context is cancelled.
func (m *JWTMiddleware) listenOnce(ctx context.Context) {
	pubsub := m.redis.Subscribe(ctx, "session:revocations")
	defer func() {
		if err := closePubSubFunc(pubsub); err != nil {
			slog.WarnContext(ctx, "failed to close Redis pubsub in revocation listener",
				"err", err, "event", "pubsub_close_error")
		}
	}()

	ch := pubSubChannelFunc(pubsub)
	healthTicker := time.NewTicker(revocationHealthCheckInterval)
	defer healthTicker.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case msg, ok := <-ch:
			if !ok {
				return
			}
			// Backend writes the tombstone before publishing. Cache the safe,
			// positive revocation decision immediately; never cache a negative
			// "not revoked" result that could outlive Redis connectivity.
			key := fmt.Sprintf("revoked:jti:%s", msg.Payload)
			m.l1cache.Add(key, cacheEntry{exists: true, storedAt: time.Now()})
		case <-healthTicker.C:
			healthCtx, cancel := context.WithTimeout(ctx, revocationHealthCheckTimeout)
			err := m.redis.Ping(healthCtx).Err()
			cancel()
			if err != nil {
				return
			}
		}
	}
}

// shouldRefreshProbabilistic implements the XFetch algorithm to prevent cache
// stampede.  Some fraction of requests will trigger a background refresh before
// the entry's TTL expires, spreading revalidation load across time.
// Ported from Python: app/deps/cache.py:56-92 (PERF-31-02).
func shouldRefreshProbabilistic(storedAt time.Time, ttl time.Duration, beta float64) bool {
	remaining := ttl - time.Since(storedAt)
	if remaining <= 0 {
		return true
	}
	randFactor := xfetchRandFunc() // #nosec G404 — non-cryptographic use
	if randFactor == 0 {
		randFactor = 1e-10
	}
	threshold := -beta * ttl.Seconds() * math.Log(randFactor)
	return remaining.Seconds() < threshold
}

// checkL1Cache checks if a session exists in the L1 cache.
// Returns: (exists, found) where found indicates if the key was in cache.
// PERF-31-02: Uses XFetch algorithm — probabilistically returns a "miss" for
// entries nearing expiry, spreading Redis revalidation across requests.
func (m *JWTMiddleware) checkL1Cache(key string) (exists bool, found bool) {
	if entry, ok := m.l1cache.Get(key); ok {
		// Negative revocation decisions are deliberately never trusted locally.
		// A Redis or Pub/Sub partition must force a live Redis check and therefore
		// a fail-closed 503 for required authentication.
		if !entry.exists {
			m.l1cache.Remove(key)
			l1Misses.Inc()
			return false, false
		}
		if shouldRefreshProbabilistic(entry.storedAt, m.l1TTL, 1.0) {
			l1ProbRefreshes.Inc()
			// Trigger a Redis re-check by returning "not found" in cache,
			// but the caller will still get the correct result from Redis.
			return false, false
		}
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

	// Cache only positive revocation tombstones. Negative caching is unsafe:
	// it can authenticate revoked tokens while Redis/PubSub is partitioned.
	if exists > 0 {
		m.l1cache.Add(key, cacheEntry{exists: true, storedAt: time.Now()})
	} else {
		m.l1cache.Remove(key)
	}

	return exists > 0, nil
}

// verifySession checks if a session is valid, using L1 cache first, then Redis
// Returns: (isValid, shouldDeny, err) where:
//   - isValid: session exists and is valid
//   - shouldDeny: if true, required auth must fail-secure with 503
//   - err: any error that occurred
func (m *JWTMiddleware) verifySession(ctx context.Context, sessionID string, failSecure bool) (isValid bool, shouldDeny bool, err error) {
	if m.redis == nil {
		redisErrors.Inc()
		return false, failSecure, errRevocationStoreUnavailable
	}
	// FIX-JTI-01: A token with no JTI (jti / claims.ID) cannot be correlated with
	// a Redis session entry, so it must be treated as invalid rather than valid.
	// Previously this branch returned (true, false, nil) — i.e. "valid, no deny" —
	// which allowed JTI-less tokens to bypass session revocation checks entirely.
	if sessionID == "" {
		slog.WarnContext(ctx, "JWT missing jti claim — rejecting token",
			"event", "jwt_missing_jti")
		return false, false, nil
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

// extractAlgFromHeader decodes the JWT header without validating the signature
// and returns the "alg" field.  Reading the algorithm BEFORE calling
// jwt.ParseWithClaims provides a defense-in-depth check against algorithm-
// confusion attacks where the token header is crafted to select a weaker alg.
//
// RZ-W15-01 (audit 2026-03-23 Wave 15): Added to achieve parity with ws-hub's
// extractAlgFromHeader (handlers.go, RZ-W14-02).  The golang-jwt WithValidMethods
// guard fires inside ParseWithClaims — this check fires before parsing so that
// the downgrade attempt is rejected and logged before any cryptographic work.
func extractAlgFromHeader(tokenString string) (string, error) {
	parts := strings.SplitN(tokenString, ".", 3)
	if len(parts) != 3 {
		return "", fmt.Errorf("malformed JWT: expected 3 dot-separated parts, got %d", len(parts))
	}
	headerBytes, err := base64.RawURLEncoding.DecodeString(parts[0])
	if err != nil {
		return "", fmt.Errorf("malformed JWT header (base64): %w", err)
	}
	var header struct {
		Alg string `json:"alg"`
	}
	if err := json.Unmarshal(headerBytes, &header); err != nil {
		return "", fmt.Errorf("malformed JWT header (json): %w", err)
	}
	if header.Alg == "" {
		return "", fmt.Errorf("JWT header missing 'alg' field")
	}
	return header.Alg, nil
}

// keyFunc returns the correct verification key based on the token's algorithm.
// It is the single point of algorithm selection — any alg not explicitly listed
// is rejected to prevent algorithm-confusion attacks.
//
// RZ-W15-01: When rsaPublicKey is configured, HS256 is explicitly rejected here
// as a second line of defence (the first is extractAlgFromHeader called before
// ParseWithClaims).  An attacker cannot downgrade to HS256 to forge tokens using
// the RSA public key as an HMAC secret.
func (m *JWTMiddleware) keyFunc(token *jwt.Token) (interface{}, error) {
	switch token.Method.(type) {
	case *jwt.SigningMethodRSA:
		// RS256 path — resolve the JOSE kid against the complete JWKS snapshot.
		if keys := m.rsaKeys.Load(); keys != nil {
			kid, _ := token.Header["kid"].(string)
			if key, ok := (*keys)[kid]; ok {
				return key, nil
			}
			if kid == "" && len(*keys) == 1 {
				for _, key := range *keys {
					return key, nil
				}
			}
			if kid == "" {
				return nil, fmt.Errorf("RS256 token is missing kid while multiple JWKS keys are configured")
			}
			return nil, fmt.Errorf("RS256 token references unknown JWKS key id %q", kid)
		}
		// Compatibility path for a directly configured PEM key.
		if key := m.rsaPublicKey.Load(); key != nil {
			return key, nil
		}
		return nil, fmt.Errorf("RS256 token received but JWKS_PUBLIC_KEY_PEM is not configured")
	case *jwt.SigningMethodHMAC:
		// HS256 path — only allowed when RS256 is NOT configured.
		// If rsaPublicKey is set, the deployment intends RS256-only; accepting HS256
		// alongside RS256 would allow an attacker with knowledge of the HMAC secret
		// to forge tokens even after the RS256 key is rotated.
		if m.rsaConfigured() {
			return nil, fmt.Errorf("HS256 token rejected: RS256 is configured and HS256 is not accepted alongside it")
		}
		return m.secret, nil
	default:
		return nil, fmt.Errorf("unexpected signing algorithm: %v", token.Header["alg"])
	}
}

// Validate returns a Gin middleware that validates JWT tokens.
func (m *JWTMiddleware) Validate(ctx context.Context) gin.HandlerFunc { //nolint:gocognit,cyclop // JWT validation is inherently complex
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

		// RZ-W15-01: Pre-parse algorithm check — mirrors ws-hub's extractAlgFromHeader.
		// Reads the alg claim from the JOSE header before any signature work, so that
		// an algorithm downgrade attempt is caught and logged early.
		if m.rsaConfigured() {
			alg, algErr := extractAlgFromHeader(tokenString)
			if algErr != nil {
				AbortWithProblem(c, http.StatusUnauthorized, "Unauthorized", "malformed token header", "https://api.university.edu/probs/invalid-token")
				return
			}
			if alg != "RS256" {
				// TD-W17-01: Structured logging for SOC/SIEM algorithm downgrade detection.
				slog.WarnContext(ctx, "algorithm downgrade attempt rejected",
					"alg", alg, "remote", c.ClientIP(), "event", "jwt_alg_downgrade")
				AbortWithProblem(c, http.StatusUnauthorized, "Unauthorized", "invalid token algorithm", "https://api.university.edu/probs/invalid-token")
				return
			}
		}

		// P1-W5-11: Parse with explicit algorithm allowlist — rejects alg=none and
		// any other algorithm not in the list before signature verification occurs.
		// RZ-W16-07: Restrict allowlist to RS256-only when RSA key is configured.
		validMethods := []string{"RS256", "HS256"}
		if m.rsaConfigured() {
			validMethods = []string{"RS256"}
		}
		parser := jwt.NewParser(
			jwt.WithValidMethods(validMethods),
			jwt.WithIssuedAt(),
			jwt.WithExpirationRequired(),
			jwt.WithAudience(m.audience),
		)
		token, err := parseJWTClaimsFunc(parser, tokenString, &Claims{}, m.keyFunc)

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
		isValid, shouldDeny, err := m.verifySession(ctx, claims.ID, true)
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

		// Tenant identity is accepted only from signed claims. A client-supplied
		// X-Tenant-ID is a routing hint, not authenticated membership, and must
		// never be promoted into signed gateway identity headers. The current
		// Python login issuer emits no tenant claim until authoritative membership
		// resolution exists, so production tenant context is intentionally empty.
		tenantID := claims.TenantID
		c.Set("user_id", claims.UserID)
		c.Set("user_role", claims.Role)
		c.Set("session_id", claims.ID)
		c.Set("tenant_id", tenantID)
		c.Set("claims", claims)

		c.Next()
	}
}

// Optional returns a middleware that extracts JWT claims but doesn't require auth.
func (m *JWTMiddleware) Optional(ctx context.Context) gin.HandlerFunc { //nolint:gocognit,cyclop // mirrors Validate complexity
	return func(c *gin.Context) {
		tenantID := ""

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

		// RZ-W15-01: Same pre-parse algorithm check as Validate() for optional auth.
		if m.rsaConfigured() {
			alg, algErr := extractAlgFromHeader(tokenString)
			if algErr != nil || alg != "RS256" {
				// Malformed header or downgrade attempt — treat as unauthenticated.
				if algErr == nil {
					slog.WarnContext(ctx, "algorithm downgrade attempt rejected (optional)",
						"alg", alg, "remote", c.ClientIP(), "event", "jwt_alg_downgrade")
				}
				c.Next()
				return
			}
		}

		// RZ-W16-07: Restrict allowlist to RS256-only when RSA key is configured.
		optValidMethods := []string{"RS256", "HS256"}
		if m.rsaConfigured() {
			optValidMethods = []string{"RS256"}
		}
		parser := jwt.NewParser(
			jwt.WithValidMethods(optValidMethods),
			jwt.WithIssuedAt(),
			jwt.WithExpirationRequired(),
			jwt.WithAudience(m.audience),
		)
		token, err := parseJWTClaimsFunc(parser, tokenString, &Claims{}, m.keyFunc)

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
		isValid, shouldDeny, err := verifySessionFunc(m, ctx, claims.ID, false)
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
		if claims.TenantID != "" {
			tenantID = claims.TenantID
		}
		c.Set("user_id", claims.UserID)
		c.Set("user_role", claims.Role)
		c.Set("session_id", claims.ID)
		c.Set("tenant_id", tenantID)
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
