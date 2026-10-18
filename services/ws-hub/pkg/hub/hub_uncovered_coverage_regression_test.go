package hub

import (
	"context"
	"testing"
	"time"

	"github.com/stretchr/testify/require"
	sdktrace "go.opentelemetry.io/otel/sdk/trace"
	"go.opentelemetry.io/otel/sdk/trace/tracetest"
)

func TestHub_RecordingNotificationSpanReportsRecipientCount(t *testing.T) {
	h := setupTestHub()
	first := &Client{ID: "first", UserID: "target-user", Send: make(chan []byte, 1), Hub: h}
	second := &Client{ID: "second", UserID: "target-user", Send: make(chan []byte, 1), Hub: h}
	other := &Client{ID: "other", UserID: "other-user", Send: make(chan []byte, 1), Hub: h}
	fixtures := map[string]*Client{
		first.ID:     first,
		second.ID:    second,
		other.ID:     other,
		"nil-client": nil,
	}
	h.mu.Lock()
	for id, client := range fixtures {
		h.Clients[id] = client
	}
	h.mu.Unlock()
	t.Cleanup(func() {
		h.mu.Lock()
		defer h.mu.Unlock()
		for id, fixture := range fixtures {
			if h.Clients[id] == fixture {
				delete(h.Clients, id)
			}
		}
	})

	exporter := tracetest.NewInMemoryExporter()
	provider := sdktrace.NewTracerProvider(
		sdktrace.WithSampler(sdktrace.AlwaysSample()),
		sdktrace.WithSyncer(exporter),
	)
	ctx := context.Background()
	t.Cleanup(func() { require.NoError(t, provider.Shutdown(ctx)) })

	_, span := provider.Tracer("hub-test").Start(ctx, "notification")
	recipients := h.collectRecipients(&Message{Type: "notification", To: "target-user"}, span)
	require.Len(t, recipients, 2)
	gotClients := make([]*Client, 0, len(recipients))
	for _, recipient := range recipients {
		gotClients = append(gotClients, recipient.client)
	}
	require.ElementsMatch(t, []*Client{first, second}, gotClients)
	span.End()

	spans := exporter.GetSpans()
	require.Len(t, spans, 1)
	var recipientCount int64
	foundRecipientCount := false
	for _, recordedAttribute := range spans[0].Attributes {
		if string(recordedAttribute.Key) == "recipient.count" {
			recipientCount = recordedAttribute.Value.AsInt64()
			foundRecipientCount = true
		}
	}
	require.True(t, foundRecipientCount, "recording notification span must include recipient.count")
	require.Equal(t, int64(2), recipientCount)
}

func TestWriteQueuedRoomMessageResumesAfterAdmissionOpens(t *testing.T) {
	const userID = "11111111-1111-4111-8111-111111111111"
	const roomID = "22222222-2222-4222-8222-222222222222"
	const frame = `{"type":"chat","room":"22222222-2222-4222-8222-222222222222"}`

	h := setupTestHub()
	client, session := newRevocationTestClient(h, "queued-resumes", userID, "session-jti", "websocket")
	client.JoinRoom(roomID)
	client.sessionCheckedUntil = time.Now().Add(time.Minute)
	observedCtx := &observedDoneContext{Context: client.ctx, observed: make(chan struct{})}
	client.ctx = observedCtx

	barrier := h.roomMembershipLock(userID, roomID)
	barrier.Lock()
	barrier.entry.mutationPending = true
	barrier.unlockRetained()
	barrierHeld := true
	releaseBarrier := func() {
		if !barrierHeld {
			return
		}
		barrier.Lock()
		barrier.entry.mutationPending = false
		barrier.entry.signalChangedLocked()
		barrier.unlockRetained()
		barrier.release()
		barrierHeld = false
	}

	writeDone := make(chan error, 1)
	writerFinished := false
	t.Cleanup(func() {
		releaseBarrier()
		client.cancel()
		if !writerFinished {
			select {
			case <-writeDone:
			case <-time.After(2 * time.Second):
				t.Error("queued room writer did not exit during cleanup")
			}
		}
	})
	go func() { writeDone <- client.writeQueuedMessage([]byte(frame), true) }()

	waitRoomMembershipSignal(t, observedCtx.observed, "queued room writer did not wait for the admission permit")
	session.mu.Lock()
	writesBeforeAdmission := len(session.writes)
	session.mu.Unlock()
	require.Zero(t, writesBeforeAdmission, "room frame must remain queued while admission is closed")

	releaseBarrier()
	select {
	case err := <-writeDone:
		writerFinished = true
		require.NoError(t, err)
	case <-time.After(2 * time.Second):
		t.Fatal("queued room writer did not resume after admission opened")
	}

	session.mu.Lock()
	writes := append([]recordedSessionWrite(nil), session.writes...)
	session.mu.Unlock()
	require.Len(t, writes, 1)
	require.Equal(t, []byte(frame), writes[0].data)
}
