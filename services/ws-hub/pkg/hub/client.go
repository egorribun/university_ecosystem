package hub

import (
	"encoding/json"
	"sync"
	"time"

	"github.com/gorilla/websocket"
	"go.uber.org/zap"
)

type Client struct {
	ID     string
	UserID string
	Conn   *websocket.Conn
	Rooms  map[string]bool
	Send   chan []byte
	Hub    *Hub
	mu     sync.Mutex
}

func (c *Client) ReadPump() {
	defer func() {
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
			if !c.Hub.AuthorizeRoomJoin(c.UserID, msg.Room) {
				c.Hub.Logger.Warn("Unauthorized room join rejected",
					zap.String("user", c.UserID),
					zap.String("room", msg.Room))
				break
			}
			c.JoinRoom(msg.Room)
		case "leave":
			c.LeaveRoom(msg.Room)
		case "message":
			if js, err := c.Hub.Nats.JetStream(); err == nil {
				_, _ = js.PublishAsync("chat."+msg.Room, data)
			} else {
				c.Hub.Logger.Error("Failed to init JetStream, falling back to core NATS", zap.Error(err))
				_ = c.Hub.Nats.Publish("chat."+msg.Room, data)
			}
			c.Hub.Broadcast <- &msg
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
