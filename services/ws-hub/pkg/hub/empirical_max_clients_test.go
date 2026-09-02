package hub

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/alicebob/miniredis/v2"
	goredis "github.com/redis/go-redis/v9"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"

	"github.com/university-ecosystem/ws-hub/pkg/config"
)

// TestEmpirical_MaxClientsPreCheck verifies that HandleWebSocket checks hub capacity
// BEFORE attempting to upgrade the HTTP connection to WebSocket.
func TestEmpirical_MaxClientsPreCheck(t *testing.T) {
	mr := miniredis.RunT(t)
	rdb := goredis.NewClient(&goredis.Options{Addr: mr.Addr()})
	t.Cleanup(func() { assert.NoError(t, rdb.Close()) })
	ctx := context.Background()

	// Seed ticket in Redis
	validTicket := "1122334455667788990011223344556677889900112233445566778899001122" // pragma: allowlist secret
	ticketKey := wsTicketKeyPrefix + validTicket
	require.NoError(t, rdb.Set(ctx, ticketKey, "user-maxclient-test:"+validSessionJTI, 15*time.Second).Err())

	h := setupEmpiricalHub(t, rdb)
	h.maxClients = 2

	t.Run("Rejects with HTTP 503 before Upgrade when hub is at capacity", func(t *testing.T) {
		// Populate hub with 2 dummy clients to reach capacity (maxClients = 2)
		h.mu.Lock()
		h.Clients["dummy-client-1"] = &Client{ID: "dummy-1"}
		h.Clients["dummy-client-2"] = &Client{ID: "dummy-2"}
		h.mu.Unlock()

		req := httptest.NewRequest("GET", "/ws?ticket="+validTicket, nil)
		req.Header.Set("Connection", "Upgrade")
		req.Header.Set("Upgrade", "websocket")
		req.Header.Set("Sec-WebSocket-Version", "13")
		req.Header.Set("Sec-WebSocket-Key", "dGhlIHNhbXBsZSBub25jZQ==")
		req.RemoteAddr = "10.0.0.1:12345"

		rec := httptest.NewRecorder()
		cfg := &config.Config{MaxClients: 2}

		h.HandleWebSocket(rec, req, cfg)

		// Verification: Response status MUST be 503 Service Unavailable
		assert.Equal(t, http.StatusServiceUnavailable, rec.Code, "Response status code must be 503 Service Unavailable when at capacity")
		assert.Contains(t, rec.Body.String(), "Service Unavailable")
		// Verify Upgrade was NOT performed (status is NOT 101 Switching Protocols)
		assert.NotEqual(t, http.StatusSwitchingProtocols, rec.Code, "Connection must NOT be upgraded to 101 Switching Protocols")
	})

	t.Run("Allows upgrade when hub capacity is not reached", func(t *testing.T) {
		// Seed fresh ticket
		ticket2 := "9988776655443322110099887766554433221100998877665544332211009988" // pragma: allowlist secret
		require.NoError(t, rdb.Set(ctx, wsTicketKeyPrefix+ticket2, "user-maxclient-test2:"+validSessionJTI, 15*time.Second).Err())

		// Remove 1 dummy client so len(Clients) = 1 < maxClients (2)
		h.mu.Lock()
		delete(h.Clients, "dummy-client-2")
		h.mu.Unlock()

		req := httptest.NewRequest("GET", "/ws?ticket="+ticket2, nil)
		req.Header.Set("Connection", "Upgrade")
		req.Header.Set("Upgrade", "websocket")
		req.Header.Set("Sec-WebSocket-Version", "13")
		req.Header.Set("Sec-WebSocket-Key", "dGhlIHNhbXBsZSBub25jZQ==")
		req.RemoteAddr = "10.0.0.2:12345"

		rec := httptest.NewRecorder()
		cfg := &config.Config{MaxClients: 2}

		h.HandleWebSocket(rec, req, cfg)

		// Status should NOT be 503 Service Unavailable (it will proceed to upgrade, returning 101 or upgrade error)
		assert.NotEqual(t, http.StatusServiceUnavailable, rec.Code, "Pre-check should pass when below capacity")
	})
}
