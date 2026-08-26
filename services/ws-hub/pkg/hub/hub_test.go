package hub

import (
	"context"
	"encoding/json"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"os"
	"testing"
	"time"

	"github.com/golang-jwt/jwt/v5"
	"github.com/prometheus/client_golang/prometheus/testutil"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"github.com/university-ecosystem/ws-hub/pkg/config"
	"go.opentelemetry.io/otel"
	"golang.org/x/time/rate"
)

// mockAuthClient implements RoomAuthClient for testing.
type mockAuthClient struct {
	allowed bool
}

func (m *mockAuthClient) CanJoinRoom(ctx context.Context, userID, room string) bool {
	return m.allowed
}

func (m *mockAuthClient) Invalidate(userID, room string) {}

func setupTestHub() *Hub {
	logger := slog.New(slog.NewTextHandler(os.Stdout, nil))
	cfg := &config.Config{
		MaxClients:          10,
		BroadcastBufferSize: 10,
		BroadcastWorkers:    1,
		ClientMsgRateLimit:  10,
		ClientMsgRateBurst:  10,
	}
	// We pass nil for nats.Conn and redis.Client to avoid external dependencies.
	return trackTestHub(NewHub(nil, logger, &mockAuthClient{allowed: true}, cfg, nil))
}

func TestMessageReplayMetadataJSON(t *testing.T) {
	t.Run("common messages do not allocate replay metadata", func(t *testing.T) {
		var message Message
		require.NoError(t, json.Unmarshal([]byte(`{"type":"chat","payload":{}}`), &message))
		assert.Nil(t, message.MessageReplayMetadata)

		encoded, err := json.Marshal(message)
		require.NoError(t, err)
		assert.NotContains(t, string(encoded), `"seq"`)
		assert.NotContains(t, string(encoded), `"resume_token"`)
	})

	t.Run("replay fields retain the flat wire contract", func(t *testing.T) {
		var message Message
		require.NoError(t, json.Unmarshal([]byte(`{"type":"chat","payload":{},"seq":42,"resume_token":"token"}`), &message))
		require.NotNil(t, message.MessageReplayMetadata)
		assert.Equal(t, uint64(42), message.Seq)
		assert.Equal(t, "token", message.ResumeToken)

		encoded, err := json.Marshal(message)
		require.NoError(t, err)
		assert.JSONEq(t, `{"type":"chat","payload":{},"seq":42,"resume_token":"token"}`, string(encoded))
	})
}

func TestStartTrackedGoroutineBalancesMetric(t *testing.T) {
	baseline := testutil.ToFloat64(ActiveGoroutines)
	started := make(chan struct{})
	release := make(chan struct{})
	done := make(chan struct{})

	StartTrackedGoroutine(func() {
		close(started)
		<-release
		close(done)
	})
	<-started
	require.Eventually(t, func() bool {
		return testutil.ToFloat64(ActiveGoroutines) == baseline+1
	}, time.Second, time.Millisecond)

	close(release)
	<-done
	require.Eventually(t, func() bool {
		return testutil.ToFloat64(ActiveGoroutines) == baseline
	}, time.Second, time.Millisecond)
}

func TestHub_RegisterUnregister(t *testing.T) {
	h := setupTestHub()
	ctx := context.Background()

	client := &Client{
		ID:    "client1",
		Rooms: make(map[string]bool),
		Send:  make(chan []byte, 1),
		Hub:   h,
		ctx:   ctx,
	}

	// Test handleRegister
	h.handleRegister(ctx, client)
	h.mu.RLock()
	if len(h.Clients) != 1 {
		t.Errorf("Expected 1 client, got %d", len(h.Clients))
	}
	h.mu.RUnlock()

	// Test handleUnregister
	h.handleUnregister(ctx, client)
	h.mu.RLock()
	if len(h.Clients) != 0 {
		t.Errorf("Expected 0 clients, got %d", len(h.Clients))
	}
	h.mu.RUnlock()
}

func TestHub_Rooms(t *testing.T) {
	h := setupTestHub()
	ctx := context.Background()

	client := &Client{
		ID:     "client1",
		UserID: "user1",
		Rooms:  make(map[string]bool),
		Send:   make(chan []byte, 1),
		Hub:    h,
		ctx:    ctx,
	}

	h.handleRegister(ctx, client)

	// Test JoinRoom
	client.JoinRoom("room1")
	h.mu.RLock()
	if len(h.Rooms["room1"]) != 1 {
		t.Errorf("Expected 1 client in room1, got %d", len(h.Rooms["room1"]))
	}
	h.mu.RUnlock()

	// Test collectRecipients for a room
	msg := &Message{Room: "room1"}
	_, span := otel.Tracer("test").Start(ctx, "test")
	recipients := h.collectRecipients(msg, span)
	span.End()

	if len(recipients) != 1 {
		t.Errorf("Expected 1 recipient for room1, got %d", len(recipients))
	}

	// Test LeaveRoom
	client.LeaveRoom("room1")
	h.mu.RLock()
	if len(h.Rooms["room1"]) != 0 {
		t.Errorf("Expected 0 clients in room1, got %d", len(h.Rooms["room1"]))
	}
	h.mu.RUnlock()
}

func TestHub_CollectRecipients(t *testing.T) {
	h := setupTestHub()
	ctx := context.Background()

	client1 := &Client{
		ID:    "client1",
		Rooms: make(map[string]bool),
		Send:  make(chan []byte, 1),
		Hub:   h,
		ctx:   ctx,
	}
	client2 := &Client{
		ID:    "client2",
		Rooms: make(map[string]bool),
		Send:  make(chan []byte, 1),
		Hub:   h,
		ctx:   ctx,
	}

	h.handleRegister(ctx, client1)
	h.handleRegister(ctx, client2)

	_, span := otel.Tracer("test").Start(ctx, "test")
	defer span.End()

	// Test To specific client
	msgTo := &Message{To: "client1"}
	recipientsTo := h.collectRecipients(msgTo, span)
	if len(recipientsTo) != 1 || recipientsTo[0].client.ID != "client1" {
		t.Errorf("Expected 1 recipient client1 for direct message")
	}

	// Test Broadcast to all
	msgAll := &Message{}
	recipientsAll := h.collectRecipients(msgAll, span)
	if len(recipientsAll) != 2 {
		t.Errorf("Expected 2 recipients for global broadcast, got %d", len(recipientsAll))
	}
}

func TestHub_LimiterCleanup(t *testing.T) {
	h := setupTestHub()

	// Create a limiter for an orphaned client
	limiter, _ := h.msgLimiters.LoadOrStore("client-orphaned", "dummy-limiter")
	if limiter == nil {
		t.Errorf("Failed to store limiter")
	}

	// Manually execute the logic run by StartLimiterCleanup ticker
	active := make(map[string]struct{}, len(h.Clients))
	h.mu.RLock()
	for id := range h.Clients {
		active[id] = struct{}{}
	}
	h.mu.RUnlock()

	h.msgLimiters.Range(func(key, _ any) bool {
		if _, ok := active[key.(string)]; !ok {
			h.msgLimiters.Delete(key)
		}
		return true
	})

	_, ok := h.msgLimiters.Load("client-orphaned")
	if ok {
		t.Errorf("Limiter was not cleaned up")
	}
}

func TestHub_AuthorizeRoomJoin(t *testing.T) {
	h := setupTestHub()
	ctx := context.Background()

	// mockAuthClient always returns true
	if !h.AuthorizeRoomJoin(ctx, "user1", "room1") {
		t.Errorf("Expected AuthorizeRoomJoin to return true")
	}

	// test with nil auth client
	h.authClient = nil
	if h.AuthorizeRoomJoin(ctx, "user1", "room1") {
		t.Errorf("Expected AuthorizeRoomJoin to return false when authClient is nil")
	}
}

func TestClient_HandleIncomingMessage_JoinLeave(t *testing.T) {
	h := setupTestHub()
	ctx := context.Background()

	client := &Client{
		ID:     "client1",
		UserID: "user1",
		Rooms:  make(map[string]bool),
		Send:   make(chan []byte, 10),
		Hub:    h,
		ctx:    ctx,
	}

	// Test join
	joinMsg := Message{Type: "join", Room: "room1"}
	client.handleIncomingMessage(client.ctx, joinMsg, []byte(`{"type":"join","room":"room1"}`))
	h.mu.RLock()
	if !client.Rooms["room1"] {
		t.Errorf("Expected client to have joined room1")
	}
	if len(h.Rooms["room1"]) != 1 {
		t.Errorf("Expected room1 to have 1 client registered in Hub")
	}
	h.mu.RUnlock()

	// Test leave
	leaveMsg := Message{Type: "leave", Room: "room1"}
	client.handleIncomingMessage(client.ctx, leaveMsg, []byte(`{"type":"leave","room":"room1"}`))
	h.mu.RLock()
	if client.Rooms["room1"] {
		t.Errorf("Expected client to have left room1")
	}
	if len(h.Rooms["room1"]) != 0 {
		t.Errorf("Expected room1 to have 0 clients registered in Hub")
	}
	h.mu.RUnlock()
}

func TestClient_HandleMessage_RateLimiter(t *testing.T) {
	h := setupTestHub()
	ctx := context.Background()

	// Configure low rate limit for testing
	h.clientMsgRateLimit = 1.0
	h.clientMsgRateBurst = 1

	client := &Client{
		ID:     "client1",
		UserID: "user1",
		Rooms:  map[string]bool{"room1": true},
		Send:   make(chan []byte, 10),
		Hub:    h,
		ctx:    ctx,
	}

	// Helper to call handleMessage
	callHandleMessage := func() {
		msg := Message{Type: "message", Room: "room1"}
		client.handleMessage(msg, []byte(`{"type":"message","room":"room1","payload":{"text":"hello"}}`))
	}

	// First message: should pass rate limit (and safely return due to nil NATS guard)
	callHandleMessage()

	// Second message immediately after: should trigger rate limiter (writes to Send channel)
	callHandleMessage()

	// Assert rate_limit_exceeded notification was written to Send channel
	select {
	case notice := <-client.Send:
		var raw map[string]string
		if err := json.Unmarshal(notice, &raw); err != nil {
			t.Fatalf("Failed to parse notice: %v", err)
		}
		if raw["type"] != "rate_limit_exceeded" {
			t.Errorf("Expected type rate_limit_exceeded, got %q", raw["type"])
		}
	default:
		t.Errorf("Expected rate_limit_exceeded notice in Send channel")
	}
}

func TestClient_HandleIncomingMessage_Invalid(t *testing.T) {
	h := setupTestHub()
	ctx := context.Background()

	client := &Client{
		ID:     "client1",
		UserID: "user1",
		Rooms:  make(map[string]bool),
		Send:   make(chan []byte, 10),
		Hub:    h,
		ctx:    ctx,
	}

	// Unknown type message
	invalidMsg := Message{Type: "unknown_type", Room: "room1"}
	client.handleIncomingMessage(client.ctx, invalidMsg, []byte(`{"type":"unknown_type","room":"room1"}`))

	// Should do nothing (no panic, rooms unaffected)
	if len(client.Rooms) != 0 {
		t.Errorf("Expected rooms to remain empty")
	}
}

func TestHandleWebSocket_Errors(t *testing.T) {
	h := setupTestHub()
	cfg := &config.Config{
		TrustedProxiesSet: make(map[string]struct{}),
	}

	t.Run("missing ticket", func(t *testing.T) {
		rec := httptest.NewRecorder()
		req := httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/ws", nil)
		h.HandleWebSocket(rec, req, cfg)
		assert.Equal(t, http.StatusUnauthorized, rec.Code)
	})

	t.Run("invalid ticket length", func(t *testing.T) {
		rec := httptest.NewRecorder()
		req := httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/ws?ticket=short", nil)
		h.HandleWebSocket(rec, req, cfg)
		assert.Equal(t, http.StatusUnauthorized, rec.Code)
	})

	t.Run("invalid ticket charset", func(t *testing.T) {
		invalidTicket := "invalid-hex-chars-that-are-long-enough-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
		rec := httptest.NewRecorder()
		req := httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/ws?ticket="+invalidTicket, nil)
		h.HandleWebSocket(rec, req, cfg)
		assert.Equal(t, http.StatusUnauthorized, rec.Code)
	})

	t.Run("redis nil error", func(t *testing.T) {
		validTicket := "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2" // pragma: allowlist secret
		rec := httptest.NewRecorder()
		req := httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/ws?ticket="+validTicket, nil)
		h.redisClient = nil
		h.HandleWebSocket(rec, req, cfg)
		assert.Equal(t, http.StatusUnauthorized, rec.Code)
	})
}

func TestValidateToken(t *testing.T) {
	h := setupTestHub()

	t.Run("malformed token", func(t *testing.T) {
		_, err := h.ValidateToken(context.Background(), "invalid-token", []string{"secret"})
		assert.Error(t, err)
	})

	t.Run("unsupported algorithm", func(t *testing.T) {
		// Create a token with alg = None
		token := jwt.New(jwt.SigningMethodNone)
		tokenStr, err := token.SignedString(jwt.UnsafeAllowNoneSignatureType)
		require.NoError(t, err)

		_, err = h.ValidateToken(context.Background(), tokenStr, []string{"secret"})
		assert.Error(t, err)
		assert.Contains(t, err.Error(), "unsupported JWT algorithm")
	})

	t.Run("HS256 success", func(t *testing.T) {
		secret := "my-secret-key" // pragma: allowlist secret
		token := jwt.NewWithClaims(jwt.SigningMethodHS256, jwt.MapClaims{
			"sub": "user-123",
			"exp": time.Now().Add(time.Hour).Unix(),
		})
		tokenStr, err := token.SignedString([]byte(secret))
		require.NoError(t, err)

		sub, err := h.ValidateToken(context.Background(), tokenStr, []string{secret})
		require.NoError(t, err)
		assert.Equal(t, "user-123", sub)
	})

	t.Run("HS256 invalid signature", func(t *testing.T) {
		token := jwt.NewWithClaims(jwt.SigningMethodHS256, jwt.MapClaims{
			"sub": "user-123",
		})
		tokenStr, err := token.SignedString([]byte("correct-secret"))
		require.NoError(t, err)

		_, err = h.ValidateToken(context.Background(), tokenStr, []string{"wrong-secret"})
		assert.Error(t, err)
	})
}

// TestHub_HandleRegister_MaxClientsReject covers the capacity-reject branch in
// hub.go:219 (h.maxClients > 0 && len(h.Clients) >= h.maxClients). The 2nd
// client must hit closeOnce.Do(close(Send)) + Conn.Close() and NOT be added to
// the Clients map. newConnPair / newClientOn live in client_unit_test.go (same
// package). A non-nil *websocket.Conn is REQUIRED: handleRegister calls
// client.Conn.Close() on reject (hub.go:225) — a nil Conn would nil-panic.
func TestHub_HandleRegister_MaxClientsReject(t *testing.T) {
	h := setupTestHub()
	h.maxClients = 1 // private field, white-box override (cfg.MaxClients=10 default)
	ctx := context.Background()

	// First client: real server-side conn, registers successfully.
	srv1, _ := newConnPair(t)
	c1 := newClientOn(h, srv1, "cap-client-1", "u1")
	h.handleRegister(ctx, c1)

	h.mu.RLock()
	require.Len(t, h.Clients, 1, "first client should register")
	_, ok1 := h.Clients["cap-client-1"]
	h.mu.RUnlock()
	require.True(t, ok1)

	// Second client: hub is at capacity → reject branch (hub.go:219-228).
	srv2, _ := newConnPair(t)
	c2 := newClientOn(h, srv2, "cap-client-2", "u2")
	h.handleRegister(ctx, c2)

	// Rejected client is NOT in the map.
	h.mu.RLock()
	assert.Len(t, h.Clients, 1, "second client must be rejected at capacity")
	_, ok2 := h.Clients["cap-client-2"]
	h.mu.RUnlock()
	assert.False(t, ok2, "rejected client must not appear in Clients map")

	// Reject path ran closeOnce.Do(close(Send)) — a receive on a closed empty
	// channel returns immediately with ok=false.
	select {
	case _, recvOK := <-c2.Send:
		assert.False(t, recvOK, "rejected client's Send channel must be closed")
	default:
		t.Errorf("expected rejected client's Send channel to be closed (closeOnce ran), got open channel")
	}
}

func TestHub_StartLimiterCleanup(t *testing.T) {
	h := setupTestHub()
	h.limiterCleanupInterval = 10 * time.Millisecond

	// Put one active client and one orphaned limiter
	h.Clients["active-client"] = &Client{ID: "active-client"}

	// Add message limiters
	h.msgLimiters.Store("active-client", rate.NewLimiter(1.0, 1))
	h.msgLimiters.Store("orphaned-client", rate.NewLimiter(1.0, 1))

	ctx, cancel := context.WithCancel(context.Background())
	h.StartLimiterCleanup(ctx)

	// Wait for ticker to run
	time.Sleep(50 * time.Millisecond)
	cancel()

	_, activeExists := h.msgLimiters.Load("active-client")
	_, orphanedExists := h.msgLimiters.Load("orphaned-client")

	assert.True(t, activeExists, "active client limiter should remain")
	assert.False(t, orphanedExists, "orphaned client limiter should be cleaned up")
}
