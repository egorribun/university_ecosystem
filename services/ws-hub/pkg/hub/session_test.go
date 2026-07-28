package hub

import (
	"io"
	"testing"
	"time"

	"github.com/gorilla/websocket"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestWebSocketSession_Methods(t *testing.T) {
	srv, cli := newConnPair(t)
	t.Cleanup(func() { _ = srv.Close() }) //nolint:errcheck
	t.Cleanup(func() { _ = cli.Close() }) //nolint:errcheck

	sess := NewWebSocketSession(srv)
	assert.Equal(t, "websocket", sess.TransportType())
	assert.NotNil(t, sess.RemoteAddr())

	sess.SetReadLimit(1024)
	require.NoError(t, sess.SetReadDeadline(time.Now().Add(10*time.Second)))
	require.NoError(t, sess.SetWriteDeadline(time.Now().Add(10*time.Second)))
	sess.SetPongHandler(func(string) error { return nil })

	err := sess.WriteMessage(websocket.TextMessage, []byte("hello"))
	assert.NoError(t, err)

	_, msg, err := cli.ReadMessage()
	assert.NoError(t, err)
	assert.Equal(t, "hello", string(msg))

	err = sess.Close()
	assert.NoError(t, err)
}

func TestWebTransportSession_Methods(t *testing.T) {
	wtSess := NewWebTransportSession(nil)
	assert.Equal(t, "webtransport", wtSess.TransportType())
	assert.Equal(t, "udp", wtSess.RemoteAddr().Network())
	assert.Equal(t, "127.0.0.1:0", wtSess.RemoteAddr().String())

	wtSess.SetReadLimit(2048)
	assert.NoError(t, wtSess.SetReadDeadline(time.Now()))
	assert.NoError(t, wtSess.SetWriteDeadline(time.Now()))
	wtSess.SetPongHandler(func(string) error { return nil })

	// Ping/pong should be no-op
	assert.NoError(t, wtSess.WriteMessage(websocket.PingMessage, nil))
	assert.NoError(t, wtSess.WriteMessage(websocket.PongMessage, nil))

	// Close
	assert.NoError(t, wtSess.Close())
	// Second close is no-op
	assert.NoError(t, wtSess.Close())
}

func TestWebTransportSession_EOF_And_Closed(t *testing.T) {
	wtSess := NewWebTransportSession(nil)
	// getOrAcceptStream on nil sess returns error
	_, err := wtSess.getOrAcceptStream()
	assert.Error(t, err)

	// ReadMessage on nil sess returns error
	_, _, err = wtSess.ReadMessage()
	assert.Error(t, err)

	// Close session
	require.NoError(t, wtSess.Close())
	_, err = wtSess.getOrAcceptStream()
	assert.Equal(t, io.EOF, err)
}
