package hub

import (
	"context"
	"testing"

	"github.com/stretchr/testify/require"
	sdktrace "go.opentelemetry.io/otel/sdk/trace"
)

// TestHub_RecordingSpanAttributes exercises the recording-only telemetry
// branches. The normal global tracer is a non-recording noop in unit tests,
// which otherwise leaves these production branches outside the 100% gate.
func TestHub_RecordingSpanAttributes(t *testing.T) {
	h := setupTestHub()
	ctx := context.Background()
	roomClient := &Client{ID: "room-client", Send: make(chan []byte, 1), Hub: h}
	directClient := &Client{ID: "direct-client", Send: make(chan []byte, 1), Hub: h}
	h.mu.Lock()
	h.Clients[roomClient.ID] = roomClient
	h.Clients[directClient.ID] = directClient
	h.Rooms["room"] = map[*Client]bool{roomClient: true}
	h.mu.Unlock()

	provider := sdktrace.NewTracerProvider(sdktrace.WithSampler(sdktrace.AlwaysSample()))
	tracer := provider.Tracer("hub-test")
	if tracer == nil {
		t.Fatal("recording tracer provider returned a nil tracer")
	}

	_, roomSpan := tracer.Start(ctx, "room")
	recipients := h.collectRecipients(&Message{Room: "room"}, roomSpan)
	require.Len(t, recipients, 1)
	roomSpan.End()

	_, directSpan := tracer.Start(ctx, "direct")
	recipients = h.collectRecipients(&Message{To: directClient.ID}, directSpan)
	require.Len(t, recipients, 1)
	directSpan.End()

	_, globalSpan := tracer.Start(ctx, "global")
	recipients = h.collectRecipients(&Message{}, globalSpan)
	require.Len(t, recipients, 2)
	globalSpan.End()

	_, oversizedSpan := tracer.Start(ctx, "oversized")
	require.True(t, h.isOversized(ctx, &Message{Type: "test", Room: "room"}, make([]byte, 60*1024+1), oversizedSpan))
	oversizedSpan.End()
	_ = provider.Shutdown(ctx)
}
