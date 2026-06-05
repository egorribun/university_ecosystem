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
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"github.com/university-ecosystem/ws-hub/pkg/config"
	"go.opentelemetry.io/otel"
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
	h := NewHub(nil, logger, &mockAuthClient{allowed: true}, cfg, nil)
	return h
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
	client.handleIncomingMessage(joinMsg, []byte(`{"type":"join","room":"room1"}`))
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
	client.handleIncomingMessage(leaveMsg, []byte(`{"type":"leave","room":"room1"}`))
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
		Rooms:  make(map[string]bool),
		Send:   make(chan []byte, 10),
		Hub:    h,
		ctx:    ctx,
	}

	// Helper to call handleMessage and recover from NATS publish panic (since NATS is nil)
	callHandleMessage := func() (panicked bool) {
		defer func() {
			if r := recover(); r != nil {
				panicked = true
			}
		}()
		msg := Message{Type: "message", Room: "room1"}
		client.handleMessage(msg, []byte(`{"type":"message","room":"room1","payload":{"text":"hello"}}`))
		return false
	}

	// First message: should pass rate limit and try to publish to NATS (causing a panic)
	panicked := callHandleMessage()
	if !panicked {
		t.Errorf("Expected first message to pass rate limiter and panic on nil NATS")
	}

	// Second message immediately after: should trigger rate limiter (returns early without NATS and writes to Send channel)
	panicked = callHandleMessage()
	if panicked {
		t.Errorf("Expected second message to be rate limited and not panic")
	}

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
	client.handleIncomingMessage(invalidMsg, []byte(`{"type":"unknown_type","room":"room1"}`))

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
		req := httptest.NewRequest(http.MethodGet, "/ws", nil)
		h.HandleWebSocket(rec, req, cfg)
		assert.Equal(t, http.StatusUnauthorized, rec.Code)
	})

	t.Run("invalid ticket length", func(t *testing.T) {
		rec := httptest.NewRecorder()
		req := httptest.NewRequest(http.MethodGet, "/ws?ticket=short", nil)
		h.HandleWebSocket(rec, req, cfg)
		assert.Equal(t, http.StatusUnauthorized, rec.Code)
	})

	t.Run("invalid ticket charset", func(t *testing.T) {
		invalidTicket := "invalid-hex-chars-that-are-long-enough-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
		rec := httptest.NewRecorder()
		req := httptest.NewRequest(http.MethodGet, "/ws?ticket="+invalidTicket, nil)
		h.HandleWebSocket(rec, req, cfg)
		assert.Equal(t, http.StatusUnauthorized, rec.Code)
	})

	t.Run("redis nil error", func(t *testing.T) {
		validTicket := "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2" // pragma: allowlist secret
		rec := httptest.NewRecorder()
		req := httptest.NewRequest(http.MethodGet, "/ws?ticket="+validTicket, nil)
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
