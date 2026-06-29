package hub

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"os"
	"testing"

	"github.com/university-ecosystem/ws-hub/pkg/config"
	"go.opentelemetry.io/otel/trace/noop"
)

// benchHub creates a minimal Hub suitable for benchmarks (no NATS, no Redis).
func benchHub() *Hub {
	logger := slog.New(slog.NewTextHandler(os.Stdout, &slog.HandlerOptions{Level: slog.LevelError}))
	cfg := &config.Config{
		MaxClients:          0, // unlimited for benchmarks
		BroadcastBufferSize: 10,
		BroadcastWorkers:    1,
		ClientMsgRateLimit:  100,
		ClientMsgRateBurst:  100,
	}
	return NewHub(nil, logger, &mockAuthClient{allowed: true}, cfg, nil)
}

// benchClient builds a minimal Client with no WebSocket connection.
func benchClient(identifier int) *Client {
	return &Client{
		ID:     fmt.Sprintf("client-%d", identifier),
		UserID: fmt.Sprintf("user-%d", identifier),
		Rooms:  make(map[string]bool),
		Send:   make(chan []byte, 256),
	}
}

// BenchmarkMessageMarshal measures JSON encoding of a typical Message.
func BenchmarkMessageMarshal(b *testing.B) {
	msg := Message{
		Type:    "message",
		Room:    "test-room",
		Payload: json.RawMessage(`{"text":"hello world"}`),
		From:    "client-1",
	}

	b.ResetTimer()
	for range b.N {
		if _, err := json.Marshal(msg); err != nil {
			b.Fatal(err)
		}
	}
}

// BenchmarkMessageUnmarshal measures JSON decoding into a Message struct.
func BenchmarkMessageUnmarshal(b *testing.B) {
	data := []byte(`{"type":"message","room":"test-room","payload":{"text":"hello world"},"from":"client-1"}`)

	b.ResetTimer()
	for range b.N {
		var msg Message
		if err := json.Unmarshal(data, &msg); err != nil {
			b.Fatal(err)
		}
	}
}

// BenchmarkClientLookup measures map lookup by client ID with 100 entries.
func BenchmarkClientLookup(b *testing.B) {
	h := benchHub()
	ctx := context.Background()

	const totalClients = 100
	for i := range totalClients {
		c := benchClient(i)
		c.Hub = h
		h.handleRegister(ctx, c)
	}

	targetID := "client-50"

	b.ResetTimer()
	for range b.N {
		h.mu.RLock()
		_ = h.Clients[targetID]
		h.mu.RUnlock()
	}
}

// BenchmarkCollectRecipients_Room measures recipient collection for a room
// message with 50 clients in the target room.
func BenchmarkCollectRecipients_Room(b *testing.B) {
	h := benchHub()
	ctx := context.Background()

	const roomSize = 50
	roomName := "test-room"
	h.Rooms[roomName] = make(map[*Client]bool, roomSize)
	for i := range roomSize {
		c := benchClient(i)
		c.Hub = h
		h.handleRegister(ctx, c)
		c.JoinRoom(roomName)
	}

	msg := &Message{Room: roomName}
	tracer := noop.NewTracerProvider().Tracer("bench")
	_, span := tracer.Start(context.Background(), "bench")
	defer span.End()

	b.ResetTimer()
	for range b.N {
		h.collectRecipients(msg, span)
	}
}

// BenchmarkCollectRecipients_DirectMessage measures recipient collection for a
// direct (To) message.
func BenchmarkCollectRecipients_DirectMessage(b *testing.B) {
	h := benchHub()
	ctx := context.Background()

	const totalClients = 100
	for i := range totalClients {
		c := benchClient(i)
		c.Hub = h
		h.handleRegister(ctx, c)
	}

	msg := &Message{To: "client-50"}
	tracer := noop.NewTracerProvider().Tracer("bench")
	_, span := tracer.Start(context.Background(), "bench")
	defer span.End()

	b.ResetTimer()
	for range b.N {
		h.collectRecipients(msg, span)
	}
}

// BenchmarkCollectRecipients_Broadcast measures recipient collection for a
// global broadcast (no room, no To) across 100 clients.
func BenchmarkCollectRecipients_Broadcast(b *testing.B) {
	h := benchHub()
	ctx := context.Background()

	const totalClients = 100
	for i := range totalClients {
		c := benchClient(i)
		c.Hub = h
		h.handleRegister(ctx, c)
	}

	msg := &Message{Type: "message"}
	tracer := noop.NewTracerProvider().Tracer("bench")
	_, span := tracer.Start(context.Background(), "bench")
	defer span.End()

	b.ResetTimer()
	for range b.N {
		h.collectRecipients(msg, span)
	}
}

// BenchmarkSafeSend measures safeSend on a buffered channel with available
// capacity.
func BenchmarkSafeSend(b *testing.B) {
	ch := make(chan []byte, b.N+1)
	data := []byte(`{"type":"message","payload":{"text":"hello"}}`)

	b.ResetTimer()
	for range b.N {
		safeSend(ch, data)
	}
}

// BenchmarkHandleRegister measures the registration path. Each iteration
// creates a fresh client and removes it afterwards to keep the map size stable.
func BenchmarkHandleRegister(b *testing.B) {
	h := benchHub()
	ctx := context.Background()

	b.ResetTimer()
	for i := range b.N {
		c := benchClient(i)
		c.Hub = h
		h.handleRegister(ctx, c)

		// Cleanup: remove the client so map size stays bounded.
		h.mu.Lock()
		delete(h.Clients, c.ID)
		h.mu.Unlock()
	}
}
