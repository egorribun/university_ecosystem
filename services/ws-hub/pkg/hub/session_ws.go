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

func (s *WebSocketSession) WriteMessage(messageType int, data []byte) error {
	return s.conn.WriteMessage(messageType, data)
}

func (s *WebSocketSession) ReadMessage() (int, []byte, error) {
	return s.conn.ReadMessage()
}

func (s *WebSocketSession) Close() error {
	return s.conn.Close()
}

func (s *WebSocketSession) RemoteAddr() net.Addr {
	return s.conn.RemoteAddr()
}

func (s *WebSocketSession) TransportType() string {
	return "websocket"
}

func (s *WebSocketSession) SetReadLimit(limit int64) {
	s.conn.SetReadLimit(limit)
}

func (s *WebSocketSession) SetReadDeadline(t time.Time) error {
	return s.conn.SetReadDeadline(t)
}

func (s *WebSocketSession) SetWriteDeadline(t time.Time) error {
	return s.conn.SetWriteDeadline(t)
}

func (s *WebSocketSession) SetPongHandler(h func(appData string) error) {
	s.conn.SetPongHandler(h)
}
