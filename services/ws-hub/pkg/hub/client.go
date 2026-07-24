package hub

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"net"
	"strings"
	"sync"
	"time"

	"github.com/gorilla/websocket"
	"github.com/quic-go/webtransport-go"
	"golang.org/x/time/rate"
)

// Client represents a connected user session (WebSocket or WebTransport).
type Client struct {
	ID        string
	UserID    string
	TenantID  string
	Conn      Session
	Rooms     map[string]bool
	Send      chan []byte
	Hub       *Hub
	mu        sync.Mutex
	closeOnce sync.Once
	// ctx / cancel are tied to this connection's lifetime.
	ctx    context.Context
	cancel context.CancelFunc
}

type chEntry struct {
	mu     sync.RWMutex
	closed bool
}

var (
	chMutexes = make(map[interface{}]*chEntry)
	chMu      sync.Mutex
)

// safeSend writes data to ch without panicking if the channel is already
// closed.
func safeSend(ch chan []byte, data []byte) (sent bool) {
	chMu.Lock()
	entry, ok := chMutexes[ch]
	if !ok {
		entry = &chEntry{}
		chMutexes[ch] = entry
	}
	if entry.closed {
		chMu.Unlock()
		return false
	}
	chMu.Unlock()

	entry.mu.RLock()
	defer entry.mu.RUnlock()

	defer func() {
		if r := recover(); r != nil {
			sent = false
			chMu.Lock()
			delete(chMutexes, ch)
			chMu.Unlock()
		}
	}()
	select {
	case ch <- data:
		return true
	default:
		return false
	}
}

// safeClose closes a channel in a data-race-free manner and cleans up channel map entry.
func safeClose(ch chan []byte) {
	chMu.Lock()
	entry, ok := chMutexes[ch]
	if !ok {
		entry = &chEntry{}
	} else {
		delete(chMutexes, ch)
	}
	entry.closed = true
	chMu.Unlock()

	entry.mu.Lock()
	defer entry.mu.Unlock()

	defer func() {
		_ = recover() //nolint:errcheck // recover() returns interface{}; blank discard is the canonical pattern.
	}()
	close(ch)
}

func isNormalCloseError(err error) bool {
	if err == nil {
		return true
	}
	if errors.Is(err, io.EOF) || errors.Is(err, net.ErrClosed) {
		return true
	}
	if websocket.IsCloseError(err,
		websocket.CloseNormalClosure,
		websocket.CloseGoingAway,
		websocket.CloseNoStatusReceived,
		websocket.CloseAbnormalClosure) {
		return true
	}
	errStr := err.Error()
	if strings.Contains(errStr, "normal closure") ||
		strings.Contains(errStr, "NO_ERROR") ||
		strings.Contains(errStr, "application error 0x0") ||
		strings.Contains(errStr, "Application error 0x0") {
		return true
	}
	var sessErr *webtransport.SessionError
	if errors.As(err, &sessErr) && (sessErr.ErrorCode == 0 || sessErr.ErrorCode == 268) {
		return true
	}
	return false
}

// ReadPump pumps messages from the session connection to the hub.
func (c *Client) ReadPump() {
	defer func() {
		c.cancel()
		c.Hub.msgLimiters.Delete(c.ID)
		// RZ-W19-16: use select to avoid goroutine leak if Run() has already exited
		select {
		case c.Hub.Unregister <- c:
		case <-c.Hub.ctx.Done():
			c.closeOnce.Do(func() { safeClose(c.Send) })
		}
		if c.Conn != nil {
			if err := c.Conn.Close(); err != nil {
				c.Hub.Logger.ErrorContext(c.ctx, "Failed to close session connection", "client_id", c.ID, "err", err)
			}
		}
	}()

	if c.Conn != nil {
		c.Conn.SetReadLimit(64 * 1024)
		if err := c.Conn.SetReadDeadline(time.Now().Add(60 * time.Second)); err != nil {
			c.Hub.Logger.ErrorContext(c.ctx, "Failed to set read deadline", "err", err)
		}
		c.Conn.SetPongHandler(func(string) error {
			if err := c.Conn.SetReadDeadline(time.Now().Add(60 * time.Second)); err != nil {
				c.Hub.Logger.ErrorContext(c.ctx, "Failed to update read deadline in pong handler", "err", err)
			}
			return nil
		})
	}

	for {
		if c.Conn == nil {
			break
		}
		_, data, err := c.Conn.ReadMessage()
		if err != nil {
			if isNormalCloseError(err) {
				c.Hub.Logger.DebugContext(c.ctx, "Session closed normally", "client_id", c.ID)
			} else {
				c.Hub.Logger.WarnContext(c.ctx, "Session read error",
					"client_id", c.ID,
					"err", err)
			}
			break
		}

		var msg Message
		if err := json.Unmarshal(data, &msg); err != nil {
			continue
		}

		// MOD-27-02: Validate message type at parse boundary
		if !isAllowedMessageType(msg.Type) {
			UnknownMsgTypeTotal.Inc()
			continue
		}

		msg.From = c.ID
		c.handleIncomingMessage(msg, data)
	}
}

func (c *Client) handleIncomingMessage(msg Message, data []byte) {
	switch msg.Type {
	case "join":
		c.handleJoin(msg)
	case "leave":
		c.handleLeave(msg)
	case "message":
		c.handleMessage(msg, data)
	default:
		// RZ-27-05: Log unknown message types for protocol drift detection.
		UnknownMsgTypeTotal.Inc()
		c.Hub.Logger.WarnContext(c.ctx, "Unknown message type",
			"client_id", c.ID, "type", msg.Type)
	}
}

func (c *Client) handleJoin(msg Message) {
	if msg.Room == "" {
		return
	}
	if !c.Hub.AuthorizeRoomJoin(c.ctx, c.UserID, msg.Room) {
		AuthFailuresTotal.WithLabelValues("room_join_denied").Inc() // RZ-23-06: wire existing metric
		c.Hub.Logger.WarnContext(c.ctx, "Unauthorized room join rejected",
			"user", c.UserID,
			"room", msg.Room)
		return
	}
	c.JoinRoom(msg.Room)
}

func (c *Client) handleLeave(msg Message) {
	c.LeaveRoom(msg.Room)
}

var allowedMessageTypes = map[string]bool{
	"join":    true,
	"leave":   true,
	"message": true,
}

func isAllowedMessageType(t string) bool {
	return allowedMessageTypes[t]
}

func (c *Client) handleMessage(msg Message, data []byte) {
	// RZ-27-02: Reject oversized messages at ingress, matching the broadcast
	// limit (RZ-23-05). Without this, messages between 60 KB and 64 KB are
	// published to NATS but silently dropped at broadcast fan-out.
	const maxIncomingBytes = 60 * 1024 // match maxBroadcastBytes in hub.go
	if len(data) > maxIncomingBytes {
		c.Hub.Logger.WarnContext(c.ctx, "Incoming message exceeds size limit, notifying client",
			"client_id", c.ID, "size_bytes", len(data), "limit_bytes", maxIncomingBytes)
		IncomingDropsTotal.Inc()
		// RZ-31-02: Notify client so it can display a user-visible error.
		// Follows the same pattern as rate-limit notification below (lines 166-171).
		if notice, err := json.Marshal(map[string]string{
			"type":   "error",
			"code":   "message_too_large",
			"detail": "message exceeds 60 KB limit",
		}); err == nil {
			select {
			case c.Send <- notice:
			default: // Send buffer full — client already overwhelmed.
			}
		}
		return
	}

	// TD-W16-03 / RZ-W18-01: Use configurable rate limit fields copied to Hub struct.
	raw, _ := c.Hub.msgLimiters.LoadOrStore(c.ID,
		rate.NewLimiter(rate.Limit(c.Hub.clientMsgRateLimit), c.Hub.clientMsgRateBurst))
	if !raw.(*rate.Limiter).Allow() {
		c.Hub.Logger.WarnContext(c.ctx, "Client message rate limit exceeded — notifying client",
			"client_id", c.ID,
			"room", msg.Room)
		if notice, err := json.Marshal(map[string]string{"type": "rate_limit_exceeded"}); err == nil {
			select {
			case c.Send <- notice:
			default:
				// Send buffer full — client is already overwhelmed; drop silently.
			}
		}
		return
	}

	if js, err := c.Hub.Nats.JetStream(); err == nil {
		if _, err := js.PublishAsync("chat."+msg.Room, data); err != nil {
			c.Hub.Logger.ErrorContext(c.ctx, "Failed to publish async to JetStream", "err", err)
		}
	} else {
		c.Hub.Logger.ErrorContext(c.ctx, "Failed to init JetStream, falling back to core NATS", "err", err)
		if err := c.Hub.Nats.Publish("chat."+msg.Room, data); err != nil {
			c.Hub.Logger.ErrorContext(c.ctx, "Failed to publish to NATS", "err", err)
		}
	}
}

// WritePump pumps messages from the hub to the session connection.
func (c *Client) WritePump() {
	ticker := time.NewTicker(30 * time.Second)
	defer func() {
		ticker.Stop()
		c.Hub.msgLimiters.Delete(c.ID) // TD-24-05: clean limiter on WritePump exit too
		if c.Conn != nil {
			if err := c.Conn.Close(); err != nil {
				c.Hub.Logger.ErrorContext(c.ctx, "Failed to close session connection in WritePump", "err", err)
			}
		}
	}()

	for {
		select {
		case msg, ok := <-c.Send:
			if c.Conn != nil {
				if err := c.Conn.SetWriteDeadline(time.Now().Add(10 * time.Second)); err != nil {
					c.Hub.Logger.ErrorContext(c.ctx, "Failed to set write deadline", "err", err)
				}
			}
			if !ok {
				if c.Conn != nil {
					if err := c.Conn.WriteMessage(websocket.CloseMessage, []byte{}); err != nil {
						c.Hub.Logger.ErrorContext(c.ctx, "Failed to write close message", "err", err)
					}
				}
				return
			}

			if c.Conn != nil {
				if err := c.Conn.WriteMessage(websocket.TextMessage, msg); err != nil {
					return
				}
			}

		case <-c.ctx.Done():
			// RZ-26-08: context cancelled (ReadPump exited) — stop immediately
			return

		case <-ticker.C:
			if c.Conn != nil {
				if err := c.Conn.SetWriteDeadline(time.Now().Add(10 * time.Second)); err != nil {
					c.Hub.Logger.ErrorContext(c.ctx, "Failed to set write deadline for ping", "err", err)
				}
				if err := c.Conn.WriteMessage(websocket.PingMessage, nil); err != nil {
					return
				}
			}
		}
	}
}

// JoinRoom adds the client to the specified room.
func (c *Client) JoinRoom(room string) {
	if room == "" {
		return
	}

	c.Hub.mu.Lock()
	defer c.Hub.mu.Unlock()

	c.mu.Lock()
	c.Rooms[room] = true
	c.mu.Unlock()

	if c.Hub.Rooms[room] == nil {
		c.Hub.Rooms[room] = make(map[*Client]bool)
	}
	c.Hub.Rooms[room][c] = true

	c.Hub.Logger.DebugContext(c.ctx, "Client joined room", "client", c.ID, "room", room)
}

// LeaveRoom removes the client from the specified room.
func (c *Client) LeaveRoom(room string) {
	if room == "" {
		return
	}

	c.Hub.mu.Lock()
	defer c.Hub.mu.Unlock()

	c.mu.Lock()
	delete(c.Rooms, room)
	c.mu.Unlock()

	if clients, ok := c.Hub.Rooms[room]; ok {
		delete(clients, c)
		if len(clients) == 0 {
			delete(c.Hub.Rooms, room)
		}
	}
}
