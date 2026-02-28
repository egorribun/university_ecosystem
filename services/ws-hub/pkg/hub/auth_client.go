package hub

import (
	"context"
	"fmt"
	"net/http"
	"sync"
	"time"
)

// RoomAuthClient verifies that a given user is permitted to join a WebSocket room.
type RoomAuthClient interface {
	CanJoinRoom(userID, roomID string) bool
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
		httpClient: &http.Client{
			// Short timeout — room joins must not block the WebSocket read pump.
			Timeout: 3 * time.Second,
		},
		cache: make(map[string]cacheEntry),
		calls: make(map[string]*call),
	}
}

func (c *InternalAPIAuthClient) doRequest(userID, roomID string) bool {
	url := fmt.Sprintf(
		"%s/api/internal/chat/check-participant?user_id=%s&room_id=%s",
		c.baseURL, userID, roomID,
	)
	req, err := http.NewRequestWithContext(context.Background(), http.MethodGet, url, nil)
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
func (c *InternalAPIAuthClient) CanJoinRoom(userID, roomID string) bool {
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

	// Perform actual request
	allowed := c.doRequest(userID, roomID)

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
