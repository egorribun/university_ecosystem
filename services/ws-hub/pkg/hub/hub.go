package hub

import (
	"context"
	"encoding/json"
	"sync"

	"github.com/nats-io/nats.go"
	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/propagation"
	"go.opentelemetry.io/otel/trace"
	"go.uber.org/zap"
)

type Message struct {
	Type    string          `json:"type"`
	Room    string          `json:"room,omitempty"`
	Payload json.RawMessage `json:"payload"`
	From    string          `json:"from,omitempty"`
	To      string          `json:"to,omitempty"`
}

type Hub struct {
	Clients    map[string]*Client
	Rooms      map[string]map[*Client]bool
	Register   chan *Client
	Unregister chan *Client
	Broadcast  chan *Message
	Nats       *nats.Conn
	Logger     *zap.Logger
	mu         sync.RWMutex
	// authClient authorizes room-join requests against the Python backend.
	// If nil, all room-join attempts are denied (fail-closed).
	authClient RoomAuthClient
}

func NewHub(nc *nats.Conn, logger *zap.Logger, authClient RoomAuthClient) *Hub {
	return &Hub{
		Clients:    make(map[string]*Client),
		Rooms:      make(map[string]map[*Client]bool),
		Register:   make(chan *Client),
		Unregister: make(chan *Client),
		Broadcast:  make(chan *Message, 4096), // sized for NATS burst peaks
		Nats:       nc,
		Logger:     logger,
		authClient: authClient,
	}
}

func (h *Hub) Run() {
	for {
		select {
		case client := <-h.Register:
			h.mu.Lock()
			h.Clients[client.ID] = client
			h.mu.Unlock()
			h.Logger.Info("Client connected", zap.String("id", client.ID))

		case client := <-h.Unregister:
			h.mu.Lock()
			if _, ok := h.Clients[client.ID]; ok {
				delete(h.Clients, client.ID)
				close(client.Send)

				client.mu.Lock()
				for room := range client.Rooms {
					if clients, ok := h.Rooms[room]; ok {
						delete(clients, client)
						if len(clients) == 0 {
							delete(h.Rooms, room)
						}
					}
				}
				client.mu.Unlock()
			}
			h.mu.Unlock()
			h.Logger.Info("Client disconnected", zap.String("id", client.ID))

		case msg := <-h.Broadcast:
			h.broadcastMessage(msg)
		}
	}
}

func (h *Hub) broadcastMessage(msg *Message) {
	tr := otel.Tracer("hub")
	_, span := tr.Start(context.Background(), "Hub.broadcastMessage",
		trace.WithAttributes(
			attribute.String("msg.type", msg.Type),
			attribute.String("msg.room", msg.Room),
			attribute.String("msg.to", msg.To),
		),
	)
	defer span.End()

	data, _ := json.Marshal(msg)

	h.mu.RLock()
	defer h.mu.RUnlock()

	var recipientCount int
	if msg.Room != "" {
		if clients, ok := h.Rooms[msg.Room]; ok {
			recipientCount = len(clients)
			span.SetAttributes(attribute.Int("recipient.count", recipientCount))
			for client := range clients {
				select {
				case client.Send <- data:
				default:
				}
			}
		}
	} else if msg.To != "" {
		if client, ok := h.Clients[msg.To]; ok {
			recipientCount = 1
			span.SetAttributes(attribute.Int("recipient.count", recipientCount))
			select {
			case client.Send <- data:
			default:
			}
		}
	} else {
		recipientCount = len(h.Clients)
		span.SetAttributes(attribute.Int("recipient.count", recipientCount))
		for _, client := range h.Clients {
			select {
			case client.Send <- data:
			default:
				// Client's send buffer is full — evict via the Unregister channel.
				// The Unregister handler holds hub.mu.Lock() exclusively and is the
				// sole owner responsible for close(client.Send). WritePump detects
				// the closed channel and exits cleanly, then closes Conn.
				// Calling Conn.Close() here would race with WritePump — do NOT do it.
				h.Logger.Warn("Client buffer full, evicting", zap.String("id", client.ID))
				go func(c *Client) { h.Unregister <- c }(client)
			}
		}
	}
}

func (h *Hub) SubscribeToNATS() {
	_, _ = h.Nats.Subscribe("chat.>", func(msg *nats.Msg) {
		// Attempt to extract context from NATS message headers if present
		ctx := otel.GetTextMapPropagator().Extract(context.Background(), propagation.HeaderCarrier(msg.Header))
		_, span := otel.Tracer("hub").Start(ctx, "NATS.Subscribe.Chat")
		defer span.End()

		var wsMsg Message
		if err := json.Unmarshal(msg.Data, &wsMsg); err == nil {
			// Non-blocking push: if the Broadcast channel is full we drop
			// the message rather than blocking the NATS subscriber goroutine.
			// A blocked subscriber would exceed NATS MaxPending and close
			// the subscription, causing a full WebSocket service outage.
			select {
			case h.Broadcast <- &wsMsg:
			default:
				h.Logger.Warn("Broadcast channel full, dropping NATS chat message",
					zap.String("subject", msg.Subject))
			}
		}
	})

	_, _ = h.Nats.Subscribe("notifications.>", func(msg *nats.Msg) {
		ctx := otel.GetTextMapPropagator().Extract(context.Background(), propagation.HeaderCarrier(msg.Header))
		_, span := otel.Tracer("hub").Start(ctx, "NATS.Subscribe.Notifications")
		defer span.End()

		var wsMsg Message
		if err := json.Unmarshal(msg.Data, &wsMsg); err == nil {
			wsMsg.Type = "notification"
			select {
			case h.Broadcast <- &wsMsg:
			default:
				h.Logger.Warn("Broadcast channel full, dropping NATS notification",
					zap.String("subject", msg.Subject))
			}
		}
	})

	h.Logger.Info("Subscribed to NATS topics")
}

// AuthorizeRoomJoin verifies that userID is a participant of the given room
// by delegating to the configured RoomAuthClient.
// Fails closed: returns false when no client is configured or the check fails.
func (h *Hub) AuthorizeRoomJoin(userID, room string) bool {
	if h.authClient == nil {
		// No auth client configured — deny by default (fail-closed).
		h.Logger.Warn("AuthorizeRoomJoin: no auth client configured, denying",
			zap.String("user", userID), zap.String("room", room))
		return false
	}
	return h.authClient.CanJoinRoom(userID, room)
}
