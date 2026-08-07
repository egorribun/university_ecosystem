package hub

import (
	"context"
	"errors"
	"io"
	"net"
	"sync"
	"time"

	"github.com/gorilla/websocket"
	"github.com/quic-go/webtransport-go"
)

// WebTransportSession adapts a quic-go webtransport.Session to implement Session.
type WebTransportSession struct {
	sess      webTransportSession
	stream    webTransportStream
	streamMu  sync.Mutex
	readLimit int64
	closed    bool
	closeMu   sync.Mutex
}

// webTransportStream is the small part of a bidirectional WebTransport stream
// used by the Session adapter. Keeping this boundary explicit makes the
// adapter testable without starting a QUIC listener for every error path.
type webTransportStream interface {
	io.Reader
	io.Writer
	Close() error
	SetReadDeadline(time.Time) error
	SetWriteDeadline(time.Time) error
}

type webTransportSession interface {
	RemoteAddr() net.Addr
	CloseWithError(webtransport.SessionErrorCode, string) error
	AcceptStream(context.Context) (webTransportStream, error)
	SendDatagram([]byte) error
}

type realWebTransportSession struct{ sess *webtransport.Session }

func (s *realWebTransportSession) RemoteAddr() net.Addr {
	return s.sess.RemoteAddr()
}

func (s *realWebTransportSession) CloseWithError(code webtransport.SessionErrorCode, message string) error {
	return s.sess.CloseWithError(code, message)
}

func (s *realWebTransportSession) AcceptStream(ctx context.Context) (webTransportStream, error) {
	return s.sess.AcceptStream(ctx)
}

func (s *realWebTransportSession) SendDatagram(data []byte) error {
	return s.sess.SendDatagram(data)
}

// NewWebTransportSession creates a new WebTransportSession wrapping sess.
func NewWebTransportSession(sess *webtransport.Session) *WebTransportSession {
	var adapted webTransportSession
	if sess != nil {
		adapted = &realWebTransportSession{sess: sess}
	}
	return &WebTransportSession{
		sess:      adapted,
		readLimit: 64 * 1024,
	}
}

// TransportType returns the transport type identifier string ("webtransport").
func (s *WebTransportSession) TransportType() string {
	return "webtransport"
}

// RemoteAddr returns the remote network address of the WebTransport session.
func (s *WebTransportSession) RemoteAddr() net.Addr {
	if s.sess != nil {
		return s.sess.RemoteAddr()
	}
	return dummyAddr{}
}

type dummyAddr struct{}

func (dummyAddr) Network() string { return "udp" }
func (dummyAddr) String() string  { return "127.0.0.1:0" }

// Close closes the underlying WebTransport session and stream.
func (s *WebTransportSession) Close() error {
	s.closeMu.Lock()
	defer s.closeMu.Unlock()
	if s.closed {
		return nil
	}
	s.closed = true
	var closeErr error
	if s.sess != nil {
		closeErr = s.sess.CloseWithError(0, "normal closure")
	}
	s.streamMu.Lock()
	if s.stream != nil {
		if err := s.stream.Close(); err != nil && closeErr == nil {
			closeErr = err
		}
	}
	s.streamMu.Unlock()
	return closeErr
}

// SetReadLimit sets the maximum size in bytes for a read operation.
func (s *WebTransportSession) SetReadLimit(limit int64) {
	s.readLimit = limit
}

// SetReadDeadline sets the read deadline on the underlying stream.
func (s *WebTransportSession) SetReadDeadline(t time.Time) error {
	s.streamMu.Lock()
	defer s.streamMu.Unlock()
	if s.stream != nil {
		return s.stream.SetReadDeadline(t)
	}
	return nil
}

// SetWriteDeadline sets the write deadline on the underlying stream.
func (s *WebTransportSession) SetWriteDeadline(t time.Time) error {
	s.streamMu.Lock()
	defer s.streamMu.Unlock()
	if s.stream != nil {
		return s.stream.SetWriteDeadline(t)
	}
	return nil
}

// SetPongHandler sets the handler for pong messages (no-op for WebTransport).
func (s *WebTransportSession) SetPongHandler(h func(appData string) error) {
	// WebTransport runs over QUIC which natively handles keep-alives at transport level.
	// Pong handler is a no-op for WebTransport.
}

func (s *WebTransportSession) getOrAcceptStream() (webTransportStream, error) {
	s.streamMu.Lock()
	defer s.streamMu.Unlock()

	if s.stream != nil {
		return s.stream, nil
	}
	if s.closed {
		return nil, io.EOF
	}
	if s.sess == nil {
		return nil, errors.New("webtransport session is nil")
	}

	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	st, err := s.sess.AcceptStream(ctx)
	if err != nil {
		return nil, err
	}

	s.stream = st
	return st, nil
}

// ReadMessage reads a message payload from the stream.
func (s *WebTransportSession) ReadMessage() (int, []byte, error) {
	st, err := s.getOrAcceptStream()
	if err != nil {
		return 0, nil, err
	}

	buf := make([]byte, s.readLimit)
	n, err := st.Read(buf)
	if err != nil {
		return 0, nil, err
	}
	return websocket.TextMessage, buf[:n], nil
}

// WriteMessage writes a message payload to the stream or datagram.
func (s *WebTransportSession) WriteMessage(messageType int, data []byte) error {
	if messageType == websocket.PingMessage || messageType == websocket.PongMessage {
		// QUIC handles keep-alives natively.
		return nil
	}
	if messageType == websocket.CloseMessage {
		return s.Close()
	}

	st, err := s.getOrAcceptStream()
	if err != nil {
		// Fall back to sending datagram if stream accept failed/not available
		if s.sess != nil {
			return s.sess.SendDatagram(data)
		}
		return err
	}

	_, err = st.Write(data)
	return err
}
