package hub

import (
	"net"
	"time"

	"github.com/gorilla/websocket"
)

// WebSocketSession wraps gorilla *websocket.Conn to implement Session.
type WebSocketSession struct {
	conn *websocket.Conn
}

// NewWebSocketSession returns a new WebSocketSession.
func NewWebSocketSession(conn *websocket.Conn) *WebSocketSession {
	return &WebSocketSession{conn: conn}
}

// WriteMessage writes a message with specified messageType and payload.
func (s *WebSocketSession) WriteMessage(messageType int, data []byte) error {
	return s.conn.WriteMessage(messageType, data)
}

// ReadMessage reads a message from the WebSocket connection.
func (s *WebSocketSession) ReadMessage() (int, []byte, error) {
	return s.conn.ReadMessage()
}

// Close closes the underlying WebSocket connection.
func (s *WebSocketSession) Close() error {
	return s.conn.Close()
}

// RemoteAddr returns the remote network address.
func (s *WebSocketSession) RemoteAddr() net.Addr {
	return s.conn.RemoteAddr()
}

// TransportType returns the transport type identifier string.
func (s *WebSocketSession) TransportType() string {
	return "websocket"
}

// SetReadLimit sets the maximum size in bytes for a message.
func (s *WebSocketSession) SetReadLimit(limit int64) {
	s.conn.SetReadLimit(limit)
}

// SetReadDeadline sets the read deadline on the underlying connection.
func (s *WebSocketSession) SetReadDeadline(t time.Time) error {
	return s.conn.SetReadDeadline(t)
}

// SetWriteDeadline sets the write deadline on the underlying connection.
func (s *WebSocketSession) SetWriteDeadline(t time.Time) error {
	return s.conn.SetWriteDeadline(t)
}

// SetPongHandler sets the handler for pong messages.
func (s *WebSocketSession) SetPongHandler(h func(appData string) error) {
	s.conn.SetPongHandler(h)
}
