package hub

import (
	"context"
	"encoding/json"
	"sync"
	"time"

	"github.com/gorilla/websocket"
	"go.uber.org/zap"
	"golang.org/x/time/rate"
)

type Client struct {
	ID     string
	UserID string
	Conn   *websocket.Conn
	Rooms  map[string]bool
	Send      chan []byte
	Hub       *Hub
	mu        sync.Mutex
	closeOnce sync.Once
	// ctx / cancel are tied to this connection's lifetime.
	// ctx is cancelled when ReadPump exits (connection closed / client gone).
	// Pass ctx to AuthorizeRoomJoin so that backend HTTP checks are cancelled
	// when the client disconnects. (WSH-05, audit 2026-03-08 Wave 5)
	ctx    context.Context
	cancel context.CancelFunc
}

// safeSend writes data to ch without panicking if the channel is already
// closed.  It returns true when the message was queued and false when either
// the channel is full (non-evict path) or was closed (RZ-F-02).
//
// Background: Go panics on any send to a closed channel, including sends
// inside a select statement.  After broadcastMessage releases h.mu.RLock,
// the Unregister handler can close client.Send before the fan-out loop
// reaches that client.  recover() is the only way to catch that panic safely.
func safeSend(ch chan []byte, data []byte) (sent bool) {
	defer func() {
		if recover() != nil {
			sent = false
		}
	}()
	select {
	case ch <- data:
		return true
	default:
		return false
	}
}

func (c *Client) ReadPump() {
	defer func() {
		// Cancel the client context so that any pending AuthorizeRoomJoin
		// HTTP checks (CanJoinRoom) are aborted immediately on disconnect.
		c.cancel()
		// TD-01 (audit 2026-03-15 Wave 7): remove per-client rate limiter
		// entry to prevent unbounded growth of msgLimiters sync.Map.
		c.Hub.msgLimiters.Delete(c.ID)
		c.Hub.Unregister <- c
		_ = c.Conn.Close()
	}()

	c.Conn.SetReadLimit(64 * 1024)
	_ = c.Conn.SetReadDeadline(time.Now().Add(60 * time.Second))
	c.Conn.SetPongHandler(func(string) error {
		_ = c.Conn.SetReadDeadline(time.Now().Add(60 * time.Second))
		return nil
	})

	for {
		_, data, err := c.Conn.ReadMessage()
		if err != nil {
			// TD-07 (audit 2026-03-15 Wave 7): distinguish normal closes from
			// unexpected errors so operators can spot protocol violations or attacks.
			if websocket.IsCloseError(err,
				websocket.CloseNormalClosure,
				websocket.CloseGoingAway,
				websocket.CloseNoStatusReceived) {
				c.Hub.Logger.Debug("WebSocket closed normally", zap.String("client_id", c.ID))
			} else {
				c.Hub.Logger.Warn("WebSocket read error",
					zap.String("client_id", c.ID),
					zap.Error(err))
			}
			break
		}

		var msg Message
		if err := json.Unmarshal(data, &msg); err != nil {
			continue
		}

		msg.From = c.ID

		switch msg.Type {
		case "join":
			// Every room-join must be authorized against the Python backend's
			// participant table to prevent OWASP A01 (broken access control).
			// Any authenticated user who knows a chat UUID must be blocked
			// from joining rooms they are not a participant of.
			if msg.Room == "" {
				break
			}
			if !c.Hub.AuthorizeRoomJoin(c.ctx, c.UserID, msg.Room) {
				c.Hub.Logger.Warn("Unauthorized room join rejected",
					zap.String("user", c.UserID),
					zap.String("room", msg.Room))
				break
			}
			c.JoinRoom(msg.Room)
		case "leave":
			c.LeaveRoom(msg.Room)
		case "message":
			// TD-01 (audit 2026-03-15 Wave 7): per-client token bucket prevents
			// a single WS connection from flooding NATS JetStream and causing
			// backpressure / delivery failures for all other clients.
			// Limit: 10 msg/sec, burst 20 — generous for human typing (~0.5 words/sec).
			//
			// WSH-P2-02 (audit Wave 10): notify the client so it can implement
			// exponential back-off instead of silently losing messages.  The
			// control frame is small and its presence does NOT fingerprint a
			// useful limit value — the burst size is not disclosed.
			raw, _ := c.Hub.msgLimiters.LoadOrStore(c.ID,
				rate.NewLimiter(rate.Limit(10), 20))
			if !raw.(*rate.Limiter).Allow() {
				c.Hub.Logger.Warn("Client message rate limit exceeded — notifying client",
					zap.String("client_id", c.ID),
					zap.String("room", msg.Room))
				if notice, err := json.Marshal(map[string]string{"type": "rate_limit_exceeded"}); err == nil {
					select {
					case c.Send <- notice:
					default:
						// Send buffer full — client is already overwhelmed; drop silently.
					}
				}
				break
			}
			// Publish to NATS only. The hub's NATS subscriber will fan the
			// message out to all connected clients via the Broadcast channel.
			// Direct Broadcast <- &msg is intentionally removed to prevent
			// duplicate delivery (RZ-6: audit 2026-02-24).
			if js, err := c.Hub.Nats.JetStream(); err == nil {
				_, _ = js.PublishAsync("chat."+msg.Room, data)
			} else {
				c.Hub.Logger.Error("Failed to init JetStream, falling back to core NATS", zap.Error(err))
				_ = c.Hub.Nats.Publish("chat."+msg.Room, data)
			}
		}
	}
}

func (c *Client) WritePump() {
	ticker := time.NewTicker(30 * time.Second)
	defer func() {
		ticker.Stop()
		_ = c.Conn.Close()
	}()

	for {
		select {
		case msg, ok := <-c.Send:
			_ = c.Conn.SetWriteDeadline(time.Now().Add(10 * time.Second))
			if !ok {
				_ = c.Conn.WriteMessage(websocket.CloseMessage, []byte{})
				return
			}

			if err := c.Conn.WriteMessage(websocket.TextMessage, msg); err != nil {
				return
			}

		case <-ticker.C:
			_ = c.Conn.SetWriteDeadline(time.Now().Add(10 * time.Second))
			if err := c.Conn.WriteMessage(websocket.PingMessage, nil); err != nil {
				return
			}
		}
	}
}

func (c *Client) JoinRoom(room string) {
	if room == "" {
		return
	}

	c.Hub.mu.Lock()
	defer c.Hub.mu.Unlock()

	// Acquire client-local lock after hub-global lock to establish a
	// consistent total lock order (hub.mu -> client.mu) matching Unregister.
	c.mu.Lock()
	c.Rooms[room] = true
	c.mu.Unlock()

	if c.Hub.Rooms[room] == nil {
		c.Hub.Rooms[room] = make(map[*Client]bool)
	}
	c.Hub.Rooms[room][c] = true

	c.Hub.Logger.Debug("Client joined room", zap.String("client", c.ID), zap.String("room", room))
}

func (c *Client) LeaveRoom(room string) {
	if room == "" {
		return
	}

	c.Hub.mu.Lock()
	defer c.Hub.mu.Unlock()

	// Same lock order as JoinRoom: hub.mu before client.mu.
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
