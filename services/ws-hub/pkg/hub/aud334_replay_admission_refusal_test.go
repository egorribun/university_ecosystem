package hub

import (
	"context"
	"encoding/binary"
	"encoding/json"
	"sync"
	"testing"
	"time"

	"github.com/gorilla/websocket"
	"github.com/stretchr/testify/require"
	"golang.org/x/time/rate"
)

const aud334AdmissionRoom = "8ef3bb0c-a893-4f74-bdb4-01544a532626"

func newAUD334AdmissionClient(h *Hub, session *recordingSession, ctx context.Context, cancel context.CancelFunc) *Client {
	return &Client{
		ID: "replay-admission-client", UserID: "replay-admission-user", Hub: h, Conn: session,
		SessionJTI: "replay-admission-session", SessionExpiresAt: time.Now().Add(time.Hour),
		Rooms: make(map[string]bool), Send: make(chan []byte, 8), ctx: ctx, cancel: cancel,
		replayJoinLimiter: rate.NewLimiter(rate.Every(time.Second), 2),
	}
}

// aud334CloseCodes returns the close status codes written to the session, in order.
func aud334CloseCodes(t *testing.T, session *recordingSession) []uint16 {
	t.Helper()
	var codes []uint16
	for _, write := range session.writes {
		if write.messageType == websocket.CloseMessage && len(write.data) >= 2 {
			codes = append(codes, binary.BigEndian.Uint16(write.data[:2]))
		}
	}
	return codes
}

// AUD-334: a replay admitted by the membership commit but refused because the
// hub is stopping must not vanish silently. The membership already delivers live
// room frames, so a silent skip would let a later frame advance the client's
// cursor past the replay it never received. The connection closes with the
// existing shutdown retry contract, and the client resumes from its signed cursor.
func TestAUD334RefusedReplayAdmissionClosesForRetry(t *testing.T) {
	h := setupTestHub()
	enableSecureReplayForTest(h)
	ctx, cancel := context.WithCancel(context.Background())
	t.Cleanup(cancel)
	session := &recordingSession{}
	client := newAUD334AdmissionClient(h, session, ctx, cancel)
	t.Cleanup(func() { safeClose(client.Send) })
	h.stopped.Store(true)

	client.handleJoin(ctx, Message{
		Type: "join", Room: aud334AdmissionRoom,
		Payload: resumeJoinPayload(t, h, client.UserID, aud334AdmissionRoom, 12),
	})

	require.Error(t, ctx.Err(), "a refused replay admission must end the connection")
	require.Equal(t, []uint16{websocket.CloseTryAgainLater}, aud334CloseCodes(t, session),
		"the client must receive the explicit try-again-later close")
	require.Zero(t, len(client.Send), "no room frame may follow a refused replay")
}

// A superseded state already has a successor that owns the room. Its refused
// admission must not tear down the connection, because the successor reports
// its own outcome.
func TestAUD334SupersededReplayAdmissionDefersToSuccessor(t *testing.T) {
	h := setupTestHub()
	enableSecureReplayForTest(h)
	ctx, cancel := context.WithCancel(context.Background())
	t.Cleanup(cancel)
	session := &recordingSession{}
	client := newAUD334AdmissionClient(h, session, ctx, cancel)
	t.Cleanup(func() { safeClose(client.Send) })

	_, superseded := client.prepareRoomReplay(ctx, aud334AdmissionRoom)
	// Replace the map entry without cancelling the old state, so the refusal
	// reaches removeRoomReplay with a state that is no longer current.
	client.replayMu.Lock()
	client.replays[aud334AdmissionRoom] = &roomReplayState{
		ctx: ctx, cancel: func() {}, buffered: make(map[uint64][]byte),
	}
	client.replayMu.Unlock()
	h.stopped.Store(true)

	client.runRoomReplay(ctx, aud334AdmissionRoom, 12, "", superseded)

	require.NoError(t, ctx.Err(), "the successor, not the superseded admission, owns the connection")
	require.Empty(t, aud334CloseCodes(t, session))
}

// Cancellation and admission refusal race on the same replay state. Whichever
// side wins, the connection closes exactly when the refusal still owned the room.
func TestAUD334RefusedReplayAdmissionRacesCancellationWithoutDoubleOwnership(t *testing.T) {
	h := setupTestHub()
	enableSecureReplayForTest(h)
	h.stopped.Store(true)
	for range 32 {
		ctx, cancel := context.WithCancel(context.Background())
		session := &recordingSession{}
		client := newAUD334AdmissionClient(h, session, ctx, cancel)
		_, state := client.prepareRoomReplay(ctx, aud334AdmissionRoom)

		start := make(chan struct{})
		var wg sync.WaitGroup
		wg.Add(2)
		go func() {
			defer wg.Done()
			<-start
			client.runRoomReplay(ctx, aud334AdmissionRoom, 12, "", state)
		}()
		go func() {
			defer wg.Done()
			<-start
			client.cancelRoomReplay(aud334AdmissionRoom)
		}()
		close(start)
		wg.Wait()

		closed := len(aud334CloseCodes(t, session)) == 1
		require.Equal(t, closed, ctx.Err() != nil, "close and cancellation must agree")
		require.LessOrEqual(t, len(aud334CloseCodes(t, session)), 1)
		cancel()
		safeClose(client.Send)
	}
}

// With replay unavailable, a join whose resume token fails verification is
// rejected before membership is committed, with the invalid-token contract.
func TestAUD334ReplayUnavailableRejectsInvalidTokenBeforeCommit(t *testing.T) {
	h := setupTestHub()
	enableSecureReplayForTest(h)
	h.chatReplayAvailable.Store(false)
	ctx, cancel := context.WithCancel(context.Background())
	t.Cleanup(cancel)
	session := &recordingSession{}
	client := newAUD334AdmissionClient(h, session, ctx, cancel)
	t.Cleanup(func() { safeClose(client.Send) })

	client.handleJoin(ctx, Message{
		Type: "join", Room: aud334AdmissionRoom,
		Payload: json.RawMessage(`{"resume_token":"not-a-signed-token"}`),
	})

	require.NoError(t, ctx.Err())
	require.Len(t, client.Send, 1)
	frame := <-client.Send
	require.Contains(t, string(frame), `"code":"invalid_resume_token"`)
	require.Contains(t, string(frame), `"room":"`+aud334AdmissionRoom+`"`)
}
