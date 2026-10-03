package hub

import (
	"bufio"
	"context"
	"encoding/json"
	"errors"
	"io"
	"net"
	"sync"
	"sync/atomic"
	"time"

	"github.com/gorilla/websocket"
	"github.com/quic-go/webtransport-go"
)

// WebTransportSession adapts a quic-go webtransport.Session to implement Session.
type WebTransportSession struct {
	sess          webTransportSession
	stream        webTransportStream
	streamMu      sync.Mutex
	reader        *bufio.Reader
	readMu        sync.Mutex
	writeMu       sync.Mutex
	readLimit     int64
	readDeadline  time.Time
	writeDeadline time.Time
	closed        atomic.Bool
	closeMu       sync.Mutex
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
	AcceptStream(context.Context) (*webtransport.Stream, error)
	SendDatagram([]byte) error
}

// NewWebTransportSession creates a new WebTransportSession wrapping sess.
func NewWebTransportSession(sess *webtransport.Session) *WebTransportSession {
	var adapted webTransportSession
	if sess != nil {
		adapted = sess
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
	if s.closed.Load() {
		return nil
	}
	s.closed.Store(true)
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

// SetReadLimit sets the maximum size in bytes of an inbound JSON object.
func (s *WebTransportSession) SetReadLimit(limit int64) {
	s.readLimit = limit
}

// SetReadDeadline sets the read deadline on the underlying stream.
func (s *WebTransportSession) SetReadDeadline(t time.Time) error {
	s.streamMu.Lock()
	defer s.streamMu.Unlock()
	s.readDeadline = t
	if s.stream != nil {
		return s.stream.SetReadDeadline(t)
	}
	return nil
}

// SetWriteDeadline sets the write deadline on the underlying stream.
func (s *WebTransportSession) SetWriteDeadline(t time.Time) error {
	s.streamMu.Lock()
	defer s.streamMu.Unlock()
	s.writeDeadline = t
	if s.stream != nil {
		return s.stream.SetWriteDeadline(t)
	}
	return nil
}

// SetPongHandler sets the handler for pong messages (no-op for WebTransport).
func (s *WebTransportSession) SetPongHandler(h func(appData string) error) {
	// WebTransport runs over QUIC which natively handles keep-alives at transport level.
	// Pong handler is a no-op for WebTransport.
	_ = h
}

func (s *WebTransportSession) getOrAcceptStream() (webTransportStream, error) {
	s.streamMu.Lock()
	defer s.streamMu.Unlock()

	if s.stream != nil {
		return s.stream, s.applyStreamDeadlines()
	}
	if s.closed.Load() {
		return nil, io.EOF
	}
	if s.sess == nil {
		return nil, errors.New("webtransport session is nil")
	}

	// Bound first-stream acceptance by deadlines already assigned by the
	// pumps, including an expiry earlier than the ordinary ten-second cap.
	// streamMu serializes deadline setters with acceptance: a setter that
	// arrives during AcceptStream cannot revise this in-flight deadline.
	deadline := time.Now().Add(10 * time.Second)
	for _, pending := range []time.Time{s.readDeadline, s.writeDeadline} {
		if !pending.IsZero() && pending.Before(deadline) {
			deadline = pending
		}
	}
	ctx, cancel := context.WithDeadline(context.Background(), deadline)
	defer cancel()
	if err := ctx.Err(); err != nil {
		return nil, err
	}
	st, err := s.sess.AcceptStream(ctx)
	if err != nil {
		return nil, err
	}
	if st == nil {
		return nil, nil
	}

	s.stream = st
	return st, s.applyStreamDeadlines()
}

// applyStreamDeadlines retains deadlines set before the first accepted stream.
// The caller holds streamMu; zero values preserve the QUIC default.
func (s *WebTransportSession) applyStreamDeadlines() error {
	if !s.readDeadline.IsZero() {
		if err := s.stream.SetReadDeadline(s.readDeadline); err != nil {
			return err
		}
	}
	if !s.writeDeadline.IsZero() {
		return s.stream.SetWriteDeadline(s.writeDeadline)
	}
	return nil
}

// ReadMessage reads one JSON object from the byte stream. JSON objects are
// self-delimiting, so this preserves the existing raw-JSON wire format without
// assuming that a stream Read corresponds to a complete application message.
func (s *WebTransportSession) ReadMessage() (int, []byte, error) {
	s.readMu.Lock()
	defer s.readMu.Unlock()

	st, err := s.getOrAcceptStream()
	if err != nil {
		return 0, nil, err
	}
	if st == nil {
		return 0, nil, errors.New("webtransport stream is nil")
	}

	if s.readLimit <= 0 {
		return 0, nil, errors.New("webtransport read limit must be positive")
	}
	if s.reader == nil {
		s.reader = bufio.NewReader(st)
	}
	payload, err := readJSONObject(s.reader, s.readLimit)
	if err != nil {
		return 0, nil, err
	}
	return websocket.TextMessage, payload, nil
}

func readJSONObject(reader *bufio.Reader, limit int64) ([]byte, error) {
	if err := readJSONObjectStart(reader, limit); err != nil {
		return nil, err
	}
	payload := []byte{'{'}
	boundary := jsonObjectBoundary{depth: 1}
	for boundary.depth > 0 {
		b, err := reader.ReadByte()
		if err != nil {
			if errors.Is(err, io.EOF) {
				err = io.ErrUnexpectedEOF
			}
			return nil, err
		}
		if int64(len(payload)) >= limit {
			return nil, errors.New("webtransport message exceeds read limit")
		}
		payload = append(payload, b)
		boundary.consume(b)
	}
	if !json.Valid(payload) {
		return nil, errors.New("invalid webtransport JSON object")
	}
	return payload, nil
}

func readJSONObjectStart(reader *bufio.Reader, limit int64) error {
	for skipped := int64(0); skipped <= limit; skipped++ {
		b, err := reader.ReadByte()
		if err != nil {
			return err
		}
		switch b {
		case ' ', '\t', '\r', '\n':
			continue
		case '{':
			return nil
		default:
			return errors.New("webtransport message must be a JSON object")
		}
	}
	return errors.New("webtransport message exceeds read limit")
}

// jsonObjectBoundary locates the outer closing brace without interpreting
// braces inside strings. json.Valid checks the complete object's syntax.
type jsonObjectBoundary struct {
	depth    int
	inString bool
	escaped  bool
}

func (b *jsonObjectBoundary) consume(char byte) {
	if b.inString {
		if b.escaped {
			b.escaped = false
		} else if char == '\\' {
			b.escaped = true
		} else if char == '"' {
			b.inString = false
		}
		return
	}
	switch char {
	case '"':
		b.inString = true
	case '{':
		b.depth++
	case '}':
		b.depth--
	}
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
	s.writeMu.Lock()
	defer s.writeMu.Unlock()

	st, err := s.getOrAcceptStream()
	if err != nil {
		// A present stream with a deadline-application failure must fail
		// closed rather than silently switching to an unchecked datagram.
		if st != nil {
			return err
		}
		if s.sess != nil {
			return s.writeDatagram(data)
		}
		return err
	}
	if st == nil {
		// getOrAcceptStream can return (nil, nil) only after a non-nil session
		// accepted no stream. Preserve delivery by using its datagram path.
		return s.writeDatagram(data)
	}

	for len(data) > 0 {
		n, err := st.Write(data)
		if err != nil {
			return err
		}
		if n <= 0 || n > len(data) {
			return io.ErrShortWrite
		}
		data = data[n:]
	}
	return nil
}

// writeDatagram preserves the fallback's nonblocking delivery while honoring
// the same pending write cutoff as the stream path.
func (s *WebTransportSession) writeDatagram(data []byte) error {
	s.streamMu.Lock()
	defer s.streamMu.Unlock()
	if !s.writeDeadline.IsZero() && !time.Now().Before(s.writeDeadline) {
		return context.DeadlineExceeded
	}
	return s.sess.SendDatagram(data)
}
