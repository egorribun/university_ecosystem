package hub

import (
	"context"
	"encoding/json"
	"testing"
	"time"

	"github.com/stretchr/testify/require"
	"golang.org/x/time/rate"
)

func TestAUD334RejectedResumeDoesNotDeliverLaterLiveFramesFromExistingMembership(t *testing.T) {
	for _, tc := range []struct {
		name        string
		unavailable bool
		code        string
	}{
		{name: "rate limited", code: "replay_join_rate_limited"},
		{name: "unavailable", unavailable: true, code: "replay_unavailable"},
	} {
		for _, previousReplay := range []bool{false, true} {
			name := tc.name + "/queued live frame"
			if previousReplay {
				name = tc.name + "/buffered by an earlier replay"
			}
			t.Run(name, func(t *testing.T) {
				h := setupTestHub()
				enableSecureReplayForTest(h)
				ctx, cancel := context.WithCancel(context.Background())
				t.Cleanup(cancel)
				session := &recordingSession{}
				client := &Client{
					ID: "existing-room-client", UserID: "existing-room-user", Hub: h, Conn: session,
					SessionJTI: "existing-room-session", SessionExpiresAt: time.Now().Add(time.Hour),
					Rooms: make(map[string]bool), Send: make(chan []byte, 8), ctx: ctx, cancel: cancel,
					replayJoinLimiter: rate.NewLimiter(0, 0),
				}
				t.Cleanup(func() { safeClose(client.Send) })
				const room = "8ef3bb0c-a893-4f74-bdb4-01544a532626"
				var previous *roomReplayState
				if previousReplay {
					_, previous = client.prepareRoomReplay(ctx, room)
				} else {
					client.JoinRoom(room)
				}

				// A checkpoint at 12 can be missing 13. A later frame already
				// queued for this room must not advance the rejected cursor.
				broadcast := func(sequence uint64) {
					h.broadcastMessage(ctx, &Message{
						Type: "new_message", Room: room,
						Payload: json.RawMessage(`{"type":"new_message","chat_id":"8ef3bb0c-a893-4f74-bdb4-01544a532626",` +
							`"message":{"id":"c55bed91-a163-4b4b-b08a-92f62af2459e",` +
							`"chat_id":"8ef3bb0c-a893-4f74-bdb4-01544a532626",` +
							`"sender_id":"cd9e5849-6db6-4262-b4f0-f93159139a9a",` +
							`"content":"later message","created_at":"2026-10-30T00:00:00Z","read_status":false}}`),
						MessageReplayMetadata: &MessageReplayMetadata{Seq: sequence, Stream: h.streamChat},
					})
				}
				if previousReplay {
					// The previous replay is independently completing from cursor 14.
					broadcast(15)
				} else {
					broadcast(14)
				}
				if !previousReplay {
					require.Len(t, client.Send, 1, "positive control: the old membership receives live traffic")
				}

				h.chatReplayAvailable.Store(!tc.unavailable)
				client.handleJoin(ctx, Message{
					Type: "join", Room: room,
					Payload: resumeJoinPayload(t, h, client.UserID, room, 12),
				})
				if previous != nil {
					// The earlier replay may have started from a different cursor.
					// Finishing it cannot justify advancing this rejected cursor.
					client.flushRoomReplay(room, previous, 14)
				}
				broadcast(16)

				for range len(client.Send) {
					frame := <-client.Send
					if err := client.writeQueuedMessage(frame, true); err != nil {
						require.ErrorIs(t, err, errSessionInactive)
						require.Error(t, ctx.Err())
						break
					}
				}
				notified := false
				for _, write := range session.writes {
					var frame map[string]any
					require.NoError(t, json.Unmarshal(write.data, &frame))
					if frame["code"] == tc.code && frame["room"] == room {
						notified = true
					}
					require.NotContains(t, frame, "seq", "a rejected resume must not deliver a later cursor")
				}
				require.True(t, notified || ctx.Err() != nil, "the client must be told to retry or disconnected")
			})
		}
	}
}

func TestAUD334RejectedResumeStopsWriterAlreadyPastSessionCheck(t *testing.T) {
	h := setupTestHub()
	enableSecureReplayForTest(h)
	ctx, cancel := context.WithCancel(context.Background())
	t.Cleanup(cancel)
	session := &recordingSession{}
	client := &Client{
		ID: "existing-room-client", UserID: "existing-room-user", Hub: h, Conn: session,
		SessionJTI: "existing-room-session", SessionExpiresAt: time.Now().Add(time.Hour),
		Rooms: make(map[string]bool), Send: make(chan []byte, 1), ctx: ctx, cancel: cancel,
		replayJoinLimiter: rate.NewLimiter(0, 0),
	}
	t.Cleanup(func() { safeClose(client.Send) })
	const room = "8ef3bb0c-a893-4f74-bdb4-01544a532626"
	client.JoinRoom(room)
	h.broadcastMessage(ctx, &Message{
		Type: "new_message", Room: room, Payload: json.RawMessage(`{"content":"later message"}`),
		MessageReplayMetadata: &MessageReplayMetadata{Seq: 14, Stream: h.streamChat},
	})
	require.Len(t, client.Send, 1, "positive control: existing membership receives the later frame")
	frame := <-client.Send
	var queued struct {
		Seq         uint64 `json:"seq"`
		ResumeToken string `json:"resume_token"`
	}
	require.NoError(t, json.Unmarshal(frame, &queued))
	require.Equal(t, uint64(14), queued.Seq)
	sequence, err := h.verifyResumeToken(queued.ResumeToken, client.UserID, room)
	require.NoError(t, err)
	require.Equal(t, uint64(14), sequence)
	join := Message{
		Type: "join", Room: room,
		Payload: resumeJoinPayload(t, h, client.UserID, room, 12),
	}

	checked := make(chan struct{}, 1)
	h.sessionRevocationCheck = func(context.Context, string) error {
		select {
		case checked <- struct{}{}:
		default:
		}
		return nil
	}
	lease := h.roomMembershipLock(client.UserID, room)
	lease.Lock()
	locked := true
	var writerDone, closeDone chan struct{}
	t.Cleanup(func() {
		cancel()
		if locked {
			lease.Unlock()
		}
		// Release admission before joining either goroutine, including failed
		// fixture assertions. Neither cleanup wait can hang the whole suite.
		for _, done := range []chan struct{}{writerDone, closeDone} {
			if done == nil {
				continue
			}
			select {
			case <-done:
			case <-time.After(2 * time.Second):
				t.Error("replay rejection goroutine did not finish during cleanup")
			}
		}
	})
	writerDone = make(chan struct{})
	var writeErr error
	go func() {
		writeErr = client.writeQueuedMessage(frame, true)
		close(writerDone)
	}()
	select {
	case <-checked:
	case <-time.After(2 * time.Second):
		t.Fatal("writer did not reach the real session authorization boundary")
	}
	// The second reference belongs to the writer: it has completed session
	// authorization and is waiting on this actual room admission mutex.
	require.Eventually(t, func() bool {
		lease.registry.mu.Lock()
		references := lease.entry.references
		lease.registry.mu.Unlock()
		return references == 2
	}, 2*time.Second, time.Millisecond)
	client.sessionCheckMu.Lock()
	authorized := !client.sessionCheckedUntil.IsZero()
	client.sessionCheckMu.Unlock()
	require.True(t, authorized, "writer must pass session authorization before cancellation")
	require.Zero(t, lease.entry.writesInFlight, "writer has not acquired a room permit")

	// handleJoin runs this exact decision callback under the same keyed lock.
	// Reject cursor 12 before admitting the already-queued cursor 14.
	decision := &roomJoinDecision{}
	require.False(t, client.prepareAuthorizedRoomJoin(ctx, join, decision))
	require.NoError(t, decision.tokenErr)
	require.True(t, decision.replayLimited)
	require.True(t, decision.reconnectOnReject)
	require.ErrorIs(t, ctx.Err(), context.Canceled)
	require.True(t, client.isInRoom(room), "ReadPump owns later membership removal")
	lease.Unlock()
	locked = false

	closeDone = make(chan struct{})
	go func() {
		client.finishAuthorizedRoomJoin(ctx, join, decision)
		close(closeDone)
	}()
	select {
	case <-writerDone:
	case <-time.After(2 * time.Second):
		t.Fatal("writer did not finish after room admission was released")
	}
	select {
	case <-closeDone:
	case <-time.After(2 * time.Second):
		t.Fatal("replay rejection did not finish after the writer released its mutex")
	}
	// Inspect only after both goroutines finish; never print signed frame data.
	require.Zero(t, len(session.writes), "a rejected resume must not deliver the later signed cursor")
	require.ErrorIs(t, writeErr, errSessionInactive)
}
