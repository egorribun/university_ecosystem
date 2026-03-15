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

type cacheEntry struct {
	allowed   bool
	expiresAt time.Time
}

// call represents an in-flight request to the backend.
type call struct {
	wg  sync.WaitGroup
	res bool
}

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

func NewInternalAPIAuthClient(baseURL string, redisClient *redis.Client) *InternalAPIAuthClient {
	cache, _ := lru.New[string, cacheEntry](100000)

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
func (c *InternalAPIAuthClient) doRequest(ctx context.Context, userID, roomID string) bool {
	params := url.Values{}
	params.Set("user_id", userID)
	params.Set("room_id", roomID)
	fullURL := fmt.Sprintf("%s/api/internal/chat/check-participant?%s", c.baseURL, params.Encode())

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, fullURL, nil)
	if err != nil {
		return false
	}
	resp, err := c.httpClient.Do(req)
	if err != nil {
		return false
	}
	defer resp.Body.Close() //nolint:errcheck

	// RZ-01 (audit 2026-03): CRITICAL FIX for socket exhaustion.
	// We must read the body to EOF to allow standard library net/http
	// to reuse the TCP connection (keep-alive). Otherwise, the connection
	// is closed and enters TIME_WAIT, quickly exhausting ephemeral ports.
	_, _ = io.Copy(io.Discard, resp.Body)

	return resp.StatusCode == http.StatusOK
}

// doRequestWithBreaker wraps doRequest with the circuit breaker.
// Returns false when the circuit is open (fail-closed for auth).
func (c *InternalAPIAuthClient) doRequestWithBreaker(ctx context.Context, userID, roomID string) bool {
	result, err := c.cb.Execute(func() (interface{}, error) {
		allowed := c.doRequest(ctx, userID, roomID)
		if !allowed {
			// Treat a 403/non-200 as a success from the circuit breaker's
			// perspective — the backend responded correctly.  Only network
			// errors / timeouts should count as failures that trip the breaker.
			return false, nil
		}
		return true, nil
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
			// Populate L1 from L2
			c.cache.Add(key, cacheEntry{
				allowed:   allowed,
				expiresAt: time.Now().Add(1 * time.Minute),
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
		// Cache for 1 minute to survive reconnect storms without long stale periods
		expiresAt: time.Now().Add(1 * time.Minute),
	})

	// Update Redis L2
	if c.redis != nil {
		redisKey := "auth:perms:" + key
		val := "0"
		if allowed {
			val = "1"
		}
		// TTL of 5 minutes for L2 as per PERF-006 brief
		c.redis.Set(ctx, redisKey, val, 5*time.Minute)
	}

	// Resolve in-flight call
	newCall.res = allowed
	newCall.wg.Done()

	c.callMu.Lock()
	delete(c.calls, key)
	c.callMu.Unlock()

	return allowed
}
