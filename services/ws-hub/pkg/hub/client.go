package hub

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"net"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/google/uuid"
	"github.com/gorilla/websocket"
	"github.com/nats-io/nats.go"
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

func getOrCreateChEntry(ch chan []byte) *chEntry {
	chMu.Lock()
	defer chMu.Unlock()
	entry, ok := chMutexes[ch]
	if !ok {
		entry = &chEntry{}
		chMutexes[ch] = entry
	}
	return entry
}

// safeSend writes data to ch without panicking if the channel is already closed.
func safeSend(ch chan []byte, data []byte) (sent bool) {
	if ch == nil {
		return false
	}
	entry := getOrCreateChEntry(ch)

	entry.mu.Lock()
	defer entry.mu.Unlock()

	if entry.closed {
		return false
	}

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
	if ch == nil {
		return
	}
	chMu.Lock()
	entry, ok := chMutexes[ch]
	if !ok {
		entry = &chEntry{}
	} else {
		delete(chMutexes, ch)
	}
	chMu.Unlock()

	entry.mu.Lock()
	defer entry.mu.Unlock()

	if entry.closed {
		return
	}
	entry.closed = true

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

func (c *Client) cleanupReadPump() {
	c.cancel()
	c.Hub.msgLimiters.Delete(c.ID)
	if c.Hub != nil {
		hCtx := c.Hub.Context()
		if hCtx != nil {
			select {
			case c.Hub.Unregister <- c:
			case <-hCtx.Done():
				c.closeOnce.Do(func() { safeClose(c.Send) })
			}
		} else {
			select {
			case c.Hub.Unregister <- c:
			default:
				c.closeOnce.Do(func() { safeClose(c.Send) })
			}
		}
	}
	if c.Conn != nil {
		if err := c.Conn.Close(); err != nil {
			c.Hub.Logger.ErrorContext(c.ctx, "Failed to close session connection", "client_id", c.ID, "err", err)
		}
	}
}

func (c *Client) setupConnection() {
	if c.Conn == nil {
		return
	}
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

func (c *Client) processNextMessage() bool {
	_, data, err := c.Conn.ReadMessage()
	if err != nil {
		if isNormalCloseError(err) {
			c.Hub.Logger.DebugContext(c.ctx, "Session closed normally", "client_id", c.ID)
		} else {
			c.Hub.Logger.WarnContext(c.ctx, "Session read error",
				"client_id", c.ID,
				"err", err)
		}
		return false
	}

	var msg Message
	if err := json.Unmarshal(data, &msg); err != nil {
		return true
	}

	// MOD-27-02: Validate message type at parse boundary
	if !isAllowedMessageType(msg.Type) {
		UnknownMsgTypeTotal.Inc()
		return true
	}

	msg.From = c.ID
	c.handleIncomingMessage(msg, data)
	return true
}

// ReadPump pumps messages from the session connection to the hub.
func (c *Client) ReadPump() {
	defer c.cleanupReadPump()
	c.setupConnection()

	for c.Conn != nil {
		if !c.processNextMessage() {
			break
		}
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

type joinPayload struct {
	LastSeq   uint64 `json:"last_seq,omitempty"`
	LastMsgID string `json:"last_msg_id,omitempty"`
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

	lastSeq := msg.LastSeq
	lastMsgID := msg.LastMsgID
	if len(msg.Payload) > 0 {
		var jp joinPayload
		if err := json.Unmarshal(msg.Payload, &jp); err == nil {
			if lastSeq == 0 {
				lastSeq = jp.LastSeq
			}
			if lastMsgID == "" {
				lastMsgID = jp.LastMsgID
			}
		}
	}

	if (lastSeq > 0 || lastMsgID != "") && c.Hub != nil && c.Hub.js != nil {
		go c.replayOfflineMessages(msg.Room, lastSeq, lastMsgID)
	}
}

//nolint:gocognit,cyclop
func (c *Client) replayOfflineMessages(room string, lastSeq uint64, lastMsgID string) {
	if c.Hub == nil || c.Hub.js == nil {
		return
	}
	js := c.Hub.js

	var opts []nats.SubOpt
	streamName := c.Hub.streamChat
	if streamName == "" {
		streamName = "CHAT_EVENTS"
	}
	opts = append(opts, nats.BindStream(streamName))

	if lastSeq > 0 {
		opts = append(opts, nats.StartSequence(lastSeq+1))
	} else if lastMsgID != "" {
		if parsedSeq, err := strconv.ParseUint(lastMsgID, 10, 64); err == nil && parsedSeq > 0 {
			opts = append(opts, nats.StartSequence(parsedSeq+1))
		} else {
			opts = append(opts, nats.DeliverAll())
		}
	}

	sub, err := js.PullSubscribe("chat."+room, "", opts...)
	if err != nil {
		c.Hub.Logger.DebugContext(c.ctx, "Failed to create pull subscription for offline replay",
			"room", room, "err", err)
		return
	}
	defer func() {
		if err := sub.Unsubscribe(); err != nil && c.Hub != nil && c.Hub.Logger != nil {
			c.Hub.Logger.DebugContext(c.ctx, "Failed to unsubscribe NATS pull sub", "err", err)
		}
	}()

	msgs, err := sub.Fetch(100, nats.MaxWait(1*time.Second))
	if err != nil {
		if !errors.Is(err, nats.ErrTimeout) {
			c.Hub.Logger.DebugContext(c.ctx, "Pull fetch for offline replay returned error",
				"room", room, "err", err)
		}
		return
	}

	foundLastMsgID := (lastMsgID == "" || lastSeq > 0)
	for _, m := range msgs {
		select {
		case <-c.ctx.Done():
			return
		default:
		}

		if err := m.Ack(); err != nil && c.Hub != nil && c.Hub.Logger != nil {
			c.Hub.Logger.DebugContext(c.ctx, "Failed to ack NATS message", "err", err)
		}
		msgID := ""
		if m.Header != nil {
			msgID = m.Header.Get("Nats-Msg-Id")
		}
		if !foundLastMsgID {
			if msgID == lastMsgID {
				foundLastMsgID = true
			}
			continue
		}

		JetStreamReplayedTotal.Inc()

		var raw map[string]any
		if err := json.Unmarshal(m.Data, &raw); err == nil {
			if meta, err := m.Metadata(); err == nil {
				raw["seq"] = meta.Sequence.Stream
			}
			raw["replayed"] = true
			if data, err := json.Marshal(raw); err == nil {
				safeSend(c.Send, data)
				continue
			}
		}
		safeSend(c.Send, m.Data)
	}
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

//nolint:cyclop
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

	if c.Hub == nil || c.Hub.Nats == nil {
		return
	}

	msgID := uuid.New().String()
	natsMsg := &nats.Msg{
		Subject: "chat." + msg.Room,
		Data:    data,
		Header:  make(nats.Header),
	}
	natsMsg.Header.Set("Nats-Msg-Id", msgID)

	if c.Hub.enableJetStream && c.Hub.js != nil {
		if _, err := c.Hub.js.PublishMsgAsync(natsMsg); err != nil {
			if c.Hub.Logger != nil {
				c.Hub.Logger.ErrorContext(c.ctx, "Failed to publish async to JetStream", "err", err)
			}
		}
	} else {
		if err := c.Hub.Nats.PublishMsg(natsMsg); err != nil {
			if c.Hub.Logger != nil {
				c.Hub.Logger.ErrorContext(c.ctx, "Failed to publish to NATS", "err", err)
			}
		}
	}
}

// WritePump pumps messages from the hub to the session connection.
//
//nolint:gocognit,cyclop
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

// Disconnect sends a WebSocket close control frame with the specified close code and reason,
// then enqueues the client into Hub.Unregister for clean channel/room teardown.
func (c *Client) Disconnect(closeCode int, reason string) {
	if c.Conn != nil {
		closeMsg := websocket.FormatCloseMessage(closeCode, reason)
		if err := c.Conn.SetWriteDeadline(time.Now().Add(5 * time.Second)); err != nil && c.Hub != nil && c.Hub.Logger != nil {
			c.Hub.Logger.DebugContext(c.ctx, "Failed to set write deadline on disconnect", "err", err)
		}
		if err := c.Conn.WriteMessage(websocket.CloseMessage, closeMsg); err != nil {
			if c.Hub != nil && c.Hub.Logger != nil {
				c.Hub.Logger.WarnContext(c.ctx, "Failed to write close control frame to client",
					"client_id", c.ID, "user_id", c.UserID, "err", err)
			}
		}
	}

	if c.Hub != nil {
		hCtx := c.Hub.Context()
		if hCtx != nil {
			select {
			case c.Hub.Unregister <- c:
			case <-hCtx.Done():
				c.closeOnce.Do(func() { safeClose(c.Send) })
			}
		} else {
			select {
			case c.Hub.Unregister <- c:
			default:
				c.closeOnce.Do(func() { safeClose(c.Send) })
			}
		}
	}
}
