package hub

import (
	"context"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"log/slog"
	"testing"

	"github.com/university-ecosystem/ws-hub/pkg/config"
	"go.opentelemetry.io/otel/trace/noop"
)

// benchHub creates a minimal Hub suitable for benchmarks (no NATS, no Redis).
func benchHub() *Hub {
	logger := slog.New(slog.NewTextHandler(io.Discard, &slog.HandlerOptions{Level: slog.LevelError}))
	cfg := &config.Config{
		MaxClients:          0, // unlimited for benchmarks
		BroadcastBufferSize: 10,
		BroadcastWorkers:    1,
		ClientMsgRateLimit:  100,
		ClientMsgRateBurst:  100,
	}
	return trackTestHub(NewHub(nil, logger, &mockAuthClient{allowed: true}, cfg, nil))
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
	const bufferSize = 256
	ch := make(chan []byte, bufferSize)
	data := []byte(`{"type":"message","payload":{"text":"hello"}}`)

	b.ResetTimer()
	for range b.N {
		safeSend(ch, data)
		select {
		case <-ch:
		default:
		}
	}
}

// BenchmarkHandleRegister measures the registration path. Each iteration
// creates a fresh client and removes it afterwards to keep the map size stable.
func BenchmarkHandleRegister(b *testing.B) {
	h := benchHub()
	ctx := context.Background()
	c := benchClient(0)
	c.Hub = h

	b.ResetTimer()
	for range b.N {
		h.handleRegister(ctx, c)

		// Cleanup: remove the client so map size stays bounded.
		h.mu.Lock()
		delete(h.Clients, c.ID)
		h.mu.Unlock()
	}
}

// BenchmarkNATSPublishSimulated measures the throughput of writing a JSON
// message into a buffered channel — the same hot path that the hub uses when
// forwarding NATS payloads to connected clients.  Using a channel instead of a
// real NATS connection keeps the benchmark deterministic and network-free.
func BenchmarkNATSPublishSimulated(b *testing.B) {
	// Mirror the default broadcast channel buffer used in production config.
	const bufferSize = 256
	simulatedNATSOut := make(chan []byte, bufferSize)

	payload, err := json.Marshal(Message{
		Type:    "notification",
		Room:    "course-101",
		Payload: json.RawMessage(`{"event":"grade_updated","student_id":"u-42"}`),
	})
	if err != nil {
		b.Fatal(err)
	}

	b.ResetTimer()
	for range b.N {
		safeSend(simulatedNATSOut, payload)
		// Drain to prevent the channel from blocking after the buffer fills.
		select {
		case <-simulatedNATSOut:
		default:
		}
	}
}

// BenchmarkJWTVerify measures the cost of verifying an HMAC-SHA256 token —
// the same verification the hub performs on internal NATS messages.  A real
// HS256 key is used so the measurement includes the full crypto path, not a
// stub.  The key is generated once in the setup phase and not counted in b.N.
func BenchmarkJWTVerify(b *testing.B) {
	// Use a fixed 32-byte secret; matches the internalSecret field on Hub.
	secret := []byte("bench-internal-secret-32-byte-ok") // #nosec G101 — benchmark only

	// Build a realistic HMAC token: header.payload.signature.
	// The hub checks HMAC-SHA256 of the raw message body, not a full JWT,
	// so we simulate that exact operation.
	message := []byte(`{"type":"cache.invalidate","user_id":"u-42","room_id":"course-101"}`)

	mac := hmac.New(sha256.New, secret)
	_, _ = mac.Write(message)
	expectedSig := hex.EncodeToString(mac.Sum(nil))

	b.ResetTimer()
	for range b.N {
		// Re-create the HMAC verifier each iteration to match the hot path.
		verifier := hmac.New(sha256.New, secret)
		_, _ = verifier.Write(message)
		computedSig := hex.EncodeToString(verifier.Sum(nil))

		// Constant-time comparison prevents timing side-channels.
		if !hmac.Equal([]byte(computedSig), []byte(expectedSig)) {
			b.Fatal("HMAC verification failed — benchmark setup error")
		}
	}
}

// BenchmarkBroadcastTo1000Clients measures recipient collection for a global
// broadcast across 1000 connected clients — a stress test for the hub's hot
// path under realistic peak load.  The setup cost is excluded from b.N.
func BenchmarkBroadcastTo1000Clients(b *testing.B) {
	const totalClients = 1000
	h := benchHub()
	ctx := context.Background()

	for i := range totalClients {
		c := benchClient(i)
		c.Hub = h
		h.handleRegister(ctx, c)
	}

	msg := &Message{Type: "broadcast"}
	tracer := noop.NewTracerProvider().Tracer("bench")
	_, span := tracer.Start(context.Background(), "bench-broadcast-1000")
	defer span.End()

	b.ResetTimer()
	for range b.N {
		h.collectRecipients(msg, span)
	}
}
