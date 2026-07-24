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
	sess      *webtransport.Session
	stream    *webtransport.Stream
	streamMu  sync.Mutex
	readLimit int64
	readOnce  sync.Once
	closed    bool
	closeMu   sync.Mutex
}

// NewWebTransportSession creates a new WebTransportSession wrapping sess.
func NewWebTransportSession(sess *webtransport.Session) *WebTransportSession {
	return &WebTransportSession{
		sess:      sess,
		readLimit: 64 * 1024,
	}
}

func (s *WebTransportSession) TransportType() string {
	return "webtransport"
}

func (s *WebTransportSession) RemoteAddr() net.Addr {
	if s.sess != nil {
		return s.sess.RemoteAddr()
	}
	return dummyAddr{}
}

type dummyAddr struct{}

func (dummyAddr) Network() string { return "udp" }
func (dummyAddr) String() string  { return "127.0.0.1:0" }

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
		_ = s.stream.Close()
	}
	s.streamMu.Unlock()
	return closeErr
}

func (s *WebTransportSession) SetReadLimit(limit int64) {
	s.readLimit = limit
}

func (s *WebTransportSession) SetReadDeadline(t time.Time) error {
	s.streamMu.Lock()
	defer s.streamMu.Unlock()
	if s.stream != nil {
		return s.stream.SetReadDeadline(t)
	}
	return nil
}

func (s *WebTransportSession) SetWriteDeadline(t time.Time) error {
	s.streamMu.Lock()
	defer s.streamMu.Unlock()
	if s.stream != nil {
		return s.stream.SetWriteDeadline(t)
	}
	return nil
}

func (s *WebTransportSession) SetPongHandler(h func(appData string) error) {
	// WebTransport runs over QUIC which natively handles keep-alives at transport level.
	// Pong handler is a no-op for WebTransport.
}

func (s *WebTransportSession) getOrAcceptStream() (*webtransport.Stream, error) {
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
