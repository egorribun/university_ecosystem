package hub

import (
	"net"
	"time"
)

// SessionWriter defines the interface for writing messages to a client session.
type SessionWriter interface {
	WriteMessage(messageType int, data []byte) error
	Close() error
	RemoteAddr() net.Addr
	TransportType() string
}

// Session extends SessionWriter with reading, deadline, and handler capabilities.
type Session interface {
	SessionWriter
	ReadMessage() (messageType int, data []byte, err error)
	SetReadLimit(limit int64)
	SetReadDeadline(t time.Time) error
	SetWriteDeadline(t time.Time) error
	SetPongHandler(h func(appData string) error)
}
