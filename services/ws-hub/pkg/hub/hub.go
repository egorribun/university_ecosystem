package hub

import (
	"context"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"sync"
	"time"

	"log/slog"
	"os"

	"github.com/lestrrat-go/jwx/v2/jwk"
	"github.com/nats-io/nats.go"
	"github.com/university-ecosystem/ws-hub/pkg/config"
	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/propagation"
	"go.opentelemetry.io/otel/trace"

	// MOD-02 (audit Wave 10): semconv v1.27.0 adds messaging.* attributes for
	// NATS subjects, enabling correlation in Jaeger/Grafana Tempo.
	semconv "go.opentelemetry.io/otel/semconv/v1.27.0"
)

// Message represents a WebSocket message.
type Message struct {
	Type    string          `json:"type"`
	Room    string          `json:"room,omitempty"`
	Payload json.RawMessage `json:"payload"`
	From    string          `json:"from,omitempty"`
	To      string          `json:"to,omitempty"`
	// TraceCtx carries the W3C traceparent/tracestate from the NATS publisher.
	TraceCtx map[string]string `json:"trace_ctx,omitempty"`
}

// Hub maintains the set of active clients and broadcasts messages.
type Hub struct {
	Clients    map[string]*Client
	Rooms      map[string]map[*Client]bool
	Register   chan *Client
	Unregister chan *Client
	Broadcast  chan *Message
	Nats       *nats.Conn
	Logger     *slog.Logger
	mu         sync.RWMutex
	authClient RoomAuthClient
	subs       []*nats.Subscription
	// UpgradeLimiter caps per-IP WebSocket upgrade attempts.
	UpgradeLimiter  *WSUpgradeRateLimiter
	jwksCache       *jwk.Cache
	jwksCacheCancel context.CancelFunc
	jwksURL         string
	// maxClients caps the number of concurrently connected WebSocket clients.
	maxClients int
	// internalSecret is the shared secret for local HMAC validation.
	internalSecret string
	// msgLimiters is a per-client token-bucket map that limits NATS publish rate.
	msgLimiters sync.Map // map[clientID string]*rate.Limiter
	stopOnce    sync.Once
	jwksMu      sync.Mutex
}

// NewHub creates a new Hub instance.
func NewHub(nc *nats.Conn, logger *slog.Logger, authClient RoomAuthClient, cfg *config.Config) *Hub {
	return &Hub{
		Clients:    make(map[string]*Client),
		Rooms:      make(map[string]map[*Client]bool),
		Register:   make(chan *Client),
		Unregister: make(chan *Client),
		Broadcast:  make(chan *Message, cfg.BroadcastBufferSize),
		Nats:       nc,
		Logger:     logger,
		authClient: authClient,
		// 10 upgrade attempts per 60-second window per IP.
		UpgradeLimiter: NewWSUpgradeRateLimiter(10, 60),
		jwksCache:      nil, // Initialised via SetupJWKS()
		maxClients:     cfg.MaxClients,
		internalSecret: cfg.InternalSecret,
	}
}

// SetupJWKS initialises the JWKS cache for RS256 token verification.
func (h *Hub) SetupJWKS(ctx context.Context, jwksURL string) error {
	if jwksURL == "" {
		return nil
	}

	h.jwksMu.Lock()
	defer h.jwksMu.Unlock()

	if h.jwksCacheCancel != nil {
		h.jwksCacheCancel()
		h.jwksCacheCancel = nil
	}

	jwksCtx, cancel := context.WithCancel(ctx)
	h.jwksCacheCancel = cancel

	h.jwksCache = jwk.NewCache(jwksCtx)
	// Refresh the cache every hour.
	err := h.jwksCache.Register(jwksURL, jwk.WithMinRefreshInterval(time.Hour))
	if err != nil {
		cancel() // release context on error
		return fmt.Errorf("failed to register JWKS URL %s: %w", jwksURL, err)
	}
	h.jwksURL = jwksURL

	_, err = h.jwksCache.Refresh(jwksCtx, jwksURL)
	if err != nil {
		h.Logger.WarnContext(ctx, "Initial JWKS fetch failed; will retry in background", "err", err)
	}

	h.Logger.InfoContext(ctx, "JWKS cache initialised", "url", jwksURL)
	return nil
}

// Run starts the hub's main select loop.
func (h *Hub) Run(ctx context.Context) {
	for {
		select {
		case <-ctx.Done():
			h.Logger.InfoContext(ctx, "Hub.Run: context cancelled, stopping loop")
			return

		case client := <-h.Register:
			h.handleRegister(ctx, client)

		case client := <-h.Unregister:
			h.handleUnregister(ctx, client)

		case msg := <-h.Broadcast:
			h.broadcastMessage(ctx, msg)
		}
	}
}

func (h *Hub) handleRegister(ctx context.Context, client *Client) {
	h.mu.Lock()
	if h.maxClients > 0 && len(h.Clients) >= h.maxClients {
		h.mu.Unlock()
		h.Logger.WarnContext(ctx, "Max connections reached, rejecting client",
			"id", client.ID,
			"max", h.maxClients)
		client.closeOnce.Do(func() { close(client.Send) })
		if err := client.Conn.Close(); err != nil {
			h.Logger.ErrorContext(ctx, "Failed to close connection after max connections", "id", client.ID, "err", err)
		}
		return
	}
	h.Clients[client.ID] = client
	h.mu.Unlock()
	ActiveConnections.Inc()
	h.Logger.InfoContext(ctx, "Client connected", "id", client.ID)
}

func (h *Hub) handleUnregister(ctx context.Context, client *Client) {
	h.mu.Lock()
	if existingClient, ok := h.Clients[client.ID]; ok && existingClient == client {
		delete(h.Clients, client.ID)
	}
	h.mu.Unlock()

	client.closeOnce.Do(func() {
		close(client.Send)

		h.mu.Lock()
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
		h.mu.Unlock()
	})
	ActiveConnections.Dec()
	h.Logger.InfoContext(ctx, "Client disconnected", "id", client.ID)
}

func (h *Hub) broadcastMessage(parentCtx context.Context, msg *Message) {
	bctx := parentCtx
	if len(msg.TraceCtx) > 0 {
		bctx = otel.GetTextMapPropagator().Extract(parentCtx, propagation.MapCarrier(msg.TraceCtx))
	}

	tr := otel.Tracer("hub")
	_, span := tr.Start(bctx, "Hub.broadcastMessage",
		trace.WithAttributes(
			attribute.String("msg.type", msg.Type),
			attribute.String("msg.room", msg.Room),
			attribute.String("msg.to", msg.To),
		),
	)
	defer span.End()

	data, err := json.Marshal(msg)
	if err != nil {
		h.Logger.ErrorContext(bctx, "Failed to marshal broadcast message", "err", err)
		return
	}

	type recipient struct {
		client      *Client
		evictOnFull bool
	}

	h.mu.RLock()
	var recipients []recipient
	if msg.Room != "" {
		if clients, ok := h.Rooms[msg.Room]; ok {
			span.SetAttributes(attribute.Int("recipient.count", len(clients)))
			recipients = make([]recipient, 0, len(clients))
			for c := range clients {
				recipients = append(recipients, recipient{client: c})
			}
		}
	} else if msg.To != "" {
		if c, ok := h.Clients[msg.To]; ok {
			span.SetAttributes(attribute.Int("recipient.count", 1))
			recipients = make([]recipient, 0, 1)
			recipients = append(recipients, recipient{client: c})
		}
	} else {
		span.SetAttributes(attribute.Int("recipient.count", len(h.Clients)))
		recipients = make([]recipient, 0, len(h.Clients))
		for _, c := range h.Clients {
			recipients = append(recipients, recipient{client: c, evictOnFull: true})
		}
	}
	h.mu.RUnlock()

	for _, r := range recipients {
		if safeSend(r.client.Send, data) {
			MessagesDeliveredTotal.Inc()
		} else if r.evictOnFull {
			h.Logger.WarnContext(bctx, "Client buffer full or closed, evicting", "id", r.client.ID)
			go func(c *Client) { h.Unregister <- c }(r.client)
		}
	}
}

// SubscribeToNATS registers NATS subscriptions and stores them for graceful shutdown.
func (h *Hub) SubscribeToNATS(appCtx context.Context) {
	chatSub, err := h.Nats.Subscribe("chat.>", h.handleChat(appCtx))
	if err != nil {
		h.Logger.ErrorContext(appCtx, "NATS chat subscription failed — hub cannot deliver messages", "err", err)
		os.Exit(1)
	}
	h.subs = append(h.subs, chatSub)

	notifSub, err := h.Nats.Subscribe("notifications.>", h.handleNotifications(appCtx))
	if err != nil {
		h.Logger.ErrorContext(appCtx, "NATS notifications subscription failed — hub cannot deliver messages", "err", err)
		os.Exit(1)
	}
	h.subs = append(h.subs, notifSub)

	invSub, err := h.Nats.Subscribe("cache.invalidate", h.handleCacheInvalidation(appCtx))
	if err != nil {
		h.Logger.ErrorContext(appCtx, "NATS cache invalidation subscription failed", "err", err)
		os.Exit(1)
	}
	h.subs = append(h.subs, invSub)

	h.Logger.InfoContext(appCtx, "Subscribed to NATS topics")
}

func (h *Hub) handleChat(appCtx context.Context) nats.MsgHandler {
	const natsCallbackTimeout = 30 * time.Second
	return func(msg *nats.Msg) {
		defer func() {
			if r := recover(); r != nil {
				h.Logger.ErrorContext(appCtx, "NATS chat callback panic recovered",
					"panic", r, "subject", msg.Subject)
			}
		}()

		select {
		case <-appCtx.Done():
			return
		default:
		}

		msgCtx, cancel := context.WithTimeout(appCtx, natsCallbackTimeout)
		defer cancel()
		msgCtx = otel.GetTextMapPropagator().Extract(msgCtx, propagation.HeaderCarrier(msg.Header))
		_, span := otel.Tracer("hub").Start(msgCtx, "NATS.Subscribe.Chat",
			trace.WithAttributes(
				semconv.MessagingSystemKey.String("nats"),
				semconv.MessagingOperationTypeKey.String("receive"),
				semconv.MessagingDestinationNameKey.String("chat.*"),
			),
		)
		defer span.End()

		var wsMsg Message
		if err := json.Unmarshal(msg.Data, &wsMsg); err != nil {
			h.Logger.WarnContext(msgCtx, "ws-hub: malformed NATS chat message dropped",
				"subject", msg.Subject, "size", len(msg.Data), "err", err)
			return
		}
		select {
		case h.Broadcast <- &wsMsg:
		default:
			h.Logger.WarnContext(msgCtx, "Broadcast channel full, dropping NATS chat message",
				"subject", msg.Subject)
		}
	}
}

func (h *Hub) handleNotifications(appCtx context.Context) nats.MsgHandler {
	const natsCallbackTimeout = 30 * time.Second
	return func(msg *nats.Msg) {
		defer func() {
			if r := recover(); r != nil {
				h.Logger.ErrorContext(appCtx, "NATS notifications callback panic recovered",
					"panic", r, "subject", msg.Subject)
			}
		}()

		select {
		case <-appCtx.Done():
			return
		default:
		}

		msgCtx, cancel := context.WithTimeout(appCtx, natsCallbackTimeout)
		defer cancel()
		msgCtx = otel.GetTextMapPropagator().Extract(msgCtx, propagation.HeaderCarrier(msg.Header))
		_, span := otel.Tracer("hub").Start(msgCtx, "NATS.Subscribe.Notifications",
			trace.WithAttributes(
				semconv.MessagingSystemKey.String("nats"),
				semconv.MessagingOperationTypeKey.String("receive"),
				semconv.MessagingDestinationNameKey.String("notifications.*"),
			),
		)
		defer span.End()

		var wsMsg Message
		if err := json.Unmarshal(msg.Data, &wsMsg); err != nil {
			h.Logger.WarnContext(msgCtx, "ws-hub: malformed NATS notification dropped",
				"subject", msg.Subject, "size", len(msg.Data), "err", err)
			return
		}
		wsMsg.Type = "notification"
		select {
		case h.Broadcast <- &wsMsg:
		default:
			h.Logger.WarnContext(msgCtx, "Broadcast channel full, dropping NATS notification",
				"subject", msg.Subject)
		}
	}
}

func (h *Hub) handleCacheInvalidation(appCtx context.Context) nats.MsgHandler {
	const natsCallbackTimeout = 30 * time.Second
	return func(msg *nats.Msg) {
		defer func() {
			if r := recover(); r != nil {
				h.Logger.ErrorContext(appCtx, "NATS cache.invalidate callback panic recovered",
					"panic", r, "subject", msg.Subject)
			}
		}()

		select {
		case <-appCtx.Done():
			return
		default:
		}

		msgCtx, cancel := context.WithTimeout(appCtx, natsCallbackTimeout)
		defer cancel()
		msgCtx = otel.GetTextMapPropagator().Extract(msgCtx, propagation.HeaderCarrier(msg.Header))
		_, span := otel.Tracer("hub").Start(msgCtx, "NATS.Subscribe.CacheInvalidate",
			trace.WithAttributes(
				semconv.MessagingSystemKey.String("nats"),
				semconv.MessagingOperationTypeKey.String("receive"),
				semconv.MessagingDestinationNameKey.String("cache.invalidate"),
			),
		)
		defer span.End()

		var payload struct {
			Data struct {
				RoomID    string `json:"room_id"`
				Timestamp uint64 `json:"timestamp"`
				UserID    string `json:"user_id"`
			} `json:"data"`
			Signature string `json:"signature"`
		}

		if err := json.Unmarshal(msg.Data, &payload); err != nil {
			h.Logger.WarnContext(msgCtx, "ws-hub: malformed NATS cache.invalidate message dropped",
				"subject", msg.Subject, "size", len(msg.Data), "err", err)
			return
		}

		dataBytes, err := json.Marshal(payload.Data)
		if err != nil {
			h.Logger.ErrorContext(msgCtx, "Failed to marshal validation data", "err", err)
			return
		}

		hFunc := hmac.New(sha256.New, []byte(h.internalSecret))
		if _, err := hFunc.Write(dataBytes); err != nil {
			h.Logger.ErrorContext(msgCtx, "Failed to write data to HMAC", "err", err)
			return
		}
		expectedSigBytes := hFunc.Sum(nil)

		payloadSigBytes, decodeErr := hex.DecodeString(payload.Signature)
		if decodeErr != nil || !hmac.Equal(payloadSigBytes, expectedSigBytes) {
			h.Logger.WarnContext(msgCtx, "Invalid internal NATS signature — dropping event",
				"room_id", payload.Data.RoomID, "user_id", payload.Data.UserID)
			return
		}

		if h.authClient != nil {
			h.authClient.Invalidate(payload.Data.UserID, payload.Data.RoomID)
		}
	}
}

// StartLimiterCleanup launches a background goroutine that periodically
// removes orphaned rate.Limiter entries from msgLimiters.
func (h *Hub) StartLimiterCleanup(ctx context.Context) {
	go func() {
		defer func() {
			if r := recover(); r != nil {
				h.Logger.ErrorContext(ctx, "CRITICAL: Panic in LimiterCleanup goroutine avoided ws-hub crash", "panic", r)
			}
		}()
		ticker := time.NewTicker(5 * time.Minute)
		defer ticker.Stop()
		for {
			select {
			case <-ctx.Done():
				return
			case <-ticker.C:
				h.mu.RLock()
				active := make(map[string]struct{}, len(h.Clients))
				for id := range h.Clients {
					active[id] = struct{}{}
				}
				h.mu.RUnlock()

				var removed int
				h.msgLimiters.Range(func(key, _ any) bool {
					if _, ok := active[key.(string)]; !ok {
						h.msgLimiters.Delete(key)
						removed++
					}
					return true
				})
				if removed > 0 {
					h.Logger.InfoContext(ctx, "Cleaned up orphaned msgLimiters",
						"removed", removed)
				}
			}
		}
	}()
}

// Stop drains all NATS subscriptions (flushing in-flight messages).
func (h *Hub) Stop() {
	h.stopOnce.Do(func() {
		for _, sub := range h.subs {
			if err := sub.Drain(); err != nil {
				h.Logger.WarnContext(context.Background(), "NATS subscription drain error", "err", err)
			}
		}
		if h.UpgradeLimiter != nil {
			h.UpgradeLimiter.Stop()
		}
		h.jwksMu.Lock()
		if h.jwksCacheCancel != nil {
			h.jwksCacheCancel()
		}
		h.jwksMu.Unlock()
	})
}

// AuthorizeRoomJoin verifies that userID is a participant of the given room.
func (h *Hub) AuthorizeRoomJoin(ctx context.Context, userID, room string) bool {
	if h.authClient == nil {
		h.Logger.WarnContext(ctx, "AuthorizeRoomJoin: no auth client configured, denying",
			"user", userID, "room", room)
		return false
	}
	return h.authClient.CanJoinRoom(ctx, userID, room)
}
