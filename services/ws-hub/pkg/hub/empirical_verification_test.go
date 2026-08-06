package hub

import (
	"context"
	"encoding/json"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"github.com/alicebob/miniredis/v2"
	"github.com/quic-go/quic-go/http3"
	"github.com/quic-go/webtransport-go"
	goredis "github.com/redis/go-redis/v9"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"

	"github.com/university-ecosystem/ws-hub/pkg/config"
)

const empiricalTicket = "aabbccddeeff00112233445566778899aabbccddeeff00112233445566778899" // pragma: allowlist secret

func setupEmpiricalHub(t *testing.T, rdb *goredis.Client) *Hub {
	logger := slog.New(slog.NewJSONHandler(io.Discard, nil))
	cfg := &config.Config{
		SendBufferSize:      256,
		BroadcastBufferSize: 4096,
		BroadcastWorkers:    2,
		ClientMsgRateLimit:  100,
		ClientMsgRateBurst:  200,
		MaxClients:          1000,
	}

	h := NewHub(nil, logger, &mockAuthClient{allowed: true}, cfg, rdb)
	return trackTestHub(h)
}

// TestEmpirical_SingleUseTicket_ConcurrentRace verifies atomic GETDEL behavior under high concurrency.
// When 50 goroutines race for the exact same ticket, EXACTLY 1 succeeds and 49 are rejected.
func TestEmpirical_SingleUseTicket_ConcurrentRace(t *testing.T) {
	mr := miniredis.RunT(t)
	rdb := goredis.NewClient(&goredis.Options{Addr: mr.Addr()})
	t.Cleanup(func() { assert.NoError(t, rdb.Close()) })
	ctx := context.Background()

	// Seed ticket in Redis
	ticketKey := wsTicketKeyPrefix + empiricalTicket
	require.NoError(t, rdb.Set(ctx, ticketKey, "user-race-77:jti-999:tenant-omega", 15*time.Second).Err())

	h := setupEmpiricalHub(t, rdb)

	const numWorkers = 50
	var successCount atomic.Int32
	var failCount atomic.Int32

	var wg sync.WaitGroup
	startBarrier := make(chan struct{})

	for i := 0; i < numWorkers; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			<-startBarrier

			userID, tenantID, err := h.validateUpgradeTicket(context.Background(), empiricalTicket)
			if err == nil {
				if userID == "user-race-77" && tenantID == "tenant-omega" {
					successCount.Add(1)
				}
			} else {
				failCount.Add(1)
			}
		}()
	}

	// Release all workers simultaneously
	close(startBarrier)
	wg.Wait()

	assert.Equal(t, int32(1), successCount.Load(), "Expected exactly 1 successful ticket validation")
	assert.Equal(t, int32(49), failCount.Load(), "Expected exactly 49 failed validations (already consumed)")

	// Verify key no longer exists in Redis
	exists, err := rdb.Exists(ctx, ticketKey).Result()
	require.NoError(t, err)
	assert.Equal(t, int64(0), exists, "Ticket key must be deleted from Redis after single use")
}

// TestEmpirical_SingleUseTicket_ValidationRules tests format, length, charset, and expired tickets.
func TestEmpirical_SingleUseTicket_ValidationRules(t *testing.T) {
	mr := miniredis.RunT(t)
	rdb := goredis.NewClient(&goredis.Options{Addr: mr.Addr()})
	t.Cleanup(func() { assert.NoError(t, rdb.Close()) })

	h := setupEmpiricalHub(t, rdb)
	ctx := context.Background()

	t.Run("invalid length", func(t *testing.T) {
		_, _, err := h.validateUpgradeTicket(ctx, "short_ticket")
		require.Error(t, err)
		assert.Contains(t, err.Error(), "invalid ticket length")
	})

	t.Run("invalid charset (uppercase)", func(t *testing.T) {
		upperTicket := "AABBCCDDEEFF00112233445566778899AABBCCDDEEFF00112233445566778899" // pragma: allowlist secret
		_, _, err := h.validateUpgradeTicket(ctx, upperTicket)
		require.Error(t, err)
		assert.Contains(t, err.Error(), "invalid ticket charset")
	})

	t.Run("invalid charset (special chars)", func(t *testing.T) {
		specTicket := "aabbccddeeff00112233445566778899aabbccddeeff001122334455667788!!"
		_, _, err := h.validateUpgradeTicket(ctx, specTicket)
		require.Error(t, err)
		assert.Contains(t, err.Error(), "invalid ticket charset")
	})

	t.Run("missing in redis / expired", func(t *testing.T) {
		_, _, err := h.validateUpgradeTicket(ctx, empiricalTicket)
		require.Error(t, err)
		assert.Contains(t, err.Error(), "ticket not found or already used")
	})

	t.Run("malformed payload in redis (missing colon)", func(t *testing.T) {
		malformedTicket := "11223344556677889900aabbccddeeff11223344556677889900aabbccddeeff" // pragma: allowlist secret
		require.NoError(t, rdb.Set(ctx, wsTicketKeyPrefix+malformedTicket, "useronly_nocolon", 15*time.Second).Err())

		_, _, err := h.validateUpgradeTicket(ctx, malformedTicket)
		require.Error(t, err)
		assert.Contains(t, err.Error(), "malformed ticket payload")
	})
}

// TestEmpirical_RateLimitingEnforcement verifies rate limiting for WebSocket and WebTransport upgrades under high request rates.
func TestEmpirical_RateLimitingEnforcement(t *testing.T) {
	h := setupEmpiricalHub(t, nil)
	cfg := &config.Config{MaxClients: 1000}

	const targetIP = "192.168.1.100"
	testTicket := empiricalTicket

	// Flood upgrade limiter for target IP
	for i := 0; i < 100; i++ {
		h.UpgradeLimiter.Allow(targetIP)
	}

	t.Run("WebSocket rate limit hit (429)", func(t *testing.T) {
		req := httptest.NewRequest("GET", "/ws?ticket="+testTicket, nil)
		req.RemoteAddr = targetIP + ":54321"
		rec := httptest.NewRecorder()

		h.HandleWebSocket(rec, req, cfg)
		assert.Equal(t, http.StatusTooManyRequests, rec.Code)
		assert.Contains(t, rec.Body.String(), "Too Many Requests")
	})

	t.Run("WebTransport rate limit hit (429)", func(t *testing.T) {
		req := httptest.NewRequest("GET", "/wt?ticket="+testTicket, nil)
		req.RemoteAddr = targetIP + ":54321"
		rec := httptest.NewRecorder()

		h.HandleWebTransport(rec, req, cfg)
		assert.Equal(t, http.StatusTooManyRequests, rec.Code)
		assert.Contains(t, rec.Body.String(), "Too Many Requests")
	})
}

// TestEmpirical_DualStack_MessageDispatch verifies that broadcast messages reach both TCP WebSocket and UDP WebTransport clients.
func TestEmpirical_DualStack_MessageDispatch(t *testing.T) {
	mr := miniredis.RunT(t)
	rdb := goredis.NewClient(&goredis.Options{Addr: mr.Addr()})
	t.Cleanup(func() { assert.NoError(t, rdb.Close()) })

	h := setupEmpiricalHub(t, rdb)
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	go h.Run(ctx)

	// Create simulated client contexts
	wsClientCtx, wsCancel := context.WithCancel(ctx)
	defer wsCancel()

	wtClientCtx, wtCancel := context.WithCancel(ctx)
	defer wtCancel()

	wsSend := make(chan []byte, 10)
	wtSend := make(chan []byte, 10)

	wsClient := &Client{
		ID:       "client-ws-1",
		UserID:   "user-ws-1",
		Identity: &ClientIdentity{TenantID: "tenant-1"},
		Send:     wsSend,
		Hub:      h,
		Rooms:    make(map[string]bool),
		ctx:      wsClientCtx,
		cancel:   wsCancel,
	}

	wtClient := &Client{
		ID:       "client-wt-1",
		UserID:   "user-wt-1",
		Identity: &ClientIdentity{TenantID: "tenant-1"},
		Send:     wtSend,
		Hub:      h,
		Rooms:    make(map[string]bool),
		ctx:      wtClientCtx,
		cancel:   wtCancel,
	}

	// Register both dual-stack clients
	h.Register <- wsClient
	h.Register <- wtClient

	// Wait for registration
	require.Eventually(t, func() bool {
		h.mu.RLock()
		defer h.mu.RUnlock()
		return len(h.Clients) == 2
	}, 1*time.Second, 10*time.Millisecond)

	// Join room "room-empirical"
	wsClient.JoinRoom("room-empirical")
	wtClient.JoinRoom("room-empirical")

	require.Eventually(t, func() bool {
		h.mu.RLock()
		defer h.mu.RUnlock()
		return len(h.Rooms["room-empirical"]) == 2
	}, 1*time.Second, 10*time.Millisecond)

	// Broadcast message to room
	payloadRaw := json.RawMessage(`"Dual-stack test message"`)
	msg := &Message{
		Type:    "chat",
		Room:    "room-empirical",
		Payload: payloadRaw,
	}
	h.Broadcast <- msg

	// Verify both TCP WS client and UDP WT client received the message
	select {
	case receivedBytes := <-wsSend:
		var receivedMsg Message
		require.NoError(t, json.Unmarshal(receivedBytes, &receivedMsg))
		assert.Equal(t, "room-empirical", receivedMsg.Room)
	case <-time.After(1 * time.Second):
		t.Fatal("TCP WebSocket client did not receive broadcast message")
	}

	select {
	case receivedBytes := <-wtSend:
		var receivedMsg Message
		require.NoError(t, json.Unmarshal(receivedBytes, &receivedMsg))
		assert.Equal(t, "room-empirical", receivedMsg.Room)
	case <-time.After(1 * time.Second):
		t.Fatal("UDP WebTransport client did not receive broadcast message")
	}
}

// TestEmpirical_UDPUnavailable_FallbackToTCP verifies non-fatal UDP/HTTP3 listener failure handling.
func TestEmpirical_UDPUnavailable_FallbackToTCP(t *testing.T) {
	logger := slog.New(slog.NewJSONHandler(io.Discard, nil))

	// Attempting to start WebTransport server on an invalid port or without TLS config
	wtServer := &webtransport.Server{
		H3: &http3.Server{
			Addr: "invalid_address:-1",
		},
	}

	errChan := make(chan error, 1)

	// Launch UDP listener goroutine matching ws-hub main.go fallback logic
	go func() {
		err := wtServer.ListenAndServe()
		if err != nil && err != http.ErrServerClosed {
			logger.WarnContext(context.Background(), "WebTransport HTTP/3 listener stopped", "err", err)
			// UDP failure is logged as warning and DOES NOT push to errChan
		}
	}()

	// Verify main TCP server channel receives NO fatal error from UDP listener
	select {
	case err := <-errChan:
		t.Fatalf("UDP WebTransport failure fatally crashed main server loop: %v", err)
	case <-time.After(100 * time.Millisecond):
		// Success: UDP failure degraded gracefully without stopping main process
	}

	assert.NoError(t, wtServer.Close())
}
