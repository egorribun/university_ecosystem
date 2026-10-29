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
