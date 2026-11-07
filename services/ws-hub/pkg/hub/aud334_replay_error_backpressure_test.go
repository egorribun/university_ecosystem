package hub

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"testing"
	"time"

	"github.com/gorilla/websocket"
	"github.com/stretchr/testify/require"
	"golang.org/x/time/rate"
)

type aud334CloseFailureSession struct {
	recordingSession
	frame       []byte
	reads       int
	retryRead   chan struct{}
	releaseRead chan struct{}
}

func (s *aud334CloseFailureSession) ReadMessage() (int, []byte, error) {
	s.reads++
	if s.reads == 1 {
		return 1, s.frame, nil
	}
	close(s.retryRead)
	<-s.releaseRead
	return 0, nil, io.EOF
}

func TestAUD334UnreportableReplayRejectionForcesReconnect(t *testing.T) {
	for _, testCase := range []struct {
		name        string
		unavailable bool
	}{
		{name: "rate limited"},
		{name: "replay unavailable", unavailable: true},
	} {
		t.Run(testCase.name, func(t *testing.T) {
			h := setupTestHub()
			enableSecureReplayForTest(h)
			h.chatReplayAvailable.Store(!testCase.unavailable)
			ctx, cancel := context.WithCancel(context.Background())
			t.Cleanup(cancel)
			session := &closeNotifyingSession{recordingSession: &recordingSession{}, closed: make(chan struct{})}
			client := &Client{
				ID: "replay-client", UserID: "replay-user", Hub: h,
				Rooms: map[string]bool{}, Send: make(chan []byte, 1), Conn: session, ctx: ctx, cancel: cancel,
				replayJoinLimiter: rate.NewLimiter(0, 0),
			}
			h.Clients[client.ID] = client
			client.Send <- []byte("pending frame")
			room := "replay-room"
			payload := resumeJoinPayload(t, h, client.UserID, room, 12)

			client.handleJoin(ctx, Message{Type: "join", Room: room, Payload: payload})

			require.Error(t, ctx.Err(), "an unreported rejected replay must close the socket so the cursor is retried")
			select {
			case <-session.closed:
			default:
				t.Fatal("unreported replay rejection did not close the transport")
			}
			require.False(t, client.isInRoom(room), "rejected replay must not become a live-only join")
		})
	}
}

func TestAUD334ReplayRejectionReleasesMembershipLockBeforeTransportClose(t *testing.T) {
	h := setupTestHub()
	enableSecureReplayForTest(h)
	ctx, cancel := context.WithCancel(context.Background())
	t.Cleanup(cancel)
	client := &Client{
		ID: "replay-client", UserID: "replay-user", Hub: h,
		SessionJTI: "replay-session", SessionExpiresAt: time.Now().Add(time.Hour),
		Rooms: map[string]bool{}, Send: make(chan []byte, 1), ctx: ctx, cancel: cancel,
		replayJoinLimiter: rate.NewLimiter(0, 0),
	}
	client.Send <- []byte("pending frame")
	room := "replay-room"
	msg := Message{Type: "join", Room: room, Payload: resumeJoinPayload(t, h, client.UserID, room, 12)}

	client.writeMu.Lock()
	locked := true
	done := make(chan error, 1)
	go func() { done <- client.authorizeAndHandleIncomingMessage(ctx, msg, nil) }()
	t.Cleanup(func() {
		if locked {
			client.writeMu.Unlock()
			<-done
		}
	})
	select {
	case <-ctx.Done():
	case <-time.After(2 * time.Second):
		t.Fatal("replay rejection did not begin transport cleanup")
	}
	lease := h.roomMembershipLock(client.UserID, room)
	available := lease.entry.mu.TryLock()
	if available {
		lease.entry.mu.Unlock()
	}
	lease.release()
	client.writeMu.Unlock()
	locked = false
	select {
	case err := <-done:
		require.NoError(t, err)
	case <-time.After(2 * time.Second):
		t.Fatal("replay rejection remained blocked after transport write was released")
	}
	require.True(t, available, "transport close must not wait while retaining the room membership lock")
}

func TestAUD334ReadPumpStopsAfterReplayRejectionEvenIfCloseFails(t *testing.T) {
	h := setupTestHub()
	enableSecureReplayForTest(h)
	h.chatReplayAvailable.Store(false)
	ctx, cancel := context.WithCancel(context.Background())
	t.Cleanup(cancel)
	room := "replay-room"
	payload := resumeJoinPayload(t, h, "replay-user", room, 12)
	frame, err := json.Marshal(Message{Type: "join", Room: room, Payload: payload})
	require.NoError(t, err)
	session := &aud334CloseFailureSession{
		recordingSession: recordingSession{closeErr: errors.New("synthetic close failure")},
		frame:            frame, retryRead: make(chan struct{}), releaseRead: make(chan struct{}),
	}
	client := &Client{
		ID: "replay-client", UserID: "replay-user", Hub: h, Conn: session,
		SessionJTI: "replay-session", SessionExpiresAt: time.Now().Add(time.Hour),
		Rooms: map[string]bool{}, Send: make(chan []byte, 1), ctx: ctx, cancel: cancel,
	}
	client.Send <- []byte("pending frame")
	h.handleRegister(ctx, client)
	done := make(chan struct{})
	go func() { client.ReadPump(ctx); close(done) }()
	select {
	case <-done:
	case <-session.retryRead:
		close(session.releaseRead)
		<-done
		t.Fatal("ReadPump retried a transport read after the replay rejection canceled its context")
	case <-time.After(2 * time.Second):
		close(session.releaseRead)
		<-done
		t.Fatal("ReadPump did not terminate after a failed transport close")
	}
	require.Error(t, ctx.Err())
	h.mu.RLock()
	_, registered := h.Clients[client.ID]
	h.mu.RUnlock()
	require.False(t, registered, "ReadPump cleanup must unregister after the rejected replay")
}

func TestAUD334RejectedReplayErrorReachesUnjoinedWebSocket(t *testing.T) {
	for _, testCase := range []struct {
		name        string
		unavailable bool
		code        string
	}{
		{name: "rate limited", code: "replay_join_rate_limited"},
		{name: "replay unavailable", unavailable: true, code: "replay_unavailable"},
	} {
		t.Run(testCase.name, func(t *testing.T) {
			h := setupTestHub()
			enableSecureReplayForTest(h)
			h.chatReplayAvailable.Store(!testCase.unavailable)
			server, browser := newConnPair(t)
			client := newClientOn(h, server, "replay-client", "replay-user")
			client.replayJoinLimiter = rate.NewLimiter(0, 0)
			h.handleRegister(client.ctx, client)
			readDone, writeDone := make(chan struct{}), make(chan struct{})
			go func() { client.ReadPump(client.ctx); close(readDone) }()
			go func() { client.WritePump(); close(writeDone) }()
			t.Cleanup(func() {
				client.cancelConnection()
				_ = browser.Close()
				_ = server.Close()
				<-readDone
				<-writeDone
			})
			room := "replay-room"
			payload := resumeJoinPayload(t, h, client.UserID, room, 12)
			frame, err := json.Marshal(Message{Type: "join", Room: room, Payload: payload})
			require.NoError(t, err)
			require.NoError(t, browser.WriteMessage(websocket.TextMessage, frame))
			require.NoError(t, browser.SetReadDeadline(time.Now().Add(time.Second)))
			_, data, err := browser.ReadMessage()
			require.NoError(t, err, "a rejected replay must tell the client to retry")
			var response map[string]any
			require.NoError(t, json.Unmarshal(data, &response))
			require.Equal(t, testCase.code, response["code"])
			require.Equal(t, room, response["room"])
			require.False(t, client.isInRoom(room), "the rejected replay must not join live-only")
		})
	}
}

func TestAUD334OtherRoomErrorsRemainMembershipScoped(t *testing.T) {
	h := setupTestHub()
	ctx, cancel := context.WithCancel(context.Background())
	t.Cleanup(cancel)
	session := &recordingSession{}
	client := &Client{
		ID: "scoped-client", UserID: "scoped-user", Hub: h, Conn: session,
		SessionJTI: "scoped-session", SessionExpiresAt: time.Now().Add(time.Hour),
		Rooms: map[string]bool{}, Send: make(chan []byte, 1), ctx: ctx, cancel: cancel,
	}
	for _, frame := range []string{
		`{"code":"replay_unavailable","detail":"chat history replay is temporarily unavailable","room":"room","type":"error","payload":{"text":"private"}}`,
		`{"code":"replay_unavailable","detail":"different detail","room":"room","type":"error"}`,
		`{"code":"different_code","detail":"chat history replay is temporarily unavailable","room":"room","type":"error"}`,
		`{"code":"replay_join_rate_limited","detail":"replay join rate limit exceeded","room":"room","type":"notification"}`,
	} {
		require.NoError(t, client.writeQueuedMessage([]byte(frame), true))
	}
	require.Empty(t, session.writes, "unrecognized or augmented room frames must still require membership")
}
