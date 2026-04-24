package hub

import (
	"context"
	"log/slog"
	"os"
	"testing"

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
		ctx:   ctx,
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
