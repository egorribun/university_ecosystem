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
}

func NewHub(nc *nats.Conn, logger *zap.Logger) *Hub {
	return &Hub{
		Clients:    make(map[string]*Client),
		Rooms:      make(map[string]map[*Client]bool),
		Register:   make(chan *Client),
		Unregister: make(chan *Client),
		Broadcast:  make(chan *Message, 256),
		Nats:       nc,
		Logger:     logger,
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
				h.Logger.Warn("Client buffer full, dropping client", zap.String("id", client.ID))
				go func(c *Client) {
					c.Hub.Unregister <- c
					_ = c.Conn.Close()
				}(client)
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
			h.Broadcast <- &wsMsg
		}
	})

	_, _ = h.Nats.Subscribe("notifications.>", func(msg *nats.Msg) {
		ctx := otel.GetTextMapPropagator().Extract(context.Background(), propagation.HeaderCarrier(msg.Header))
		_, span := otel.Tracer("hub").Start(ctx, "NATS.Subscribe.Notifications")
		defer span.End()

		var wsMsg Message
		if err := json.Unmarshal(msg.Data, &wsMsg); err == nil {
			wsMsg.Type = "notification"
			h.Broadcast <- &wsMsg
		}
	})

	h.Logger.Info("Subscribed to NATS topics")
}
