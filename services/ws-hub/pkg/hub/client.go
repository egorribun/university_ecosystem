package hub

import (
	"context"
	"encoding/json"
	"sync"
	"time"

	"github.com/gorilla/websocket"
	"golang.org/x/time/rate"
)

// Client represents a connected WebSocket user.
type Client struct {
	ID        string
	UserID    string
	Conn      *websocket.Conn
	Rooms     map[string]bool
	Send      chan []byte
	Hub       *Hub
	mu        sync.Mutex
	closeOnce sync.Once
	// ctx / cancel are tied to this connection's lifetime.
	ctx    context.Context
	cancel context.CancelFunc
}

// safeSend writes data to ch without panicking if the channel is already
// closed.
func safeSend(ch chan []byte, data []byte) (sent bool) {
	defer func() {
		if r := recover(); r != nil {
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

// ReadPump pumps messages from the websocket connection to the hub.
func (c *Client) ReadPump() {
	defer func() {
		c.cancel()
		c.Hub.msgLimiters.Delete(c.ID)
		// RZ-W19-16: use select to avoid goroutine leak if Run() has already exited
		select {
		case c.Hub.Unregister <- c:
		case <-c.Hub.ctx.Done():
			c.closeOnce.Do(func() { close(c.Send) })
		}
		if err := c.Conn.Close(); err != nil {
			c.Hub.Logger.ErrorContext(c.ctx, "Failed to close websocket connection", "client_id", c.ID, "err", err)
		}
	}()

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

	for {
		_, data, err := c.Conn.ReadMessage()
		if err != nil {
			if websocket.IsCloseError(err,
				websocket.CloseNormalClosure,
				websocket.CloseGoingAway,
				websocket.CloseNoStatusReceived) {
				c.Hub.Logger.DebugContext(c.ctx, "WebSocket closed normally", "client_id", c.ID)
			} else {
				c.Hub.Logger.WarnContext(c.ctx, "WebSocket read error",
					"client_id", c.ID,
					"err", err)
			}
			break
		}

		var msg Message
		if err := json.Unmarshal(data, &msg); err != nil {
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

func (c *Client) handleMessage(msg Message, data []byte) {
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

// WritePump pumps messages from the hub to the websocket connection.
func (c *Client) WritePump() {
	ticker := time.NewTicker(30 * time.Second)
	defer func() {
		ticker.Stop()
		if err := c.Conn.Close(); err != nil {
			c.Hub.Logger.ErrorContext(c.ctx, "Failed to close websocket connection In WritePump", "err", err)
		}
	}()

	for {
		select {
		case msg, ok := <-c.Send:
			if err := c.Conn.SetWriteDeadline(time.Now().Add(10 * time.Second)); err != nil {
				c.Hub.Logger.ErrorContext(c.ctx, "Failed to set write deadline", "err", err)
			}
			if !ok {
				if err := c.Conn.WriteMessage(websocket.CloseMessage, []byte{}); err != nil {
					c.Hub.Logger.ErrorContext(c.ctx, "Failed to write close message", "err", err)
				}
				return
			}

			if err := c.Conn.WriteMessage(websocket.TextMessage, msg); err != nil {
				return
			}

		case <-ticker.C:
			if err := c.Conn.SetWriteDeadline(time.Now().Add(10 * time.Second)); err != nil {
				c.Hub.Logger.ErrorContext(c.ctx, "Failed to set write deadline for ping", "err", err)
			}
			if err := c.Conn.WriteMessage(websocket.PingMessage, nil); err != nil {
				return
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
