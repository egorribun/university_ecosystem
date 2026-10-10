package hub

import (
	"context"
	"encoding/json"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestRoomRevocationCoversEveryUserConnectionReconnectAndShutdown(t *testing.T) {
	const (
		removedUser = "11111111-1111-1111-1111-111111111111"
		otherUser   = "33333333-3333-3333-3333-333333333333"
		roomID      = "22222222-2222-2222-2222-222222222222"
	)

	auth := &membershipRecordingAuthClient{
		memberships: map[[2]string]bool{{removedUser, roomID}: false, {otherUser, roomID}: true},
	}
	h := newNatsTestHub(auth, "internal-secret", 10) // pragma: allowlist secret
	t.Cleanup(h.Stop)
	ctx := context.Background()

	newRegisteredClient := func(id, userID string) *Client {
		t.Helper()
		serverConn, _ := newConnPair(t)
		client := newClientOn(h, serverConn, id, userID)
		h.handleRegister(ctx, client)
		return client
	}

	first := newRegisteredClient("removed-user-first", removedUser)
	second := newRegisteredClient("removed-user-second", removedUser)
	other := newRegisteredClient("other-user", otherUser)
	for _, client := range []*Client{first, second, other} {
		client.JoinRoom(roomID)
	}

	require.NoError(t, h.evictRoomMembership(ctx, removedUser, roomID))
	for _, client := range []*Client{first, second} {
		assert.False(t, client.isInRoom(roomID), "all active connections for the removed user must lose room membership")
		select {
		case frame := <-client.Send:
			var notice map[string]string
			require.NoError(t, json.Unmarshal(frame, &notice))
			assert.Equal(t, roomAccessRevokedCode, notice["code"])
			assert.Equal(t, roomID, notice["room"])
		default:
			t.Fatalf("revocation notice was not queued for %s", client.ID)
		}
	}
	assert.True(t, other.isInRoom(roomID), "revocation must preserve another user's membership")
	assert.Empty(t, other.Send, "unrelated members must not receive a revocation notice")

	recipients := h.collectRecipients(&Message{Type: "new_message", Room: roomID}, nil)
	require.Len(t, recipients, 1)
	assert.Same(t, other, recipients[0].client, "room broadcasts must no longer include either removed connection")

	reconnected := newRegisteredClient("removed-user-reconnected", removedUser)
	reconnected.handleJoin(ctx, Message{Type: "join", Room: roomID})
	assert.False(t, reconnected.isInRoom(roomID), "a reconnect must re-check current membership instead of inheriting removed access")

	auth.mu.Lock()
	auth.memberships[[2]string{removedUser, roomID}] = true
	auth.mu.Unlock()
	reconnected.handleJoin(ctx, Message{Type: "join", Room: roomID})
	assert.True(t, reconnected.isInRoom(roomID), "a later authoritative re-add may join on the new connection")

	h.Stop()
	h.mu.RLock()
	clientCount, roomCount := len(h.Clients), len(h.Rooms)
	h.mu.RUnlock()
	assert.Zero(t, clientCount, "shutdown must unregister every active connection")
	assert.Zero(t, roomCount, "shutdown must remove all room indexes")
	for _, client := range []*Client{first, second, other, reconnected} {
		assert.ErrorIs(t, client.ctx.Err(), context.Canceled, "shutdown must stop each connection")
		client.mu.Lock()
		assert.Empty(t, client.Rooms, "shutdown must clear each client's room membership")
		client.mu.Unlock()
		_, open := <-client.Send
		assert.False(t, open, "shutdown must close each client queue")
	}
}
