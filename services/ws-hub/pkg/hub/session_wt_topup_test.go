package hub

import (
	"context"
	"errors"
	"io"
	"net"
	"testing"
	"time"

	"github.com/gorilla/websocket"
	"github.com/quic-go/webtransport-go"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestWebTransportSession_NilAndClosedGuards(t *testing.T) {
	s := NewWebTransportSession(nil)
	assert.Equal(t, "webtransport", s.TransportType())
	assert.Equal(t, "udp", s.RemoteAddr().Network())
	assert.Equal(t, "127.0.0.1:0", s.RemoteAddr().String())
	assert.NoError(t, s.SetReadDeadline(nowForSessionTest()))
	assert.NoError(t, s.SetWriteDeadline(nowForSessionTest()))
	s.SetPongHandler(func(string) error { return errors.New("must not be called") })

	assert.NoError(t, s.WriteMessage(websocket.PingMessage, nil))
	assert.NoError(t, s.WriteMessage(websocket.PongMessage, nil))
	_, _, err := s.ReadMessage()
	assert.EqualError(t, err, "webtransport session is nil")
	assert.NoError(t, s.Close())
	assert.NoError(t, s.Close(), "Close is idempotent")

	_, _, err = s.ReadMessage()
	assert.ErrorIs(t, err, io.EOF)
	assert.ErrorIs(t, s.WriteMessage(websocket.TextMessage, []byte("after-close")), io.EOF)
	assert.NoError(t, s.WriteMessage(websocket.CloseMessage, nil))
}

func TestWebTransportSession_GetOrAcceptStreamNilSessionAndClosed(t *testing.T) {
	open := NewWebTransportSession(nil)
	stream, err := open.getOrAcceptStream()
	assert.Nil(t, stream)
	assert.EqualError(t, err, "webtransport session is nil")

	closed := NewWebTransportSession(nil)
	require.NoError(t, closed.Close())
	stream, err = closed.getOrAcceptStream()
	assert.Nil(t, stream)
	assert.ErrorIs(t, err, io.EOF)
}

func nowForSessionTest() time.Time { return time.Now() }

type fakeWebTransportStream struct {
	readData        []byte
	readErr         error
	writeErr        error
	closeErr        error
	readDeadline    error
	writeDeadline   error
	readDeadlineAt  time.Time
	writeDeadlineAt time.Time
}

func (s *fakeWebTransportStream) Read(p []byte) (int, error) {
	if s.readErr != nil {
		return 0, s.readErr
	}
	return copy(p, s.readData), nil
}

func (s *fakeWebTransportStream) Write(p []byte) (int, error) {
	if s.writeErr != nil {
		return 0, s.writeErr
	}
	return len(p), nil
}

func (s *fakeWebTransportStream) Close() error { return s.closeErr }

func (s *fakeWebTransportStream) SetReadDeadline(at time.Time) error {
	s.readDeadlineAt = at
	return s.readDeadline
}

func (s *fakeWebTransportStream) SetWriteDeadline(at time.Time) error {
	s.writeDeadlineAt = at
	return s.writeDeadline
}

type fakeWebTransportSession struct {
	remote      net.Addr
	closeErr    error
	acceptErr   error
	accepted    *webtransport.Stream
	datagramErr error
}

func (s *fakeWebTransportSession) RemoteAddr() net.Addr { return s.remote }

func (s *fakeWebTransportSession) CloseWithError(webtransport.SessionErrorCode, string) error {
	return s.closeErr
}

func (s *fakeWebTransportSession) AcceptStream(context.Context) (*webtransport.Stream, error) {
	if s.acceptErr != nil {
		return nil, s.acceptErr
	}
	return s.accepted, nil
}

func (s *fakeWebTransportSession) SendDatagram([]byte) error { return s.datagramErr }

func TestWebTransportSession_DelegatesSessionAndStreamOperations(t *testing.T) {
	stream := &fakeWebTransportStream{readData: []byte("hello")}
	session := &fakeWebTransportSession{remote: &net.UDPAddr{IP: net.IPv4(192, 0, 2, 1), Port: 443}}
	s := &WebTransportSession{sess: session, stream: stream, readLimit: 16}

	assert.Equal(t, session.remote, s.RemoteAddr())
	assert.NoError(t, s.SetReadDeadline(time.Now()))
	assert.NoError(t, s.SetWriteDeadline(time.Now()))
	_, data, err := s.ReadMessage()
	require.NoError(t, err)
	assert.Equal(t, "hello", string(data))
	assert.NoError(t, s.WriteMessage(websocket.TextMessage, []byte("payload")))

	assert.NoError(t, s.Close())
	assert.NoError(t, s.Close())
}

func TestWebTransportSession_DelegatesErrorsAndDatagramFallback(t *testing.T) {
	streamErr := errors.New("stream failure")
	stream := &fakeWebTransportStream{readErr: streamErr, writeErr: streamErr, closeErr: streamErr}
	sessionErr := errors.New("session failure")
	session := &fakeWebTransportSession{remote: &net.UDPAddr{}, closeErr: sessionErr}
	s := &WebTransportSession{sess: session, stream: stream, readLimit: 16}

	_, _, err := s.ReadMessage()
	assert.ErrorIs(t, err, streamErr)
	assert.ErrorIs(t, s.WriteMessage(websocket.TextMessage, []byte("payload")), streamErr)
	assert.ErrorIs(t, s.Close(), sessionErr, "session close error takes precedence")

	streamCloseOnly := &WebTransportSession{
		sess:   &fakeWebTransportSession{},
		stream: &fakeWebTransportStream{closeErr: streamErr},
	}
	assert.ErrorIs(t, streamCloseOnly.Close(), streamErr)

	noStream := &fakeWebTransportSession{datagramErr: nil, acceptErr: errors.New("stream unavailable")}
	s = &WebTransportSession{sess: noStream, readLimit: 16}
	assert.NoError(t, s.WriteMessage(websocket.TextMessage, []byte("datagram")))

	noDatagram := &fakeWebTransportSession{datagramErr: errors.New("datagram failure"), acceptErr: errors.New("stream unavailable")}
	s = &WebTransportSession{sess: noDatagram, readLimit: 16}
	assert.EqualError(t, s.WriteMessage(websocket.TextMessage, []byte("datagram")), "datagram failure")

	nilStream := &fakeWebTransportSession{}
	s = &WebTransportSession{sess: nilStream, readLimit: 16}
	_, _, err = s.ReadMessage()
	assert.EqualError(t, err, "webtransport stream is nil")
	assert.NoError(t, s.WriteMessage(websocket.TextMessage, []byte("datagram after nil stream")))

	noSession := &WebTransportSession{}
	assert.EqualError(t, noSession.WriteMessage(websocket.TextMessage, []byte("payload")), "webtransport session is nil")
}

func TestWebTransportSession_AcceptStreamAndExistingStreamPaths(t *testing.T) {
	stream := &fakeWebTransportStream{readData: []byte("accepted")}
	accepted := &webtransport.Stream{}
	session := &fakeWebTransportSession{accepted: accepted}
	s := &WebTransportSession{sess: session, readLimit: 16}
	got, err := s.getOrAcceptStream()
	require.NoError(t, err)
	assert.Same(t, accepted, got)
	s.stream = stream
	got, err = s.getOrAcceptStream()
	require.NoError(t, err)
	assert.Same(t, stream, got)

	failing := &WebTransportSession{sess: &fakeWebTransportSession{acceptErr: errors.New("accept failed")}, readLimit: 16}
	got, err = failing.getOrAcceptStream()
	assert.Nil(t, got)
	assert.EqualError(t, err, "accept failed")
}

func TestNewWebTransportSession_AdaptsConcreteSession(t *testing.T) {
	concrete := &webtransport.Session{}

	session := NewWebTransportSession(concrete)

	assert.Same(t, concrete, session.sess)
}
