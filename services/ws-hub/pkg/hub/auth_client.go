package hub

import (
	"context"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"sync"
	"time"

	"github.com/google/uuid"
	lru "github.com/hashicorp/golang-lru/v2"
	"github.com/redis/go-redis/v9"
	"github.com/sony/gobreaker"
)

// RoomAuthClient verifies that a given user is permitted to join a WebSocket room.
// WSH-05 (audit 2026-03-08 Wave 5): ctx propagation — callers pass request/shutdown
// context so that in-flight backend checks are cancelled on disconnect or shutdown.
type RoomAuthClient interface {
	CanJoinRoom(ctx context.Context, userID, roomID string) bool
	Invalidate(userID, roomID string)
}

// authCacheTTL is the single source of truth for both L1 (in-process LRU)
// and L2 (Redis) cache lifetimes.  WSH-P3-02 (audit Wave 10): previously L1
// was 1 min and L2 was 5 min, so a miss on L1 would repopulate from Redis
// with data up to 4 min stale — defeating the shorter TTL entirely.
const authCacheTTL = 1 * time.Minute

type cacheEntry struct {
	allowed   bool
	expiresAt time.Time
}

// call represents an in-flight request to the backend.
type call struct {
	wg  sync.WaitGroup
	res bool
}

// InternalAPIAuthClient implements RoomAuthClient using backend HTTP calls.
type InternalAPIAuthClient struct {
	baseURL    string
	httpClient *http.Client

	cache *lru.Cache[string, cacheEntry]
	redis *redis.Client

	callMu sync.Mutex
	calls  map[string]*call

	// MOD-03 (audit 2026-03-15 Wave 7): Circuit breaker prevents goroutine
	// accumulation when the backend is consistently unavailable.  Each
	// timed-out HTTP call occupies a goroutine for up to 3 s (httpClient
	// timeout); at 10k clients reconnecting simultaneously this saturates
	// the thread pool.  gobreaker trips after 10 consecutive failures and
	// stays open for 10 s before probing with up to 5 half-open requests.
	cb *gobreaker.CircuitBreaker
}

// NewInternalAPIAuthClient creates a client with L1/L2 caching.
func NewInternalAPIAuthClient(baseURL string, redisClient *redis.Client) *InternalAPIAuthClient {
	cache, err := lru.New[string, cacheEntry](100000)
	if err != nil {
		// FP-P2-03: Panic if LRU fails to initialize (should never happen with valid size)
		panic(fmt.Sprintf("failed to initialize LRU cache: %v", err))
	}

	// MOD-03 (audit 2026-03-15 Wave 7): Circuit breaker configuration.
	// ReadyToTrip: open after 10 consecutive HTTP failures (not cache hits).
	// Timeout: stay open for 10 s before allowing a probe (half-open).
	// MaxRequests: allow 5 probes in half-open state before deciding.
	cb := gobreaker.NewCircuitBreaker(gobreaker.Settings{
		Name:        "backend-auth",
		MaxRequests: 5,
		Interval:    30 * time.Second,
		Timeout:     10 * time.Second,
		ReadyToTrip: func(counts gobreaker.Counts) bool {
			return counts.ConsecutiveFailures > 10
		},
	})

	return &InternalAPIAuthClient{
		baseURL: baseURL,
		redis:   redisClient,
		// WSH-04 (audit 2026-03-08 Wave 5): Explicit transport configuration.
		// Go's default transport has MaxIdleConnsPerHost=0 (unlimited), which
		// can accumulate idle sockets to the backend under reconnect storms.
		// DisableCompression=true eliminates CPU overhead for internal traffic.
		httpClient: &http.Client{
			Timeout: 3 * time.Second,
			Transport: &http.Transport{
				MaxIdleConns:        100,
				MaxIdleConnsPerHost: 10,
				MaxConnsPerHost:     20,
				IdleConnTimeout:     60 * time.Second,
				DisableCompression:  true, // internal API — no benefit from gzip
			},
		},
		cache: cache,
		calls: make(map[string]*call),
		cb:    cb,
	}
}

// StartEviction is no longer needed since lru.Cache manages its own memory bound.
// We keep it as a no-op to satisfy existing interfaces if any.
func (c *InternalAPIAuthClient) StartEviction(ctx context.Context) {
	// The lru.Cache will naturally bound its size to 100k items.
	// Expired entries are ignored on read and eventually evicted when space is needed.
}

// Invalidate removes a (user, room) entry from the local cache.
func (c *InternalAPIAuthClient) Invalidate(userID, roomID string) {
	if !isValidUUID(userID) || !isValidUUID(roomID) {
		return
	}
	key := userID + ":" + roomID
	c.cache.Remove(key)
}

// isValidUUID returns true when s is a canonical RFC-4122 UUID string.
// Rejects empty strings, non-UUID garbage, and injection payloads before
// they can reach the query string or the cache key.
func isValidUUID(s string) bool {
	_, err := uuid.Parse(s)
	return err == nil
}

// doRequest performs the actual HTTP check against the backend.
// WSH-05 (audit 2026-03-08 Wave 5): accepts ctx so that the request is
// cancelled when the calling goroutine's context is done (e.g. shutdown).
//
// MOD-03 (audit 2026-03-15 Wave 7): wrapped by circuit breaker in CanJoinRoom.
//
// WSH-P1-02 (audit Wave 10): returns a non-nil error only for conditions that
// indicate backend _unavailability_ (network/DNS errors, HTTP 5xx).  HTTP 4xx
// responses mean the backend is healthy but denied the request — those are NOT
// errors from the circuit-breaker's perspective and must return (false, nil).
func (c *InternalAPIAuthClient) doRequest(ctx context.Context, userID, roomID string) (bool, error) {
	// PERF-01 (audit Wave 12): wrap the caller's context with a per-call 1.5s deadline.
	// The client-level Transport timeout (3s) bounds total TCP dial + TLS + response,
	// but under concurrent load 10 goroutines × 3s each = 30 goroutine-seconds of
	// amplified latency.  A 1.5s per-call deadline aligns with P99 SLOs and creates
	// back-pressure so slow backend responses shed load instead of accumulating.
	callCtx, cancel := context.WithTimeout(ctx, 1500*time.Millisecond)
	defer cancel()

	params := url.Values{}
	params.Set("user_id", userID)
	params.Set("room_id", roomID)
	fullURL := fmt.Sprintf("%s/api/internal/chat/check-participant?%s", c.baseURL, params.Encode())

	req, err := http.NewRequestWithContext(callCtx, http.MethodGet, fullURL, nil)
	if err != nil {
		return false, err
	}
	resp, err := c.httpClient.Do(req)
	if err != nil {
		// Network/DNS/timeout error — backend may be unavailable.
		return false, err
	}
	defer resp.Body.Close() //nolint:errcheck

	// RZ-01 (audit 2026-03): CRITICAL FIX for socket exhaustion.
	// We must read the body to EOF to allow standard library net/http
	// to reuse the TCP connection (keep-alive). Otherwise, the connection
	// is closed and enters TIME_WAIT, quickly exhausting ephemeral ports.
	if _, err := io.Copy(io.Discard, resp.Body); err != nil {
		// Log but don't fail; connection might just be closed
		_ = err
	}

	switch {
	case resp.StatusCode == http.StatusOK:
		return true, nil
	case resp.StatusCode >= 500:
		// HTTP 5xx: backend is reachable but struggling — count toward breaker.
		return false, fmt.Errorf("auth backend returned HTTP %d", resp.StatusCode)
	default:
		// HTTP 4xx (403 Forbidden, 404, etc.): healthy denial — do not trip breaker.
		return false, nil
	}
}

// doRequestWithBreaker wraps doRequest with the circuit breaker.
// Returns false when the circuit is open (fail-closed for auth).
func (c *InternalAPIAuthClient) doRequestWithBreaker(ctx context.Context, userID, roomID string) bool {
	result, err := c.cb.Execute(func() (interface{}, error) {
		// WSH-P1-02: propagate reqErr so that network errors and HTTP 5xx trip
		// the breaker, while healthy 4xx responses (backend up, access denied)
		// are returned as success to gobreaker — they measure authorization, not
		// availability.
		allowed, reqErr := c.doRequest(ctx, userID, roomID)
		if reqErr != nil {
			return false, reqErr
		}
		return allowed, nil
	})
	if err != nil {
		// gobreaker.ErrOpenState or gobreaker.ErrTooManyRequests (half-open limit)
		// → fail-closed: deny room join when backend is unreachable.
		return false
	}
	return result.(bool)
}

// CanJoinRoom checks local cache, uses single-flight to prevent thundering herd,
// and calls the Python backend on cache miss.
//
// RZ-NEW-01: Both IDs are validated as UUIDs before cache lookup and HTTP request
// to prevent URL parameter injection via crafted WebSocket messages.
// WSH-05 (audit 2026-03-08 Wave 5): ctx propagated to doRequest.
func (c *InternalAPIAuthClient) CanJoinRoom(ctx context.Context, userID, roomID string) bool {
	// Reject malformed IDs before they pollute the cache or reach the backend URL.
	if !isValidUUID(userID) || !isValidUUID(roomID) {
		return false
	}

	key := userID + ":" + roomID

	// 1. Fast path: check local TTL cache
	entry, ok := c.cache.Get(key)
	if ok && time.Now().Before(entry.expiresAt) {
		return entry.allowed
	}

	// 2. Redis L2 path: check shared cache (PERF-006)
	if c.redis != nil {
		redisKey := "auth:perms:" + key
		val, err := c.redis.Get(ctx, redisKey).Result()
		if err == nil {
			allowed := val == "1"
			// Populate L1 from L2 — use same TTL constant so L1 never outlives L2.
			c.cache.Add(key, cacheEntry{
				allowed:   allowed,
				expiresAt: time.Now().Add(authCacheTTL),
			})
			return allowed
		}
	}

	// 3. Slow path: single-flight request
	c.callMu.Lock()
	if c.calls[key] != nil {
		activeCall := c.calls[key]
		c.callMu.Unlock()
		activeCall.wg.Wait()
		return activeCall.res
	}
	newCall := new(call)
	newCall.wg.Add(1)
	c.calls[key] = newCall
	c.callMu.Unlock()

	// Perform actual request with caller's context, guarded by circuit breaker.
	allowed := c.doRequestWithBreaker(ctx, userID, roomID)

	// Update cache
	c.cache.Add(key, cacheEntry{
		allowed: allowed,
		// WSH-P3-02: use shared authCacheTTL constant (L1 = L2 = 1 min)
		expiresAt: time.Now().Add(authCacheTTL),
	})

	// Update Redis L2
	if c.redis != nil {
		redisKey := "auth:perms:" + key
		val := "0"
		if allowed {
			val = "1"
		}
		// WSH-P3-02: align L2 TTL with L1 using shared authCacheTTL constant
		c.redis.Set(ctx, redisKey, val, authCacheTTL)
	}

	// Resolve in-flight call
	newCall.res = allowed
	newCall.wg.Done()

	c.callMu.Lock()
	delete(c.calls, key)
	c.callMu.Unlock()

	return allowed
}
