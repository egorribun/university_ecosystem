package hub

import (
	"context"
	"testing"
	"time"

	"github.com/stretchr/testify/require"
)

// TestAUD334SupersededReplayRefusalKeepsCurrentOwnerThroughBlockedRevocation composes
// the three AUD-334 hazards on one connection. A replay is superseded by a newer
// replay for the same room, and the socket writer is blocked mid-frame when a
// membership revocation arrives. The superseded refusal must leave the connection and
// the current owner alone. The revocation must wait for the in-flight write to drain.
// Afterwards the room, the current replay owner, and every queued room frame are gone,
// while the connection itself survives and the superseded refusal stays harmless.
func TestAUD334SupersededReplayRefusalKeepsCurrentOwnerThroughBlockedRevocation(t *testing.T) {
	const userID = "11111111-1111-1111-1111-111111111111"
	const roomID = "22222222-2222-2222-2222-222222222222"
	refreshStarted := make(chan struct{})
	refreshResult := make(chan bool, 1)
	auth := &controlledRoomMembershipAuth{
		canJoin: func(context.Context, string, string) bool { return true },
		refresh: func(context.Context, string, string) (bool, error) {
			close(refreshStarted)
			return <-refreshResult, nil
		},
	}
	h := newNatsTestHub(auth, "internal-secret", 10)
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	order := &roomWriteOrder{}
	session := &blockedRoomWriteSession{
		writeStarted: make(chan struct{}, 2),
		allowWrite:   make(chan struct{}),
		order:        order,
	}
	client := &Client{
		ID:               "superseded-replay-client",
		SessionJTI:       validSessionJTI,
		SessionExpiresAt: time.Now().Add(time.Hour),
		UserID:           userID,
		Rooms:            make(map[string]bool),
		Conn:             session,
		Send:             make(chan []byte, 2),
		Hub:              h,
		ctx:              ctx,
		cancel:           cancel,
	}
	client.JoinRoom(roomID)
	privateFrame := []byte(`{"type":"new_message","room":"22222222-2222-2222-2222-222222222222","payload":{"text":"private"}}`)
	client.Send <- privateFrame
	client.Send <- privateFrame
	close(client.Send)
	writeDone := make(chan struct{})
	go func() {
		client.WritePump()
		close(writeDone)
	}()
	waitRoomMembershipSignal(t, session.writeStarted, "first room frame did not enter the blocked socket write")

	// Two replays for the same room: the second supersedes the first, which is
	// cancelled by prepareRoomReplay.
	_, superseded := client.prepareRoomReplay(ctx, roomID)
	_, current := client.prepareRoomReplay(ctx, roomID)
	client.replayMu.Lock()
	require.Same(t, current, client.replays[roomID], "the newer replay must own the room")
	client.replayMu.Unlock()
	require.Error(t, superseded.ctx.Err(), "the superseded replay must be cancelled")

	// The superseded refusal runs while the writer is blocked. It must not touch the
	// connection or the current owner.
	client.runRoomReplay(ctx, roomID, 0, "", superseded)
	require.NoError(t, ctx.Err(), "a superseded refusal must not close the connection")
	require.True(t, client.isInRoom(roomID))
	client.replayMu.Lock()
	require.Same(t, current, client.replays[roomID], "a superseded refusal must not evict the current owner")
	client.replayMu.Unlock()
	require.NoError(t, current.ctx.Err())

	// Revocation of the same membership waits behind the in-flight write.
	barrierStarted, releaseBarrier := waitRoomMembershipBarrierStart(t, h, userID, roomID)
	t.Cleanup(releaseBarrier)
	evictDone := make(chan error, 1)
	go func() {
		evictDone <- h.evictRoomMembership(context.Background(), userID, roomID)
	}()
	waitRoomMembershipSignal(t, barrierStarted, "revocation did not close room write admission")
	releaseBarrier()
	select {
	case err := <-evictDone:
		t.Fatalf("revocation finished before the in-flight write drained: %v", err)
	case <-time.After(50 * time.Millisecond):
	}
	client.replayMu.Lock()
	require.Same(t, current, client.replays[roomID], "the current owner must survive until the revocation completes")
	client.replayMu.Unlock()

	session.release()
	waitRoomMembershipSignal(t, refreshStarted, "authorization refresh did not start after the in-flight write drained")
	refreshResult <- false
	select {
	case err := <-evictDone:
		require.NoError(t, err)
	case <-time.After(2 * time.Second):
		t.Fatal("revocation did not finish after the write drained")
	}

	// The revocation removes the room and cancels its current owner. The connection
	// itself survives, and a late superseded refusal remains harmless.
	require.False(t, client.isInRoom(roomID))
	client.replayMu.Lock()
	_, stillOwned := client.replays[roomID]
	client.replayMu.Unlock()
	require.False(t, stillOwned, "revocation must release the replay owner for the room")
	require.Error(t, current.ctx.Err(), "revocation must cancel the current replay owner")
	require.NoError(t, ctx.Err(), "revocation must not close the connection")
	client.runRoomReplay(ctx, roomID, 0, "", superseded)
	require.NoError(t, ctx.Err())

	select {
	case <-writeDone:
	case <-time.After(2 * time.Second):
		t.Fatal("write pump did not consume the queued frames after revocation")
	}
	require.Equal(t, []string{"private_frame_written"}, order.snapshot(),
		"only the frame admitted before revocation may reach the socket")
}
