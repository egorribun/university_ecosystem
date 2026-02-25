package hub

import (
	"context"
	"encoding/json"
	"fmt"
	"sync"
	"time"

	"github.com/lestrrat-go/jwx/v2/jwk"
	"github.com/nats-io/nats.go"
	"github.com/university-ecosystem/ws-hub/pkg/config"
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
	// subs holds active NATS subscriptions for graceful Drain on shutdown.
	subs []*nats.Subscription
	// UpgradeLimiter caps per-IP WebSocket upgrade attempts. (RZ-2)
	UpgradeLimiter *WSUpgradeRateLimiter
	// jwksCache stores public keys fetched via MOD-1 / JWKS URL.
	jwksCache *jwk.Cache
	// jwksURL is the URL registered with jwksCache; used to retrieve the key set.
	jwksURL string
}

func NewHub(nc *nats.Conn, logger *zap.Logger, authClient RoomAuthClient, cfg *config.Config) *Hub {
	return &Hub{
		Clients:        make(map[string]*Client),
		Rooms:          make(map[string]map[*Client]bool),
		Register:       make(chan *Client),
		Unregister:     make(chan *Client),
		Broadcast:      make(chan *Message, cfg.BroadcastBufferSize),
		Nats:           nc,
		Logger:         logger,
		authClient:     authClient,
		// 10 upgrade attempts per 60-second window per IP.
		// At ~1 KB/handshake this limits the surface area for JWT-brute-force
		// DDoS without affecting legitimate reconnect scenarios.
		UpgradeLimiter: NewWSUpgradeRateLimiter(10, 60),
		jwksCache:      nil, // Initialised via SetupJWKS()
	}
}

// SetupJWKS initialises the JWKS cache for RS256 token verification.
// It fetches public keys from jwksURL and refreshes them periodically. (MOD-1)
func (h *Hub) SetupJWKS(ctx context.Context, jwksURL string) error {
	if jwksURL == "" {
		return nil
	}

	h.jwksCache = jwk.NewCache(ctx)
	// Refresh the cache every hour.
	err := h.jwksCache.Register(jwksURL, jwk.WithMinRefreshInterval(time.Hour))
	if err != nil {
		return fmt.Errorf("failed to register JWKS URL %s: %w", jwksURL, err)
	}
	// Store the URL so ValidateToken can retrieve the correct key set.
	h.jwksURL = jwksURL

	// Initial fetch to ensure we have keys at startup.
	_, err = h.jwksCache.Refresh(ctx, jwksURL)
	if err != nil {
		h.Logger.Warn("Initial JWKS fetch failed; will retry in background", zap.Error(err))
	}

	h.Logger.Info("JWKS cache initialised", zap.String("url", jwksURL))
	return nil
}

// Run starts the hub's main select loop.
//
// The loop is terminated when ctx is cancelled, enabling clean goroutine
// shutdown without leaking the goroutine after SIGTERM. Callers should
// pass the application-level context so the hub stops alongside the server.
func (h *Hub) Run(ctx context.Context) {
	for {
		select {
		case <-ctx.Done():
			// Application shutdown: exit the loop so the goroutine is reclaimed.
			h.Logger.Info("Hub.Run: context cancelled, stopping loop")
			return

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

	// PERF-3: snapshot recipients under the read lock, then release
	// the lock before writing to channels.
	//
	// Holding RLock for the entire send loop forces every Register/Unregister
	// (which need the write lock) to queue behind ALL channel writes — O(N)
	// critical section under contention.  Snapshotting first reduces the lock
	// hold time to O(1) (just map iteration + slice append), making channel
	// writes contention-free.
	type recipient struct {
		client   *Client
		evictOnFull bool // true only for global broadcast where we auto-evict
	}
	var recipients []recipient

	h.mu.RLock()
	if msg.Room != "" {
		if clients, ok := h.Rooms[msg.Room]; ok {
			span.SetAttributes(attribute.Int("recipient.count", len(clients)))
			for c := range clients {
				recipients = append(recipients, recipient{client: c})
			}
		}
	} else if msg.To != "" {
		if c, ok := h.Clients[msg.To]; ok {
			span.SetAttributes(attribute.Int("recipient.count", 1))
			recipients = append(recipients, recipient{client: c})
		}
	} else {
		// Global broadcast — evict slow consumers.
		span.SetAttributes(attribute.Int("recipient.count", len(h.Clients)))
		for _, c := range h.Clients {
			recipients = append(recipients, recipient{client: c, evictOnFull: true})
		}
	}
	h.mu.RUnlock() // released before any channel writes

	// Fan-out happens outside the lock — Register/Unregister can now proceed
	// concurrently without blocking on our channel writes.
	for _, r := range recipients {
		select {
		case r.client.Send <- data:
		default:
			if r.evictOnFull {
				// Buffer full: schedule eviction via the Unregister channel.
				// Unregister handler is the sole owner of close(client.Send).
				h.Logger.Warn("Client buffer full, evicting", zap.String("id", r.client.ID))
				go func(c *Client) { h.Unregister <- c }(r.client)
			}
			// For room/direct messages, silently drop — the client has an
			// application-level reconnect mechanism.
		}
	}
}

// SubscribeToNATS registers NATS subscriptions and stores them for graceful
// shutdown via Stop().  Fatals on subscription error (RZ-4): a hub that
// cannot receive NATS messages delivers no messages — better to fail loudly
// at startup than silently serve a broken system.
func (h *Hub) SubscribeToNATS() {
	chatSub, err := h.Nats.Subscribe("chat.>", func(msg *nats.Msg) {
		// Attempt to extract trace context from NATS message headers if present.
		ctx := otel.GetTextMapPropagator().Extract(context.Background(), propagation.HeaderCarrier(msg.Header))
		_, span := otel.Tracer("hub").Start(ctx, "NATS.Subscribe.Chat")
		defer span.End()

		var wsMsg Message
		if err := json.Unmarshal(msg.Data, &wsMsg); err == nil {
			// Non-blocking push: dropping here is safer than blocking the NATS
			// subscriber goroutine (blocked goroutine → MaxPending exceeded → sub closed).
			select {
			case h.Broadcast <- &wsMsg:
			default:
				h.Logger.Warn("Broadcast channel full, dropping NATS chat message",
					zap.String("subject", msg.Subject))
			}
		}
	})
	if err != nil {
		h.Logger.Fatal("NATS chat subscription failed — hub cannot deliver messages",
			zap.Error(err))
	}
	h.subs = append(h.subs, chatSub)

	notifSub, err := h.Nats.Subscribe("notifications.>", func(msg *nats.Msg) {
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
	if err != nil {
		h.Logger.Fatal("NATS notifications subscription failed — hub cannot deliver messages",
			zap.Error(err))
	}
	h.subs = append(h.subs, notifSub)

	h.Logger.Info("Subscribed to NATS topics")
}

// Stop drains all NATS subscriptions (flushing in-flight messages) and
// stops the per-IP upgrade rate limiter GC goroutine.  Call this from
// the application shutdown path before closing the NATS connection.
func (h *Hub) Stop() {
	for _, sub := range h.subs {
		if err := sub.Drain(); err != nil {
			h.Logger.Warn("NATS subscription drain error", zap.Error(err))
		}
	}
	if h.UpgradeLimiter != nil {
		h.UpgradeLimiter.Stop()
	}
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
