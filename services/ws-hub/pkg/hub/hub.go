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

	lru "github.com/hashicorp/golang-lru/v2"
	"github.com/lestrrat-go/jwx/v2/jwk"
	"github.com/nats-io/nats.go"
	goredis "github.com/redis/go-redis/v9"
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
	Type      string            `json:"type"`
	Room      string            `json:"room,omitempty"`
	Payload   json.RawMessage   `json:"payload"`
	From      string            `json:"from,omitempty"`
	To        string            `json:"to,omitempty"`
	TraceCtx  map[string]string `json:"trace_ctx,omitempty"`
	LastSeq   uint64            `json:"last_seq,omitempty"`
	LastMsgID string            `json:"last_msg_id,omitempty"`
}

// LOCK HIERARCHY — RZ-22-04 (Wave 22 audit)
//
// Acquire locks in this exact order to prevent deadlock:
//   1. Hub.mu    (sync.RWMutex) — guards Clients and Rooms maps
//   2. Client.mu (sync.Mutex)   — guards per-client Rooms set
//
// NEVER acquire Hub.mu while holding Client.mu. Any code path that needs
// both locks MUST acquire Hub.mu first, then Client.mu.
// Violation will cause deadlock under concurrent JoinRoom/LeaveRoom/Unregister.

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
	// broadcastWorkers is the size of the broadcast goroutine pool (PERF-W14-02).
	broadcastWorkers int
	// internalSecret is the shared secret for local HMAC validation.
	internalSecret string
	// msgLimiters is a per-client token-bucket map that limits NATS publish rate.
	msgLimiters sync.Map // map[clientID string]*rate.Limiter
	// RZ-W18-01 (audit 2026-03-23 Wave 18): per-client message rate limit fields.
	// Previously accessed via c.Hub.Config which did not exist on the Hub struct.
	clientMsgRateLimit float64
	clientMsgRateBurst int
	// ctx is the lifecycle context for the Hub, cancelled when Run() exits.
	// Used by ReadPump/WritePump goroutines to detect hub shutdown (RZ-24-02).
	ctx         context.Context
	ctxCancel   context.CancelFunc
	lifecycleMu sync.Mutex
	stopOnce    sync.Once
	jwksMu      sync.Mutex
	// redisClient is the shared Redis connection used for upgrade ticket validation.
	// RZ-W14-01 (audit 2026-03-23 Wave 14): tickets replace JWT-in-Sec-WebSocket-Protocol.
	redisClient            *goredis.Client
	limiterCleanupInterval time.Duration

	// JetStream R1 fields
	js              nats.JetStreamContext
	dedupCache      *lru.Cache[string, time.Time]
	streamChat      string
	streamNotif     string
	durableChat     string
	durableNotif    string
	enableJetStream bool
}

// safeAck attempts to ACK a NATS message, suppressing nats.ErrNotJS for core/synthetic NATS messages.
func safeAck(msg *nats.Msg) {
	if msg == nil {
		return
	}
	err := msg.Ack()
	if err == nil {
		JetStreamAcksTotal.Inc()
	}
}

// safeNakWithDelay attempts to NAK a NATS message with delay, suppressing nats.ErrNotJS.
func safeNakWithDelay(msg *nats.Msg, delay time.Duration) {
	if msg == nil {
		return
	}
	err := msg.NakWithDelay(delay)
	if err == nil {
		JetStreamNaksTotal.Inc()
	}
}

// NewHub creates a new Hub instance.
func NewHub(nc *nats.Conn, logger *slog.Logger, authClient RoomAuthClient, cfg *config.Config, rdb *goredis.Client) *Hub {
	bufSize := 4096
	maxC := 10000
	workers := 4
	secret := ""
	rateLimit := 10.0
	rateBurst := 20
	streamChat := "CHAT_EVENTS"
	streamNotif := "NOTIFICATIONS_EVENTS"
	durableChat := "ws-hub-chat"
	durableNotif := "ws-hub-notifications"
	enableJS := true

	if cfg != nil {
		if cfg.BroadcastBufferSize > 0 {
			bufSize = cfg.BroadcastBufferSize
		}
		maxC = cfg.MaxClients
		workers = cfg.BroadcastWorkers
		secret = cfg.InternalSecret // #pragma: allowlist secret
		if cfg.ClientMsgRateLimit > 0 {
			rateLimit = cfg.ClientMsgRateLimit
		}
		if cfg.ClientMsgRateBurst > 0 {
			rateBurst = cfg.ClientMsgRateBurst
		}
		if cfg.NatsStreamChat != "" {
			streamChat = cfg.NatsStreamChat
		}
		if cfg.NatsStreamNotifications != "" {
			streamNotif = cfg.NatsStreamNotifications
		}
		if cfg.NatsDurableChat != "" {
			durableChat = cfg.NatsDurableChat
		}
		if cfg.NatsDurableNotifications != "" {
			durableNotif = cfg.NatsDurableNotifications
		}
		enableJS = cfg.EnableJetStream
	}

	dedupCache, err := lru.New[string, time.Time](10000)
	if err != nil && logger != nil {
		logger.Error("Failed to initialize dedup LRU cache", "err", err)
	}

	var js nats.JetStreamContext
	if nc != nil && enableJS {
		if jsc, err := nc.JetStream(); err == nil {
			js = jsc
		}
	}

	return &Hub{
		Clients:                make(map[string]*Client),
		Rooms:                  make(map[string]map[*Client]bool),
		Register:               make(chan *Client),
		Unregister:             make(chan *Client),
		Broadcast:              make(chan *Message, bufSize),
		Nats:                   nc,
		Logger:                 logger,
		authClient:             authClient,
		UpgradeLimiter:         NewWSUpgradeRateLimiter(10, 60),
		jwksCache:              nil, // Initialised via SetupJWKS()
		maxClients:             maxC,
		broadcastWorkers:       workers,
		internalSecret:         secret,
		clientMsgRateLimit:     rateLimit,
		clientMsgRateBurst:     rateBurst,
		redisClient:            rdb,
		limiterCleanupInterval: 5 * time.Minute,
		js:                     js,
		dedupCache:             dedupCache,
		streamChat:             streamChat,
		streamNotif:            streamNotif,
		durableChat:            durableChat,
		durableNotif:           durableNotif,
		enableJetStream:        enableJS,
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
//
// PERF-14-04 (audit Wave 14): Broadcast messages are dispatched to a worker
// pool so that JSON marshalling and per-recipient writes do not block the
// Register/Unregister channels.  broadcastMessage already acquires h.mu.RLock
// so concurrent broadcasts are safe.
//
// PERF-W14-02 (audit 2026-03-23 Wave 14): worker count is now read from
// h.broadcastWorkers (set from cfg.BroadcastWorkers / WS_BROADCAST_WORKERS
// env var, default 2×GOMAXPROCS) instead of the hard-coded constant 4.
func (h *Hub) Run(ctx context.Context) {
	runCtx, runCancel := context.WithCancel(ctx)
	h.lifecycleMu.Lock()
	h.ctx, h.ctxCancel = runCtx, runCancel
	h.lifecycleMu.Unlock()
	defer func() {
		runCancel()
		h.lifecycleMu.Lock()
		h.ctx, h.ctxCancel = nil, nil
		h.lifecycleMu.Unlock()
	}()

	workers := h.broadcastWorkers
	if workers <= 0 {
		workers = 4 // safe minimum
	}
	broadcastCh := make(chan *Message, cap(h.Broadcast))
	// RZ-23-07 (audit 2026-03-25 Wave 23): Track broadcast worker goroutines
	// with WaitGroup so shutdown can verify all workers drained.
	var broadcastWg sync.WaitGroup
	for i := 0; i < workers; i++ {
		broadcastWg.Add(1)
		ActiveGoroutines.Inc()
		go func() {
			defer broadcastWg.Done()
			defer ActiveGoroutines.Dec()
			for msg := range broadcastCh {
				h.broadcastMessage(runCtx, msg)
			}
		}()
	}

	// PERF-W17-03: Sample broadcast queue depth every 5s for Prometheus.
	queueDepthTicker := time.NewTicker(5 * time.Second)
	defer queueDepthTicker.Stop()

	for {
		select {
		case <-runCtx.Done():
			h.Logger.InfoContext(runCtx, "Hub.Run: context cancelled, stopping loop")
			close(broadcastCh)
			broadcastWg.Wait() // RZ-23-07: ensure all broadcast workers drained before return
			return

		case client := <-h.Register:
			h.handleRegister(ctx, client)

		case client := <-h.Unregister:
			h.handleUnregister(ctx, client)

		case msg := <-h.Broadcast:
			select {
			case broadcastCh <- msg:
			default:
				BroadcastDropsTotal.Inc()
				h.Logger.WarnContext(ctx, "Broadcast worker pool full, dropping message",
					"type", msg.Type,
					"room", msg.Room)
			}

		case <-queueDepthTicker.C:
			BroadcastQueueDepth.Set(float64(len(broadcastCh)))
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
		client.closeOnce.Do(func() { safeClose(client.Send) })
		if client.Conn != nil {
			if err := client.Conn.Close(); err != nil {
				h.Logger.ErrorContext(ctx, "Failed to close connection after max connections", "id", client.ID, "err", err)
			}
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
		safeClose(client.Send)

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

		// RZ-33-03: Dec inside closeOnce so concurrent unregister calls
		// only decrement the gauge once per client.
		ActiveConnections.Dec()
	})
	h.Logger.InfoContext(ctx, "Client disconnected", "id", client.ID)
}

type recipient struct {
	client      *Client
	evictOnFull bool
}

// collectRecipients gathers target clients under a read-lock.
// MOD-23-03 (audit 2026-03-25 Wave 23): Collect recipients under read-lock,
// then fan-out writes lock-free. Go 1.24 range-over-map is stable for sets.
func (h *Hub) collectRecipients(msg *Message, span trace.Span) []recipient {
	h.mu.RLock()
	defer h.mu.RUnlock()

	switch {
	case msg.Room != "":
		clients, ok := h.Rooms[msg.Room]
		if !ok {
			return nil
		}
		span.SetAttributes(attribute.Int("recipient.count", len(clients)))
		recipients := make([]recipient, 0, len(clients))
		for c := range clients {
			recipients = append(recipients, recipient{client: c})
		}
		return recipients
	case msg.To != "":
		c, ok := h.Clients[msg.To]
		if !ok {
			return nil
		}
		span.SetAttributes(attribute.Int("recipient.count", 1))
		return []recipient{{client: c}}
	default:
		span.SetAttributes(attribute.Int("recipient.count", len(h.Clients)))
		recipients := make([]recipient, 0, len(h.Clients))
		for _, c := range h.Clients {
			recipients = append(recipients, recipient{client: c, evictOnFull: true})
		}
		return recipients
	}
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

	// RZ-23-05 (audit 2026-03-25 Wave 23): Drop oversized broadcasts that would
	// exceed clients' ReadLimit (64 KB). Without this guard, recipients' ReadPump
	// closes the connection with CloseMessageTooBig. 4 KB headroom accounts for
	// WebSocket framing overhead.
	const maxBroadcastBytes = 60 * 1024 // 60 KB
	if len(data) > maxBroadcastBytes {
		h.Logger.WarnContext(bctx, "Broadcast message exceeds size limit, dropping",
			"size_bytes", len(data),
			"limit_bytes", maxBroadcastBytes,
			"type", msg.Type,
			"room", msg.Room)
		BroadcastDropsTotal.Inc()
		span.SetAttributes(attribute.Bool("dropped.oversized", true))
		return
	}

	recipients := h.collectRecipients(msg, span)

	for _, r := range recipients {
		if safeSend(r.client.Send, data) {
			MessagesDeliveredTotal.Inc()
		} else if r.evictOnFull {
			h.Logger.WarnContext(bctx, "Client buffer full or closed, evicting", "id", r.client.ID)
			go func(c *Client) {
				select {
				case h.Unregister <- c:
				case <-h.ctx.Done():
					// RZ-24-03: Hub shutting down; close client directly.
					c.closeOnce.Do(func() { safeClose(c.Send) })
				}
			}(r.client)
		}
	}
}

// SubscribeToNATS registers NATS subscriptions and stores them for graceful shutdown.
//
// TD-W14-08 (audit 2026-03-23 Wave 14): replaced over-broad "chat.>" wildcard
// with the specific single-level wildcard "chat.*".  The ">" token matches ALL
// subjects at any depth under "chat." (e.g. chat.admin, chat.audit.*.raw),
// which could deliver internal or future subjects to client WebSockets
// unintentionally.  "chat.*" matches exactly one additional token, restricting
// delivery to the current chat.{room_id} pattern.  Same tightening applied to
// "notifications.*".  Both are intentional breaking changes if any internal
// service currently publishes multi-level subjects under these prefixes.
//
//nolint:cyclop
func (h *Hub) SubscribeToNATS(appCtx context.Context) {
	if h.js == nil && h.Nats != nil && h.enableJetStream {
		if js, err := h.Nats.JetStream(); err == nil {
			h.js = js
		}
	}

	var chatSub *nats.Subscription
	var err error

	if h.js != nil && h.enableJetStream {
		chatSub, err = h.js.Subscribe("chat.*", h.handleChat(appCtx),
			nats.Durable(h.durableChat),
			nats.AckExplicit(),
			nats.ManualAck(),
		)
		if err != nil {
			h.Logger.WarnContext(appCtx, "JetStream chat subscription failed, falling back to core NATS", "err", err)
			chatSub, err = h.Nats.Subscribe("chat.*", h.handleChat(appCtx))
		}
	} else {
		chatSub, err = h.Nats.Subscribe("chat.*", h.handleChat(appCtx))
	}
	if err != nil {
		h.Logger.ErrorContext(appCtx, "NATS chat subscription failed — hub cannot deliver messages", "err", err)
		os.Exit(1)
	}
	h.subs = append(h.subs, chatSub)

	var notifSub *nats.Subscription
	if h.js != nil && h.enableJetStream {
		notifSub, err = h.js.Subscribe("notifications.*", h.handleNotifications(appCtx),
			nats.Durable(h.durableNotif),
			nats.AckExplicit(),
			nats.ManualAck(),
		)
		if err != nil {
			h.Logger.WarnContext(appCtx, "JetStream notifications subscription failed, falling back to core NATS", "err", err)
			notifSub, err = h.Nats.Subscribe("notifications.*", h.handleNotifications(appCtx))
		}
	} else {
		notifSub, err = h.Nats.Subscribe("notifications.*", h.handleNotifications(appCtx))
	}
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

	ctrlSub, err := h.Nats.Subscribe("ws_hub.control", h.handleControlMessage(appCtx))
	if err != nil {
		h.Logger.ErrorContext(appCtx, "NATS control subscription failed — hub cannot receive session control events", "err", err)
		os.Exit(1)
	}
	h.subs = append(h.subs, ctrlSub)

	// RZ-21-05 (audit 2026-03-25 Wave 21): Pre-warm JWKS cache on key rotation.
	jwksSub, err := h.Nats.Subscribe("keys.rotated", func(msg *nats.Msg) {
		h.Logger.InfoContext(appCtx, "JWKS rotation event received — pre-warming cache")
		h.tryForceRefreshJWKS(appCtx)
	})
	if err != nil {
		h.Logger.WarnContext(appCtx, "NATS keys.rotated subscription failed — falling back to on-demand refresh", "err", err)
	} else {
		h.subs = append(h.subs, jwksSub)
	}

	if h.js != nil && h.enableJetStream {
		h.Logger.InfoContext(appCtx, "Subscribed to NATS JetStream streams (CHAT_EVENTS, NOTIFICATIONS_EVENTS)")
	} else {
		h.Logger.InfoContext(appCtx, "Subscribed to NATS topics")
	}
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

		msgID := ""
		if msg.Header != nil {
			msgID = msg.Header.Get("Nats-Msg-Id")
		}
		if msgID != "" && h.dedupCache != nil {
			if _, ok := h.dedupCache.Get(msgID); ok {
				JetStreamDedupHitsTotal.Inc()
				safeAck(msg)
				return
			}
		}

		var wsMsg Message
		if err := json.Unmarshal(msg.Data, &wsMsg); err != nil {
			h.Logger.WarnContext(msgCtx, "ws-hub: malformed NATS chat message dropped",
				"subject", msg.Subject, "size", len(msg.Data), "err", err)
			safeAck(msg)
			return
		}
		select {
		case h.Broadcast <- &wsMsg:
			if msgID != "" && h.dedupCache != nil {
				h.dedupCache.Add(msgID, time.Now())
			}
			safeAck(msg)
		default:
			BroadcastDropsTotal.Inc()
			h.Logger.WarnContext(msgCtx, "Broadcast channel full, dropping NATS chat message",
				"subject", msg.Subject)
			safeNakWithDelay(msg, 5*time.Second)
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

		msgID := ""
		if msg.Header != nil {
			msgID = msg.Header.Get("Nats-Msg-Id")
		}
		if msgID != "" && h.dedupCache != nil {
			if _, ok := h.dedupCache.Get(msgID); ok {
				JetStreamDedupHitsTotal.Inc()
				safeAck(msg)
				return
			}
		}

		var wsMsg Message
		if err := json.Unmarshal(msg.Data, &wsMsg); err != nil {
			h.Logger.WarnContext(msgCtx, "ws-hub: malformed NATS notification dropped",
				"subject", msg.Subject, "size", len(msg.Data), "err", err)
			safeAck(msg)
			return
		}
		wsMsg.Type = "notification"
		select {
		case h.Broadcast <- &wsMsg:
			if msgID != "" && h.dedupCache != nil {
				h.dedupCache.Add(msgID, time.Now())
			}
			safeAck(msg)
		default:
			BroadcastDropsTotal.Inc()
			h.Logger.WarnContext(msgCtx, "Broadcast channel full, dropping NATS notification",
				"subject", msg.Subject)
			safeNakWithDelay(msg, 5*time.Second)
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

type controlPayload struct {
	Data struct {
		Action    string `json:"action"`
		Reason    string `json:"reason"`
		Timestamp uint64 `json:"timestamp"`
		UserID    string `json:"user_id"`
	} `json:"data"`
	Signature string `json:"signature"`
}

func (h *Hub) handleControlMessage(appCtx context.Context) nats.MsgHandler {
	const natsCallbackTimeout = 30 * time.Second
	return func(msg *nats.Msg) {
		defer func() {
			if r := recover(); r != nil {
				h.Logger.ErrorContext(appCtx, "NATS control callback panic recovered",
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
		_, span := otel.Tracer("hub").Start(msgCtx, "NATS.Subscribe.Control",
			trace.WithAttributes(
				semconv.MessagingSystemKey.String("nats"),
				semconv.MessagingOperationTypeKey.String("receive"),
				semconv.MessagingDestinationNameKey.String("ws_hub.control"),
			),
		)
		defer span.End()

		var payload controlPayload
		if err := json.Unmarshal(msg.Data, &payload); err != nil {
			h.Logger.WarnContext(msgCtx, "ws-hub: malformed NATS control message dropped",
				"subject", msg.Subject, "size", len(msg.Data), "err", err)
			return
		}

		if h.internalSecret == "" {
			h.Logger.WarnContext(msgCtx, "ws-hub: internalSecret empty, dropping control event",
				"user_id", payload.Data.UserID)
			return
		}

		dataBytes, err := json.Marshal(payload.Data)
		if err != nil {
			h.Logger.ErrorContext(msgCtx, "Failed to marshal control payload data for HMAC verification", "err", err)
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
			h.Logger.WarnContext(msgCtx, "Invalid internal NATS control signature — dropping event",
				"action", payload.Data.Action, "user_id", payload.Data.UserID)
			return
		}

		h.Logger.InfoContext(msgCtx, "Received valid NATS control event",
			"action", payload.Data.Action, "user_id", payload.Data.UserID, "reason", payload.Data.Reason)

		if h.authClient != nil {
			h.authClient.Invalidate(payload.Data.UserID, "")
		}

		if payload.Data.Action == "disconnect" || payload.Data.Reason == "access_revoked" {
			reason := payload.Data.Reason
			if reason == "" || reason == "access_revoked" {
				reason = "Access Revoked"
			}
			//nolint:contextcheck
			h.DisconnectUser(payload.Data.UserID, 4401, reason)
			SessionsRevokedTotal.Inc()
		} else {
			h.Logger.WarnContext(msgCtx, "Unknown control action ignored", "action", payload.Data.Action)
		}
	}
}

// DisconnectUser finds active client(s) for the given userID under a read lock (Hub.mu.RLock),
// then writes a WebSocket close control frame (code 4401, reason) and triggers unregistration.
// Adheres strictly to RZ-22-04: Hub.mu is released BEFORE calling client.Disconnect.
func (h *Hub) DisconnectUser(userID string, closeCode int, reason string) {
	if userID == "" {
		return
	}

	h.mu.RLock()
	var targets []*Client
	for _, client := range h.Clients {
		if client.UserID == userID || client.ID == userID {
			targets = append(targets, client)
		}
	}
	h.mu.RUnlock()

	if len(targets) == 0 {
		h.Logger.DebugContext(context.Background(), "DisconnectUser: no active connections found", "user_id", userID)
		return
	}

	h.Logger.InfoContext(context.Background(), "Disconnecting active user sessions",
		"user_id", userID, "count", len(targets), "code", closeCode, "reason", reason)

	for _, client := range targets {
		client.Disconnect(closeCode, reason)
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
		interval := h.limiterCleanupInterval
		if interval == 0 {
			interval = 5 * time.Minute
		}
		ticker := time.NewTicker(interval)
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
		h.lifecycleMu.Lock()
		if h.ctxCancel != nil {
			h.ctxCancel()
		}
		h.lifecycleMu.Unlock()
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

// HasJWKSCache reports whether the JWKS cache has been initialised.
// MOD-W17-05: Used by the readiness health endpoint to detect degraded state.
func (h *Hub) HasJWKSCache() bool {
	h.jwksMu.Lock()
	defer h.jwksMu.Unlock()
	return h.jwksCache != nil
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
