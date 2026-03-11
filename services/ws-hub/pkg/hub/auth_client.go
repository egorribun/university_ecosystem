package hub

import (
	"context"
	"fmt"
	"net/http"
	"net/url"
	"sync"
	"time"

	"github.com/google/uuid"
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

	cacheMu sync.RWMutex
	cache   map[string]cacheEntry

	callMu sync.Mutex
	calls  map[string]*call
}

func NewInternalAPIAuthClient(baseURL string) *InternalAPIAuthClient {
	return &InternalAPIAuthClient{
		baseURL: baseURL,
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
		cache: make(map[string]cacheEntry),
		calls: make(map[string]*call),
	}
}

// StartEviction launches a background goroutine that periodically removes
// expired cache entries. Without eviction, the map grows unboundedly when
// users join many unique rooms (WSH-07, audit 2026-03-08 Wave 5).
//
// Call this once after NewInternalAPIAuthClient; pass the application-level
// context so the goroutine exits cleanly on shutdown.
func (c *InternalAPIAuthClient) StartEviction(ctx context.Context) {
	go func() {
		ticker := time.NewTicker(5 * time.Minute)
		defer ticker.Stop()
		for {
			select {
			case <-ctx.Done():
				return
			case <-ticker.C:
				now := time.Now()
				c.cacheMu.Lock()
				for k, v := range c.cache {
					if now.After(v.expiresAt) {
						delete(c.cache, k)
					}
				}
				c.cacheMu.Unlock()
			}
		}
	}()
}

// Invalidate removes a (userID, roomID) entry from the auth cache so that the
// next CanJoinRoom call issues a fresh request to the backend.
//
// TD-NEW-07 (audit 2026-03): Without invalidation, a removed participant
// retained a cached "allowed" result for up to 60 seconds after being kicked.
// The Python backend calls the /internal/cache/invalidate endpoint after every
// participant-removal operation to flush the stale entry immediately.
func (c *InternalAPIAuthClient) Invalidate(userID, roomID string) {
	if !isValidUUID(userID) || !isValidUUID(roomID) {
		return
	}
	key := userID + ":" + roomID
	c.cacheMu.Lock()
	delete(c.cache, key)
	c.cacheMu.Unlock()
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
	resp.Body.Close() //nolint:errcheck
	return resp.StatusCode == http.StatusOK
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
	c.cacheMu.RLock()
	entry, ok := c.cache[key]
	c.cacheMu.RUnlock()

	if ok && time.Now().Before(entry.expiresAt) {
		return entry.allowed
	}

	// 2. Slow path: single-flight request
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

	// Perform actual request with caller's context.
	allowed := c.doRequest(ctx, userID, roomID)

	// Update cache
	c.cacheMu.Lock()
	c.cache[key] = cacheEntry{
		allowed: allowed,
		// Cache for 1 minute to survive reconnect storms without long stale periods
		expiresAt: time.Now().Add(1 * time.Minute),
	}
	c.cacheMu.Unlock()

	// Resolve in-flight call
	newCall.res = allowed
	newCall.wg.Done()

	c.callMu.Lock()
	delete(c.calls, key)
	c.callMu.Unlock()

	return allowed
}
