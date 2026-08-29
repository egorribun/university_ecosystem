package hub

// Coverage tests (testing session 10) for pkg/hub/client.go — the Client
// pump/room/message machinery that prior sessions exercised only through the
// single happy-path HandleWebSocket E2E. These drive ReadPump / WritePump /
// handleMessage / JoinRoom / LeaveRoom / safeSend directly via real gorilla
// connection pairs and direct calls.
//
// CAUTION (session-9 gotcha, still binding): NEVER send a {"type":"message"}
// frame THROUGH ReadPump in these tests — handleMessage publishes to a nil
// *nats.Conn and the panic inside the ReadPump goroutine would kill the test
// binary. The oversized / rate-limit branches of handleMessage are reached via
// DIRECT calls below (they return before any NATS access). join/leave are
// NATS-free and safe over the socket.
//
// Metric-asserting tests read package-global counters via prometheus/testutil
// before+after within one test and are NOT marked t.Parallel().

import (
	"context"
	"errors"
	"io"
	"net"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/gorilla/websocket"
	"github.com/prometheus/client_golang/prometheus/testutil"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"github.com/university-ecosystem/ws-hub/pkg/config"
)

// newConnPair returns a connected (server, client) gorilla websocket pair via a
// throwaway httptest server. net.Pipe does NOT work — *websocket.Conn requires a
// real handshake. Both ends are closed on cleanup.
func newConnPair(t *testing.T) (server, client *websocket.Conn) {
	t.Helper()
	upgrader := websocket.Upgrader{
		CheckOrigin: func(*http.Request) bool { return true },
	}
	srvCh := make(chan *websocket.Conn, 1)
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		c, err := upgrader.Upgrade(w, r, nil)
		if err != nil {
			return
		}
		srvCh <- c
	}))
	t.Cleanup(srv.Close)

	wsURL := "ws" + strings.TrimPrefix(srv.URL, "http")
	client, resp, err := websocket.DefaultDialer.Dial(wsURL, nil)
	require.NoError(t, err)
	if resp != nil && resp.Body != nil {
		_ = resp.Body.Close() //nolint:errcheck // handshake response cleanup
	}
	select {
	case server = <-srvCh:
	case <-time.After(2 * time.Second):
		t.Fatal("server side of websocket pair never arrived")
	}
	t.Cleanup(func() {
		_ = client.Close() //nolint:errcheck // test cleanup
		_ = server.Close() //nolint:errcheck // test cleanup
	})
	return server, client
}

// newClientOn wires a *Client around the server side of a pair, with a private
// context so teardown branches are reachable without running the whole hub.
func newClientOn(h *Hub, serverConn *websocket.Conn, id, userID string) *Client {
	ctx, cancel := context.WithCancel(context.Background())
	return &Client{
		ID:         id,
		UserID:     userID,
		SessionJTI: "test-" + id,
		Conn:       NewWebSocketSession(serverConn),
		Rooms:      make(map[string]bool),
		Send:       make(chan []byte, 8),
		Hub:        h,
		ctx:        ctx,
		cancel:     cancel,
	}
}

// ---------------------------------------------------------------------------
// safeSend
// ---------------------------------------------------------------------------

func TestSafeSend(t *testing.T) {
	ok := make(chan []byte, 1)
	assert.True(t, safeSend(ok, []byte("x")), "buffered channel accepts")

	full := make(chan []byte) // unbuffered, no reader → default branch
	assert.False(t, safeSend(full, []byte("x")), "full channel returns false")

	closed := make(chan []byte, 1)
	close(closed)
	assert.False(t, safeSend(closed, []byte("x")), "send on closed channel recovers to false")
}

func TestSafeClose_MapCleanup(t *testing.T) {
	ch := make(chan []byte, 4)
	assert.True(t, safeSend(ch, []byte("payload")))

	chMu.Lock()
	_, inMap := chMutexes[ch]
	chMu.Unlock()
	assert.True(t, inMap, "channel should be registered in chMutexes after safeSend")

	safeClose(ch)

	chMu.Lock()
	_, inMapAfterClose := chMutexes[ch]
	chMu.Unlock()
	assert.False(t, inMapAfterClose, "channel should be removed from chMutexes after safeClose")

	// safeSend on already closed channel should return false and not leak map entry
	assert.False(t, safeSend(ch, []byte("late payload")))

	chMu.Lock()
	_, inMapLate := chMutexes[ch]
	chMu.Unlock()
	assert.False(t, inMapLate, "safeSend on closed channel should not leave entry in chMutexes")
}

func TestIsNormalCloseError(t *testing.T) {
	assert.True(t, isNormalCloseError(nil))
	assert.True(t, isNormalCloseError(io.EOF))
	assert.True(t, isNormalCloseError(net.ErrClosed))
	assert.True(t, isNormalCloseError(&websocket.CloseError{Code: websocket.CloseNormalClosure}))
	assert.True(t, isNormalCloseError(&websocket.CloseError{Code: websocket.CloseGoingAway}))
	assert.True(t, isNormalCloseError(errors.New("QUIC normal closure")))
	assert.False(t, isNormalCloseError(errors.New("unexpected database connection drop")))
}

// ---------------------------------------------------------------------------
// JoinRoom / LeaveRoom (direct)
// ---------------------------------------------------------------------------

func TestJoinLeaveRoom_Direct(t *testing.T) {
	h := setupTestHub()
	go h.Run(context.Background()) // hub ctx for logger; not strictly required here
	srv, _ := newConnPair(t)
	c := newClientOn(h, srv, "c-join", "u-join")

	c.JoinRoom("") // empty no-op
	h.mu.RLock()
	assert.Empty(t, h.Rooms, "empty room name is a no-op")
	h.mu.RUnlock()

	c.JoinRoom("room-a")
	h.mu.RLock()
	assert.Len(t, h.Rooms["room-a"], 1)
	h.mu.RUnlock()
	c.mu.Lock()
	assert.True(t, c.Rooms["room-a"])
	c.mu.Unlock()

	c.LeaveRoom("") // empty no-op
	c.LeaveRoom("never-joined")
	c.LeaveRoom("room-a")
	h.mu.RLock()
	_, stillThere := h.Rooms["room-a"]
	h.mu.RUnlock()
	assert.False(t, stillThere, "leaving the last client deletes the room key")
}

// ---------------------------------------------------------------------------
// handleMessage (direct — guard paths only, NATS-free)
// ---------------------------------------------------------------------------

func TestHandleMessage_Oversized(t *testing.T) {
	h := setupTestHub()
	srv, _ := newConnPair(t)
	c := newClientOn(h, srv, "c-big", "u-big")

	before := testutil.ToFloat64(IncomingDropsTotal)
	big := make([]byte, 61*1024) // > 60 KB ingress limit
	c.handleMessage(Message{Type: "message", Room: "r"}, big)
	assert.Equal(t, before+1, testutil.ToFloat64(IncomingDropsTotal))

	select {
	case notice := <-c.Send:
		assert.Contains(t, string(notice), "message_too_large")
	default:
		t.Fatal("expected a message_too_large notice on Send")
	}
}

func TestHandleMessage_OversizedDropsWhenSendFull(t *testing.T) {
	h := setupTestHub()
	srv, _ := newConnPair(t)
	c := newClientOn(h, srv, "c-bigfull", "u-bigfull")
	// Saturate the Send buffer so the notice hits the default (drop) arm.
	for i := 0; i < cap(c.Send); i++ {
		c.Send <- []byte("filler")
	}
	before := testutil.ToFloat64(IncomingDropsTotal)
	c.handleMessage(Message{Type: "message"}, make([]byte, 61*1024))
	assert.Equal(t, before+1, testutil.ToFloat64(IncomingDropsTotal),
		"drop is still counted even when the client notice can't be enqueued")
}

func TestHandleMessage_RateLimited(t *testing.T) {
	h := setupTestHub()
	h.clientMsgRateLimit = 0 // deny everything
	h.clientMsgRateBurst = 0
	srv, _ := newConnPair(t)
	c := newClientOn(h, srv, "c-rl", "u-rl")
	c.JoinRoom("r")

	c.handleMessage(Message{Type: "message", Room: "r"}, []byte(`{"type":"message"}`))
	select {
	case notice := <-c.Send:
		assert.Contains(t, string(notice), "rate_limit_exceeded")
	default:
		t.Fatal("expected a rate_limit_exceeded notice on Send")
	}
}

func TestHandleMessage_RateLimitedDropsWhenSendFull(t *testing.T) {
	h := setupTestHub()
	h.clientMsgRateLimit = 0
	h.clientMsgRateBurst = 0
	srv, _ := newConnPair(t)
	c := newClientOn(h, srv, "c-rlfull", "u-rlfull")
	c.JoinRoom("r")
	for i := 0; i < cap(c.Send); i++ {
		c.Send <- []byte("filler")
	}
	// Must not panic / block — the notice is silently dropped on a full buffer.
	c.handleMessage(Message{Type: "message", Room: "r"}, []byte(`{"type":"message"}`))
}

// ---------------------------------------------------------------------------
// handleIncomingMessage dispatch (direct)
// ---------------------------------------------------------------------------

func TestHandleIncomingMessage_JoinLeaveDispatch(t *testing.T) {
	h := setupTestHub() // mockAuthClient allowed=true
	srv, _ := newConnPair(t)
	c := newClientOn(h, srv, "c-disp", "u-disp")

	c.handleIncomingMessage(c.ctx, Message{Type: "join", Room: "room-d"}, nil)
	h.mu.RLock()
	assert.Len(t, h.Rooms["room-d"], 1)
	h.mu.RUnlock()

	c.handleIncomingMessage(c.ctx, Message{Type: "leave", Room: "room-d"}, nil)
	h.mu.RLock()
	_, ok := h.Rooms["room-d"]
	h.mu.RUnlock()
	assert.False(t, ok)
}

func TestMergeTopLevelJoinReplayIntoPayload(t *testing.T) {
	msg := &Message{Type: "join", Payload: []byte(`{"last_msg_id":"payload-id"}`)}

	mergeTopLevelJoinReplay(msg, []byte(`{"type":"join","last_seq":42,"last_msg_id":"top-id"}`))

	assert.JSONEq(t, `{"last_seq":42,"last_msg_id":"payload-id"}`, string(msg.Payload))
}

func TestHandleIncomingMessage_UnknownTypeIncrementsMetric(t *testing.T) {
	h := setupTestHub()
	srv, _ := newConnPair(t)
	c := newClientOn(h, srv, "c-unk", "u-unk")

	before := testutil.ToFloat64(UnknownMsgTypeTotal)
	c.handleIncomingMessage(c.ctx, Message{Type: "totally-bogus"}, nil)
	assert.Equal(t, before+1, testutil.ToFloat64(UnknownMsgTypeTotal))
}

func TestHandleJoin_EmptyRoomNoOp(t *testing.T) {
	h := setupTestHub()
	srv, _ := newConnPair(t)
	c := newClientOn(h, srv, "c-empty", "u-empty")
	c.handleJoin(c.ctx, Message{Type: "join", Room: ""})
	h.mu.RLock()
	assert.Empty(t, h.Rooms)
	h.mu.RUnlock()
}

func TestHandleJoin_DeniedIncrementsAuthFailures(t *testing.T) {
	logger := setupTestHub().Logger
	cfg := &config.Config{MaxClients: 10, BroadcastBufferSize: 10, BroadcastWorkers: 1}
	h := trackTestHub(NewHub(nil, logger, &mockAuthClient{allowed: false}, cfg, nil))
	srv, _ := newConnPair(t)
	c := newClientOn(h, srv, "c-deny", "u-deny")

	before := testutil.ToFloat64(AuthFailuresTotal.WithLabelValues("room_join_denied"))
	c.handleJoin(c.ctx, Message{Type: "join", Room: "secret"})
	assert.Equal(t, before+1,
		testutil.ToFloat64(AuthFailuresTotal.WithLabelValues("room_join_denied")))
	h.mu.RLock()
	_, ok := h.Rooms["secret"]
	h.mu.RUnlock()
	assert.False(t, ok, "denied join must not create the room")
}

// ---------------------------------------------------------------------------
// ReadPump (driven from the client side; NATS-free frames only)
// ---------------------------------------------------------------------------

func TestReadPump_InvalidJSONThenJoin(t *testing.T) {
	h := setupTestHub()
	go h.Run(context.Background())
	srv, cli := newConnPair(t)
	c := newClientOn(h, srv, "c-read", "u-read")
	// Register so the ReadPump teardown's Unregister send has a receiver.
	h.Register <- c
	require.Eventually(t, func() bool {
		h.mu.RLock()
		defer h.mu.RUnlock()
		_, ok := h.Clients["c-read"]
		return ok
	}, 2*time.Second, 10*time.Millisecond)

	go c.ReadPump(c.ctx)

	require.NoError(t, cli.WriteMessage(websocket.TextMessage, []byte("{not valid json")))
	require.NoError(t, cli.WriteJSON(map[string]string{"type": "join", "room": "room-r"}))
	require.Eventually(t, func() bool {
		h.mu.RLock()
		defer h.mu.RUnlock()
		return len(h.Rooms["room-r"]) == 1
	}, 2*time.Second, 10*time.Millisecond)

	// Closing the client side drives ReadPump teardown → Unregister + limiter delete.
	require.NoError(t, cli.Close())
	require.Eventually(t, func() bool {
		h.mu.RLock()
		defer h.mu.RUnlock()
		_, ok := h.Clients["c-read"]
		return !ok
	}, 2*time.Second, 10*time.Millisecond)
}

func TestReadPump_DisallowedTypeOverSocket(t *testing.T) {
	h := setupTestHub()
	go h.Run(context.Background())
	srv, cli := newConnPair(t)
	c := newClientOn(h, srv, "c-bad", "u-bad")
	h.Register <- c
	go c.ReadPump(c.ctx)

	before := testutil.ToFloat64(UnknownMsgTypeTotal)
	// "ping" is not in allowedMessageTypes → rejected at the parse boundary.
	require.NoError(t, cli.WriteJSON(map[string]string{"type": "ping"}))
	require.Eventually(t, func() bool {
		return testutil.ToFloat64(UnknownMsgTypeTotal) >= before+1
	}, 2*time.Second, 10*time.Millisecond)
	require.NoError(t, cli.Close())
}

func TestReadPump_HubCtxDoneTeardown(t *testing.T) {
	// When the hub ctx is already cancelled, the teardown select takes the
	// ctx.Done() arm and closes Send via closeOnce instead of Unregister.
	logger := setupTestHub().Logger
	cfg := &config.Config{MaxClients: 10, BroadcastBufferSize: 10, BroadcastWorkers: 1,
		ClientMsgRateLimit: 10, ClientMsgRateBurst: 10}
	h := trackTestHub(NewHub(nil, logger, &mockAuthClient{allowed: true}, cfg, nil))
	hubCtx, hubCancel := context.WithCancel(context.Background())
	h.ctx = hubCtx
	hubCancel() // hub ctx done before ReadPump teardown runs

	srv, cli := newConnPair(t)
	c := newClientOn(h, srv, "c-ctx", "u-ctx")

	done := make(chan struct{})
	go func() { c.ReadPump(c.ctx); close(done) }()
	require.NoError(t, cli.Close()) // ends the read loop → teardown
	select {
	case <-done:
	case <-time.After(2 * time.Second):
		t.Fatal("ReadPump did not exit on closed conn with hub ctx done")
	}
	// Send was closed via closeOnce on the ctx.Done() teardown arm.
	_, open := <-c.Send
	assert.False(t, open, "Send channel should be closed by the ctx.Done teardown arm")
}

// ---------------------------------------------------------------------------
// WritePump
// ---------------------------------------------------------------------------

func TestWritePump_DeliversThenCloses(t *testing.T) {
	h := setupTestHub()
	srv, cli := newConnPair(t)
	c := newClientOn(h, srv, "c-write", "u-write")

	var wg sync.WaitGroup
	wg.Add(1)
	go func() { defer wg.Done(); c.WritePump() }()

	c.Send <- []byte(`{"type":"hello"}`)
	require.NoError(t, cli.SetReadDeadline(time.Now().Add(2*time.Second)))
	mt, data, err := cli.ReadMessage()
	require.NoError(t, err)
	assert.Equal(t, websocket.TextMessage, mt)
	assert.JSONEq(t, `{"type":"hello"}`, string(data))

	// Closing Send makes WritePump emit a CloseMessage and return.
	safeClose(c.Send)
	wg.Wait()
}

func TestWritePump_ExitsOnCtxCancel(t *testing.T) {
	h := setupTestHub()
	srv, _ := newConnPair(t)
	c := newClientOn(h, srv, "c-wctx", "u-wctx")

	done := make(chan struct{})
	go func() { c.WritePump(); close(done) }()
	c.cancel() // ctx.Done() arm → immediate return
	select {
	case <-done:
	case <-time.After(2 * time.Second):
		t.Fatal("WritePump did not exit on ctx cancel")
	}
}
