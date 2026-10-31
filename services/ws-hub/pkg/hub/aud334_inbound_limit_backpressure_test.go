package hub

import (
	"context"
	"errors"
	"testing"
	"time"

	"github.com/stretchr/testify/require"
)

func TestAUD334UnreportableInboundLimitClosesConnection(t *testing.T) {
	for _, queueClosed := range []bool{false, true} {
		name := "full queue"
		if queueClosed {
			name = "closed queue"
		}
		t.Run(name, func(t *testing.T) {
			h := setupTestHub()
			h.clientMsgRateLimit, h.clientMsgRateBurst = 1e-9, 1
			ctx, cancel := context.WithCancel(context.Background())
			t.Cleanup(cancel)
			session := &closeNotifyingSession{recordingSession: &recordingSession{}, closed: make(chan struct{})}
			client := &Client{ID: "limited-client", Hub: h, Conn: session, Send: make(chan []byte, 1), ctx: ctx, cancel: cancel}
			t.Cleanup(func() { safeClose(client.Send) })
			require.True(t, client.allowIncomingMessage())
			if queueClosed {
				safeClose(client.Send)
			} else {
				client.Send <- []byte("queued")
			}

			require.True(t, client.rejectRateLimitedMessage())

			require.Error(t, ctx.Err(), "a lost rate-limit notice must force reconnect")
			select {
			case <-session.closed:
			default:
				t.Fatal("a lost rate-limit notice left the transport open")
			}
		})
	}
}

func TestAUD334InboundLimitClosesWithoutHoldingMembershipLock(t *testing.T) {
	h := setupTestHub()
	h.clientMsgRateLimit, h.clientMsgRateBurst = 1e-9, 1
	ctx, cancel := context.WithCancel(context.Background())
	t.Cleanup(cancel)
	client := &Client{ID: "limited-client", UserID: "limited-user", Hub: h, Send: make(chan []byte, 1), ctx: ctx, cancel: cancel}
	t.Cleanup(func() { safeClose(client.Send) })
	require.True(t, client.allowIncomingMessage())
	client.Send <- []byte("queued")
	client.writeMu.Lock()
	locked := true
	done := make(chan struct{})
	go func() {
		client.rejectRateLimitedMessage()
		close(done)
	}()
	t.Cleanup(func() {
		if locked {
			client.writeMu.Unlock()
		}
		select {
		case <-done:
		case <-time.After(2 * time.Second):
			t.Error("rate-limit rejection did not finish during cleanup")
		}
	})
	select {
	case <-ctx.Done():
	case <-done:
		t.Fatal("a lost rate-limit notice did not start connection cleanup")
	case <-time.After(2 * time.Second):
		t.Fatal("rate-limit rejection did not begin connection cleanup")
	}
	lease := h.roomMembershipLock(client.UserID, "room")
	available := lease.entry.mu.TryLock()
	if available {
		lease.entry.mu.Unlock()
	}
	lease.release()
	client.writeMu.Unlock()
	locked = false
	select {
	case <-done:
	case <-time.After(2 * time.Second):
		t.Fatal("rate-limit rejection stayed blocked after releasing the writer")
	}
	require.True(t, available, "transport close must not retain a room membership lock")
}

func TestAUD334ReadPumpStopsWhenUnreportedInboundLimitCloseFails(t *testing.T) {
	h := setupTestHub()
	h.clientMsgRateLimit, h.clientMsgRateBurst = 1e-9, 1
	ctx, cancel := context.WithCancel(context.Background())
	t.Cleanup(cancel)
	session := &aud334CloseFailureSession{
		recordingSession: recordingSession{closeErr: errors.New("synthetic close failure")},
		frame:            []byte(`{"type":"join","room":"room"}`),
		retryRead:        make(chan struct{}), releaseRead: make(chan struct{}),
	}
	client := &Client{
		ID: "limited-client", UserID: "limited-user", Hub: h, Conn: session,
		Rooms: make(map[string]bool), Send: make(chan []byte, 1), ctx: ctx, cancel: cancel,
	}
	t.Cleanup(func() { safeClose(client.Send) })
	require.True(t, client.allowIncomingMessage())
	client.Send <- []byte("queued")
	h.handleRegister(ctx, client)
	done := make(chan struct{})
	go func() { client.ReadPump(ctx); close(done) }()
	select {
	case <-done:
	case <-session.retryRead:
		close(session.releaseRead)
		<-done
		t.Fatal("ReadPump retried after an unreportable rate-limit rejection")
	case <-time.After(2 * time.Second):
		close(session.releaseRead)
		<-done
		t.Fatal("ReadPump did not terminate after transport close failed")
	}
	require.Error(t, ctx.Err())
	h.mu.RLock()
	_, registered := h.Clients[client.ID]
	h.mu.RUnlock()
	require.False(t, registered, "ReadPump must unregister after cancellation")
}
