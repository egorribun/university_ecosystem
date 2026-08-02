package hub

import (
	"context"
	"errors"
	"io"
	"net"
	"testing"
	"time"

	"github.com/gorilla/websocket"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

type recordingSession struct {
	readLimit        int64
	readDeadlines    []time.Time
	readDeadlineErr  error
	writeDeadlines   []time.Time
	writeDeadlineErr error
	pongHandler      func(string) error
	writes           []recordedSessionWrite
	writeMessageErr  error
	writeObserved    chan struct{}
	closeErr         error
}

type recordedSessionWrite struct {
	messageType int
	data        []byte
}

func (s *recordingSession) ReadMessage() (int, []byte, error) {
	return 0, nil, io.EOF
}

func (s *recordingSession) SetReadLimit(limit int64) {
	s.readLimit = limit
}

func (s *recordingSession) SetReadDeadline(deadline time.Time) error {
	s.readDeadlines = append(s.readDeadlines, deadline)
	return s.readDeadlineErr
}

func (s *recordingSession) SetWriteDeadline(deadline time.Time) error {
	s.writeDeadlines = append(s.writeDeadlines, deadline)
	return s.writeDeadlineErr
}

func (s *recordingSession) SetPongHandler(handler func(string) error) {
	s.pongHandler = handler
}

func (s *recordingSession) WriteMessage(messageType int, data []byte) error {
	s.writes = append(s.writes, recordedSessionWrite{
		messageType: messageType,
		data:        append([]byte(nil), data...),
	})
	if s.writeObserved != nil {
		select {
		case s.writeObserved <- struct{}{}:
		default:
		}
	}
	return s.writeMessageErr
}

func (s *recordingSession) Close() error {
	return s.closeErr
}

func (s *recordingSession) RemoteAddr() net.Addr {
	return &net.TCPAddr{}
}

func (s *recordingSession) TransportType() string {
	return "test"
}

func TestClientSetupConnection_ConfiguresReadLimitAndPongRefresh(t *testing.T) {
	h := setupTestHub()
	session := &recordingSession{}
	client := &Client{
		Conn: session,
		Hub:  h,
		ctx:  context.Background(),
	}

	started := time.Now()
	client.setupConnection()
	finished := time.Now()

	assert.Equal(t, int64(64*1024), session.readLimit)
	require.Len(t, session.readDeadlines, 1)
	assert.True(t, session.readDeadlines[0].After(started.Add(59*time.Second)))
	assert.True(t, session.readDeadlines[0].Before(finished.Add(61*time.Second)))
	require.NotNil(t, session.pongHandler)

	assert.NoError(t, session.pongHandler("keep-alive"))
	require.Len(t, session.readDeadlines, 2)
	assert.WithinDuration(t, time.Now().Add(60*time.Second), session.readDeadlines[1], 2*time.Second)
}

func TestClientSetupConnection_LogsDeadlineErrorsAndReturnsNilFromPong(t *testing.T) {
	h := setupTestHub()
	session := &recordingSession{readDeadlineErr: errors.New("deadline unavailable")}
	client := &Client{
		Conn: session,
		Hub:  h,
		ctx:  context.Background(),
	}

	client.setupConnection()
	require.NotNil(t, session.pongHandler)
	assert.NoError(t, session.pongHandler("deadline-error"))
	assert.Len(t, session.readDeadlines, 2)
}

func TestClientSetupConnection_NilSessionIsNoOp(t *testing.T) {
	client := &Client{Hub: setupTestHub(), ctx: context.Background()}

	assert.NotPanics(t, client.setupConnection)
}

func TestClientDisconnect_QueuesClientForHubUnregister(t *testing.T) {
	h := setupTestHub()
	h.Unregister = make(chan *Client, 1)
	session := &recordingSession{}
	client := &Client{
		ID:     "disconnect-client",
		UserID: "disconnect-user",
		Conn:   session,
		Hub:    h,
		Send:   make(chan []byte, 1),
		ctx:    context.Background(),
	}

	client.Disconnect(4401, "Access Revoked")

	require.Len(t, session.writeDeadlines, 1)
	require.Len(t, session.writes, 1)
	assert.Equal(t, websocket.CloseMessage, session.writes[0].messageType)
	assert.Equal(t, websocket.FormatCloseMessage(4401, "Access Revoked"), session.writes[0].data)
	select {
	case registered := <-h.Unregister:
		assert.Same(t, client, registered)
	default:
		t.Fatal("Disconnect did not enqueue client for unregister")
	}

	select {
	case _, open := <-client.Send:
		assert.True(t, open, "Send must remain open when unregister owns teardown")
	default:
	}
}

func TestClientDisconnect_ClosesSendOnHubShutdownAndHandlesWriteErrors(t *testing.T) {
	h := setupTestHub()
	hubCtx, cancel := context.WithCancel(context.Background())
	cancel()
	h.lifecycleMu.Lock()
	h.ctx = hubCtx
	h.lifecycleMu.Unlock()

	session := &recordingSession{
		writeDeadlineErr: errors.New("write deadline unavailable"),
		writeMessageErr:  errors.New("connection already closed"),
	}
	client := &Client{
		ID:     "shutdown-client",
		UserID: "shutdown-user",
		Conn:   session,
		Hub:    h,
		Send:   make(chan []byte, 1),
		ctx:    context.Background(),
	}

	client.Disconnect(1000, "shutdown")

	require.Len(t, session.writeDeadlines, 1)
	require.Len(t, session.writes, 1)
	select {
	case _, open := <-client.Send:
		assert.False(t, open, "Send must close when the hub lifecycle is done")
	case <-time.After(time.Second):
		t.Fatal("Disconnect did not close Send after hub shutdown")
	}
}

func TestClientDisconnectWithoutHubOnlyWritesCloseFrame(t *testing.T) {
	session := &recordingSession{}
	send := make(chan []byte, 1)
	client := &Client{
		Conn: session,
		Send: send,
		ctx:  context.Background(),
	}

	client.Disconnect(1001, "going away")

	require.Len(t, session.writes, 1)
	assert.Equal(t, websocket.CloseMessage, session.writes[0].messageType)
	select {
	case _, open := <-send:
		assert.True(t, open)
	default:
	}
}

func TestClientWritePump_LogsWriteDeadlineErrorBeforeWriting(t *testing.T) {
	h := setupTestHub()
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	session := &recordingSession{
		writeDeadlineErr: errors.New("write deadline unavailable"),
		writeObserved:    make(chan struct{}, 1),
	}
	client := &Client{
		ID:   "write-deadline-client",
		Conn: session,
		Hub:  h,
		Send: make(chan []byte, 1),
		ctx:  ctx,
	}
	done := make(chan struct{})
	go func() {
		client.WritePump()
		close(done)
	}()

	client.Send <- []byte("deadline-error-payload")
	select {
	case <-session.writeObserved:
	case <-time.After(time.Second):
		t.Fatal("WritePump did not write the queued message")
	}
	cancel()

	select {
	case <-done:
	case <-time.After(time.Second):
		t.Fatal("WritePump did not stop after context cancellation")
	}

	require.Len(t, session.writeDeadlines, 1)
	assert.Equal(t, websocket.TextMessage, session.writes[0].messageType)
	assert.Equal(t, []byte("deadline-error-payload"), session.writes[0].data)
}

func TestClientWritePump_SendsHeartbeatAndStopsOnPingError(t *testing.T) {
	h := setupTestHub()
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	session := &recordingSession{
		writeDeadlineErr: errors.New("ping deadline unavailable"),
		writeMessageErr:  errors.New("ping connection closed"),
		writeObserved:    make(chan struct{}, 1),
	}
	client := &Client{
		ID:   "heartbeat-client",
		Conn: session,
		Hub:  h,
		Send: make(chan []byte, 1),
		ctx:  ctx,
	}

	originalInterval := writePumpPingInterval
	writePumpPingInterval = time.Millisecond
	t.Cleanup(func() { writePumpPingInterval = originalInterval })

	done := make(chan struct{})
	go func() {
		client.WritePump()
		close(done)
	}()

	select {
	case <-session.writeObserved:
	case <-time.After(time.Second):
		t.Fatal("WritePump did not send a heartbeat")
	}

	select {
	case <-done:
	case <-time.After(time.Second):
		t.Fatal("WritePump did not stop after heartbeat write failure")
	}

	require.NotEmpty(t, session.writes)
	assert.Equal(t, websocket.PingMessage, session.writes[0].messageType)
}
