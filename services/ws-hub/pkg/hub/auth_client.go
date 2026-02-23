package hub

import (
	"context"
	"fmt"
	"net/http"
	"time"
)

// RoomAuthClient verifies that a given user is permitted to join a WebSocket room.
// The interface decouples hub.go from the concrete HTTP implementation so that
// tests can inject a stub without starting a real Python server.
type RoomAuthClient interface {
	// CanJoinRoom returns true when userID is a confirmed participant of roomID.
	// Fails closed: any network error, timeout, or non-200 response returns false.
	CanJoinRoom(userID, roomID string) bool
}

// InternalAPIAuthClient calls the Python backend's internal authorization
// endpoint to verify room membership.
// The endpoint is expected to be at:
//
//	GET <baseURL>/api/internal/chat/check-participant?user_id=<uid>&room_id=<rid>
//	→ 200 OK when the user is a participant, 403/404 otherwise.
type InternalAPIAuthClient struct {
	baseURL    string
	httpClient *http.Client
}

// NewInternalAPIAuthClient creates a production auth client.
// baseURL should be the internal hostname of the Python backend,
// e.g. "http://backend:8000".
func NewInternalAPIAuthClient(baseURL string) *InternalAPIAuthClient {
	return &InternalAPIAuthClient{
		baseURL: baseURL,
		httpClient: &http.Client{
			// Short timeout — room joins must not block the WebSocket read pump.
			Timeout: 3 * time.Second,
		},
	}
}

// CanJoinRoom calls the Python backend and returns true only on HTTP 200.
func (c *InternalAPIAuthClient) CanJoinRoom(userID, roomID string) bool {
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
