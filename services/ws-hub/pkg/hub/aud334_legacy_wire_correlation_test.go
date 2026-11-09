package hub

import (
	"context"
	"encoding/json"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"github.com/gorilla/websocket"
	"github.com/nats-io/nats.go"
	"github.com/stretchr/testify/require"
)

// A legacy generic limit response has no way to distinguish a rejected leave
// from a rejected resume join. The actual socket pumps and resume admission are
// used here; only the session authority and empty JetStream fetch are doubled.
func TestAUD334LegacyGenericLimitDoesNotIdentifyRejectedCommand(t *testing.T) {
	const room = "8ef3bb0c-a893-4f74-bdb4-01544a532626"
	const oldRoom = "9a8e2d87-1188-40fb-a1ef-d33f943d16f5"
	h := setupTestHub()
	enableSecureReplayForTest(h)
	h.clientMsgRateLimit = 0.000001 // No refill during the test.
	h.clientMsgRateBurst = 2
	h.js = &scriptedPullSubscription{pull: func(string, string, ...nats.SubOpt) (*nats.Subscription, error) {
		return &nats.Subscription{}, nil
	}}
	oldFetch, oldUnsubscribe := fetchPullMessagesFunc, unsubscribePullFunc
	t.Cleanup(func() {
		h.replayWG.Wait()
		fetchPullMessagesFunc, unsubscribePullFunc = oldFetch, oldUnsubscribe
	})
	replayDrained := make(chan struct{}, 1)
	fetchPullMessagesFunc = func(*nats.Subscription, int, ...nats.PullOpt) ([]*nats.Msg, error) {
		return nil, nats.ErrTimeout
	}
	unsubscribePullFunc = func(*nats.Subscription) error {
		select {
		case replayDrained <- struct{}{}:
		default:
		}
		return nil
	}

	server, browser := newConnPair(t)
	client := newClientOn(h, server, "aud334-wire", "replay-user")
	h.handleRegister(client.ctx, client)
	readDone, writeDone := make(chan struct{}), make(chan struct{})
	go func() { client.ReadPump(client.ctx); close(readDone) }()
	go func() { client.WritePump(); close(writeDone) }()
	t.Cleanup(func() {
		client.cancelConnection()
		_ = browser.Close()
		_ = server.Close()
		for _, done := range []<-chan struct{}{readDone, writeDone} {
			select {
			case <-done:
			case <-time.After(3 * time.Second):
				t.Error("test socket pump did not stop")
			}
		}
	})

	oldJoin, err := json.Marshal(Message{Type: "join", Room: oldRoom})
	require.NoError(t, err)
	require.NoError(t, browser.WriteMessage(websocket.TextMessage, oldJoin))
	join, err := json.Marshal(Message{
		Type: "join", Room: room, Payload: resumeJoinPayload(t, h, client.UserID, room, 12),
	})
	require.NoError(t, err)
	require.NoError(t, browser.WriteMessage(websocket.TextMessage, join))
	select {
	case <-replayDrained:
	case <-time.After(3 * time.Second):
		t.Fatal("the initial resume did not drain")
	}
	require.Eventually(t, func() bool {
		client.replayMu.Lock()
		_, replaying := client.replays[room]
		client.replayMu.Unlock()
		return client.isInRoom(room) && !replaying
	}, time.Second, time.Millisecond, "the initial resume must finish before testing unrelated rejection")
	require.True(t, client.isInRoom(oldRoom), "the earlier room was joined over the socket")

	leave, err := json.Marshal(Message{Type: "leave", Room: oldRoom})
	require.NoError(t, err)
	require.NoError(t, browser.WriteMessage(websocket.TextMessage, leave))
	require.NoError(t, browser.SetReadDeadline(time.Now().Add(3*time.Second)))
	_, leaveRejection, err := browser.ReadMessage()
	require.NoError(t, err)
	require.JSONEq(t, `{"type":"rate_limit_exceeded"}`, string(leaveRejection))
	require.True(t, client.isInRoom(room), "an unrelated leave must not change the resumed membership")
	require.True(t, client.isInRoom(oldRoom), "the rate-limited leave was never dispatched")

	require.NoError(t, browser.WriteMessage(websocket.TextMessage, join))
	_, joinRejection, err := browser.ReadMessage()
	require.NoError(t, err)
	require.Equal(t, leaveRejection, joinRejection,
		"legacy rejections for a leave and resume join are indistinguishable on the wire")
	require.True(t, client.isInRoom(room), "a frame rejected before dispatch must leave membership intact")
}

type aud334DelayedRoomAuth struct {
	calls   atomic.Int32
	waiting chan struct{}
	release chan struct{}
}

func (auth *aud334DelayedRoomAuth) CanJoinRoom(ctx context.Context, _, _ string) bool {
	if auth.calls.Add(1) != 2 {
		return true
	}
	close(auth.waiting)
	select {
	case <-auth.release:
		return true
	case <-ctx.Done():
		return false
	}
}

func (*aud334DelayedRoomAuth) Invalidate(string, string) {}

// A live room event can advance the signed checkpoint while an older invalid
// resume join is still waiting for authorization. The later error names only
// the room, so it cannot identify which checkpoint was rejected.
func TestAUD334LegacyInvalidResumeErrorCanFollowNewerCheckpoint(t *testing.T) {
	const room = "8ef3bb0c-a893-4f74-bdb4-01544a532626"
	h := setupTestHub()
	enableSecureReplayForTest(h)
	auth := &aud334DelayedRoomAuth{waiting: make(chan struct{}), release: make(chan struct{})}
	h.authClient = auth
	var releaseOnce sync.Once
	release := func() { releaseOnce.Do(func() { close(auth.release) }) }

	server, browser := newConnPair(t)
	client := newClientOn(h, server, "aud334-delayed-error", "replay-user")
	h.handleRegister(client.ctx, client)
	readDone, writeDone := make(chan struct{}), make(chan struct{})
	go func() { client.ReadPump(client.ctx); close(readDone) }()
	go func() { client.WritePump(); close(writeDone) }()
	t.Cleanup(func() {
		release()
		client.cancelConnection()
		_ = browser.Close()
		_ = server.Close()
		for _, done := range []<-chan struct{}{readDone, writeDone} {
			select {
			case <-done:
			case <-time.After(3 * time.Second):
				t.Error("test socket pump did not stop")
			}
		}
	})

	join, err := json.Marshal(Message{Type: "join", Room: room})
	require.NoError(t, err)
	require.NoError(t, browser.WriteMessage(websocket.TextMessage, join))
	require.Eventually(t, func() bool { return client.isInRoom(room) }, time.Second, time.Millisecond)
	invalidJoin, err := json.Marshal(map[string]string{
		"type": "join", "room": room, "resume_token": "invalid-old-cursor",
	})
	require.NoError(t, err)
	require.NoError(t, browser.WriteMessage(websocket.TextMessage, invalidJoin))
	select {
	case <-auth.waiting:
	case <-time.After(3 * time.Second):
		t.Fatal("invalid resume did not reach the delayed room authorization")
	}

	h.broadcastMessage(client.ctx, &Message{
		Type: "new_message", Room: room,
		Payload: json.RawMessage(`{"type":"new_message","chat_id":"8ef3bb0c-a893-4f74-bdb4-01544a532626",` +
			`"message":{"id":"c55bed91-a163-4b4b-b08a-92f62af2459e",` +
			`"chat_id":"8ef3bb0c-a893-4f74-bdb4-01544a532626",` +
			`"sender_id":"cd9e5849-6db6-4262-b4f0-f93159139a9a",` +
			`"content":"newer","created_at":"2026-10-30T00:00:00Z","read_status":false}}`),
		MessageReplayMetadata: &MessageReplayMetadata{Seq: 13, Stream: h.streamChat},
	})
	require.NoError(t, browser.SetReadDeadline(time.Now().Add(3*time.Second)))
	_, newerFrame, err := browser.ReadMessage()
	require.NoError(t, err)
	var newer struct {
		Type        string `json:"type"`
		Seq         uint64 `json:"seq"`
		ResumeToken string `json:"resume_token"`
	}
	require.NoError(t, json.Unmarshal(newerFrame, &newer))
	require.Equal(t, "new_message", newer.Type)
	require.EqualValues(t, 13, newer.Seq)
	verifiedSeq, err := h.verifyResumeToken(newer.ResumeToken, client.UserID, room)
	require.NoError(t, err)
	require.EqualValues(t, 13, verifiedSeq)

	release()
	_, oldError, err := browser.ReadMessage()
	require.NoError(t, err)
	var rejection map[string]any
	require.NoError(t, json.Unmarshal(oldError, &rejection))
	require.Equal(t, "error", rejection["type"])
	require.Equal(t, "invalid_resume_token", rejection["code"])
	require.Equal(t, room, rejection["room"])
}
