package hub

import (
	"context"
	"testing"
	"time"

	"github.com/prometheus/client_golang/prometheus/testutil"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestReplayDisconnectCleansClientBeforeSameUserReconnect(t *testing.T) {
	h := setupTestHub()
	t.Cleanup(h.Stop)
	ctx := context.Background()
	const userID = "reconnect-user"
	const roomID = "reconnect-room"
	const secondaryRoomID = "reconnect-secondary-room"
	const disconnectedID = "replay-disconnected"
	roomIDs := []string{roomID, secondaryRoomID}
	baseline := testutil.ToFloat64(ActiveConnections)

	serverConn, _ := newConnPair(t)
	disconnected := newClientOn(h, serverConn, disconnectedID, userID)
	h.handleRegister(ctx, disconnected)
	for _, id := range roomIDs {
		disconnected.JoinRoom(id)
	}
	h.msgLimiters.Store(disconnected.ID, struct{}{})
	t.Cleanup(func() {
		disconnected.cancelConnection()
		disconnected.closeTransport("test cleanup")
		h.handleUnregister(ctx, disconnected)
	})

	readDone := make(chan struct{})
	writeDone := make(chan struct{})
	go func() {
		defer close(readDone)
		disconnected.ReadPump(disconnected.ctx)
	}()
	go func() {
		defer close(writeDone)
		disconnected.WritePump()
	}()

	disconnected.failReplayConnection()
	for name, done := range map[string]<-chan struct{}{
		"read pump":  readDone,
		"write pump": writeDone,
	} {
		select {
		case <-done:
		case <-time.After(time.Second):
			t.Fatalf("%s did not stop after replay failure", name)
		}
	}

	var stillRegistered, stillInRoom, stillInClientRooms, limiterRemains bool
	cleaned := assert.Eventually(t, func() bool {
		h.mu.RLock()
		_, stillRegistered = h.Clients[disconnected.ID]
		stillInRoom = false
		for _, id := range roomIDs {
			if _, ok := h.Rooms[id][disconnected]; ok {
				stillInRoom = true
				break
			}
		}
		h.mu.RUnlock()
		disconnected.mu.Lock()
		stillInClientRooms = false
		for _, id := range roomIDs {
			if disconnected.Rooms[id] {
				stillInClientRooms = true
				break
			}
		}
		disconnected.mu.Unlock()
		_, limiterRemains = h.msgLimiters.Load(disconnected.ID)
		return !stillRegistered && !stillInRoom && !stillInClientRooms && !limiterRemains
	}, time.Second, time.Millisecond, "disconnect must remove registry, room, and rate-limit state")
	if !cleaned {
		t.Fatalf("cleanup incomplete: registered=%t hub-room=%t client-room=%t limiter=%t", stillRegistered, stillInRoom, stillInClientRooms, limiterRemains)
	}
	h.handleUnregister(ctx, disconnected)
	h.handleUnregister(ctx, disconnected)
	assert.Equal(t, baseline, testutil.ToFloat64(ActiveConnections))
	select {
	case _, open := <-disconnected.Send:
		assert.False(t, open, "disconnected Send queue must be closed")
	default:
		t.Fatal("disconnected Send queue remained open")
	}

	newServerConn, _ := newConnPair(t)
	reconnected := newClientOn(h, newServerConn, "reconnected-client", userID)
	h.handleRegister(ctx, reconnected)
	reconnected.JoinRoom(roomID)
	t.Cleanup(func() {
		reconnected.cancelConnection()
		reconnected.closeTransport("test cleanup")
		h.handleUnregister(ctx, reconnected)
	})

	frame := []byte(`{"type":"new_message","room":"reconnect-room"}`)
	h.deliverBroadcastRecipient(
		ctx,
		&Message{Type: "new_message", Room: roomID},
		frame,
		recipient{client: reconnected, evictOnFull: true},
	)
	select {
	case got := <-reconnected.Send:
		assert.Equal(t, frame, got, "the replacement connection should receive room traffic")
	default:
		t.Fatal("the replacement connection did not receive room traffic")
	}

	reconnected.Disconnect(1000, "test complete")
	require.Eventually(t, func() bool {
		h.mu.RLock()
		defer h.mu.RUnlock()
		_, stillRegistered := h.Clients[reconnected.ID]
		return !stillRegistered && len(h.Rooms[roomID]) == 0
	}, time.Second, time.Millisecond, "replacement disconnect must also clean the room")
	assert.Equal(t, baseline, testutil.ToFloat64(ActiveConnections))
}
