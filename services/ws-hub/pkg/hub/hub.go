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

type Message struct {
	Type    string          `json:"type"`
	Room    string          `json:"room,omitempty"`
	Payload json.RawMessage `json:"payload"`
	From    string          `json:"from,omitempty"`
	To      string          `json:"to,omitempty"`
	// TraceCtx carries the W3C traceparent/tracestate from the NATS publisher
	// so that the broadcastMessage OTel span is linked to the originating trace.
	// WSH-06 (audit 2026-03-08 Wave 5).
	TraceCtx map[string]string `json:"trace_ctx,omitempty"`
}

type Hub struct {
	Clients    map[string]*Client
	Rooms      map[string]map[*Client]bool
	Register   chan *Client
	Unregister chan *Client
	Broadcast  chan *Message
	Nats       *nats.Conn
	Logger     *slog.Logger
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
	// jwksCacheCancel cancels the context passed to jwk.NewCache so the
	// internal refresh goroutine is stopped when Stop() is called.
	// TD-02 (audit 2026-03-15 Wave 7).
	jwksCacheCancel context.CancelFunc
	// jwksURL is the URL registered with jwksCache; used to retrieve the key set.
	jwksURL string
	// maxClients caps the number of concurrently connected WebSocket clients.
	// 0 means unlimited.  RZ-F-07 (audit 2026-03-07).
	maxClients int
	// internalSecret is the shared secret for local HMAC validation. (TD-NEW-07)
	internalSecret string
	// msgLimiters is a per-client token-bucket map that limits NATS publish rate.
	// TD-01 (audit 2026-03-15 Wave 7): prevents a single WS client from
	// flooding JetStream and causing backpressure for all other clients.
	msgLimiters sync.Map // map[clientID string]*rate.Limiter
	// WSH-P1-01 (audit Wave 10): stopOnce makes Stop() idempotent — a second
	// call is a no-op.  Without this, rolling deploys and test teardowns can
	// call Stop() twice, leaking the JWKS cache refresh goroutine each time.
	stopOnce sync.Once
}

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
		// At ~1 KB/handshake this limits the surface area for JWT-brute-force
		// DDoS without affecting legitimate reconnect scenarios.
		UpgradeLimiter: NewWSUpgradeRateLimiter(10, 60),
		jwksCache:      nil, // Initialised via SetupJWKS()
		maxClients:     cfg.MaxClients,
		internalSecret: cfg.InternalSecret,
	}
}

// SetupJWKS initialises the JWKS cache for RS256 token verification.
// It fetches public keys from jwksURL and refreshes them periodically. (MOD-1)
//
// TD-02 (audit 2026-03-15 Wave 7): a dedicated child context is created so
// that Stop() can cancel the jwk.Cache's internal refresh goroutine
// independently of the application-level context.  Without this, the goroutine
// would keep running after Stop() if the parent context is not cancelled yet
// (e.g. in tests or staged shutdowns).
func (h *Hub) SetupJWKS(ctx context.Context, jwksURL string) error {
	if jwksURL == "" {
		return nil
	}

	// RED-06 (audit Wave 11): Cancel any existing JWKS cache goroutine before
	// replacing it.  Without this, repeated calls to SetupJWKS (e.g. in rolling
	// deploys, integration tests, or staged restarts) overwrite h.jwksCacheCancel
	// before calling the old cancel — leaking the previous jwk.Cache refresh goroutine.
	// stopOnce in Stop() only helps for the CURRENT cancel; it does not retroactively
	// stop goroutines from prior SetupJWKS calls.
	if h.jwksCacheCancel != nil {
		h.jwksCacheCancel()
		h.jwksCacheCancel = nil
	}

	// Derive a child context whose cancel is stored for Stop().
	jwksCtx, cancel := context.WithCancel(ctx)
	h.jwksCacheCancel = cancel

	h.jwksCache = jwk.NewCache(jwksCtx)
	// Refresh the cache every hour.
	err := h.jwksCache.Register(jwksURL, jwk.WithMinRefreshInterval(time.Hour))
	if err != nil {
		cancel() // release context on error
		return fmt.Errorf("failed to register JWKS URL %s: %w", jwksURL, err)
	}
	// Store the URL so ValidateToken can retrieve the correct key set.
	h.jwksURL = jwksURL

	// Initial fetch to ensure we have keys at startup.
	_, err = h.jwksCache.Refresh(jwksCtx, jwksURL)
	if err != nil {
		h.Logger.Warn("Initial JWKS fetch failed; will retry in background", "err", err)
	}

	h.Logger.Info("JWKS cache initialised", "url", jwksURL)
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
			// RZ-F-07 (audit 2026-03-07): Enforce a maximum connection count so
			// that a single source cannot exhaust file descriptors or goroutine
			// stacks.  Reject the client gracefully (Close + drain Send channel)
			// rather than silently leaking it.
			if h.maxClients > 0 && len(h.Clients) >= h.maxClients {
				h.mu.Unlock()
				h.Logger.Warn("Max connections reached, rejecting client",
					"id", client.ID,
					"max", h.maxClients)
				client.closeOnce.Do(func() { close(client.Send) })
				_ = client.Conn.Close()
				continue
			}
			h.Clients[client.ID] = client
			h.mu.Unlock()
			ActiveConnections.Inc()
			h.Logger.Info("Client connected", "id", client.ID)

		case client := <-h.Unregister:
			h.mu.Lock()
			if existingClient, ok := h.Clients[client.ID]; ok && existingClient == client {
				delete(h.Clients, client.ID)
			}
			h.mu.Unlock()

			client.closeOnce.Do(func() {
				close(client.Send)

				// Establish consistent lock order (Hub.mu -> Client.mu) matching JoinRoom.
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
			h.Logger.Info("Client disconnected", "id", client.ID)

		case msg := <-h.Broadcast:
			// WSH-06 (audit 2026-03-08 Wave 5): pass a background context here;
			// trace context is injected per-message via msg.TraceCtx in broadcastMessage.
			h.broadcastMessage(ctx, msg)
		}
	}
}

// broadcastMessage fans a message out to the appropriate recipients.
// WSH-06 (audit 2026-03-08 Wave 5): accepts parent ctx and restores the
// OTel trace context from msg.TraceCtx (W3C traceparent map) so spans are
// linked to the upstream NATS publisher trace rather than being orphaned.
func (h *Hub) broadcastMessage(parentCtx context.Context, msg *Message) {
	// Restore W3C trace context if the publisher embedded it.
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
		client      *Client
		evictOnFull bool // true only for global broadcast where we auto-evict
	}

	// PERF-01 (audit 2026-03-15 Wave 7): pre-allocate the slice inside the
	// RLock using the current map length so append() never reallocates.
	// For 500 clients this saves ~9 copy operations, reducing critical-section
	// hold time from O(N log N) allocations to a single O(N) slice write.
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
		// Global broadcast — evict slow consumers.
		span.SetAttributes(attribute.Int("recipient.count", len(h.Clients)))
		recipients = make([]recipient, 0, len(h.Clients))
		for _, c := range h.Clients {
			recipients = append(recipients, recipient{client: c, evictOnFull: true})
		}
	}
	h.mu.RUnlock() // released before any channel writes

	// Fan-out happens outside the lock — Register/Unregister can now proceed
	// concurrently without blocking on our channel writes.
	//
	// RZ-F-02 (audit 2026-03-07): Use safeSend instead of a bare select to
	// guard against the closed-channel race.  Between h.mu.RUnlock() above
	// and the send below, the Unregister handler can close(client.Send).
	// A send to a closed channel panics even inside a select statement; only
	// a recover()-based wrapper handles it safely.
	for _, r := range recipients {
		if safeSend(r.client.Send, data) {
			MessagesDeliveredTotal.Inc()
		} else if r.evictOnFull {
			// Buffer full or channel closed: schedule eviction.
			// Unregister handler is the sole owner of close(client.Send).
			h.Logger.Warn("Client buffer full or closed, evicting", "id", r.client.ID)
			go func(c *Client) { h.Unregister <- c }(r.client)
		}
		// For room/direct messages, silently drop — the client has an
		// application-level reconnect mechanism.
	}
}

// SubscribeToNATS registers NATS subscriptions and stores them for graceful
// shutdown via Stop().  Fatals on subscription error (RZ-4): a hub that
// cannot receive NATS messages delivers no messages — better to fail loudly
// at startup than silently serve a broken system.
//
// WSH-P1-03 (audit Wave 10): appCtx is the application lifecycle context.
// Each callback checks appCtx.Done() before processing so that in-flight
// messages are discarded cleanly during shutdown rather than blocking the
// NATS drain and causing terminationGracePeriodSeconds to be exceeded.
func (h *Hub) SubscribeToNATS(appCtx context.Context) {
	const natsCallbackTimeout = 30 * time.Second

	chatSub, err := h.Nats.Subscribe("chat.>", func(msg *nats.Msg) {
		// RZ-03 (audit 2026-03-15 Wave 7): recover() first so that any panic
		// (e.g. nil pointer dereference on malformed NATS payload) is logged
		// rather than crashing the subscriber goroutine.  A crashed goroutine
		// silently stops the subscription — the hub would deliver no messages
		// until restarted.
		defer func() {
			if r := recover(); r != nil {
				h.Logger.Error("NATS chat callback panic recovered",
					"panic", r,
					"subject", msg.Subject)
			}
		}()

		// WSH-P1-03: exit immediately if the application is shutting down.
		select {
		case <-appCtx.Done():
			return
		default:
		}

		// Propagate W3C trace context from NATS headers, chained from appCtx
		// so the span lifecycle is bounded by the application context.
		msgCtx, cancel := context.WithTimeout(appCtx, natsCallbackTimeout)
		defer cancel()
		msgCtx = otel.GetTextMapPropagator().Extract(msgCtx, propagation.HeaderCarrier(msg.Header))
		_, span := otel.Tracer("hub").Start(msgCtx, "NATS.Subscribe.Chat",
			// MOD-02: messaging.* semconv v1.27.0 for Jaeger/Tempo correlation.
			trace.WithAttributes(
				semconv.MessagingSystemKey.String("nats"),
				semconv.MessagingOperationTypeKey.String("receive"),
				semconv.MessagingDestinationNameKey.String("chat.*"),
			),
		)
		defer span.End()

		var wsMsg Message
		if err := json.Unmarshal(msg.Data, &wsMsg); err == nil {
			// Non-blocking push: dropping here is safer than blocking the NATS
			// subscriber goroutine (blocked goroutine → MaxPending exceeded → sub closed).
			select {
			case h.Broadcast <- &wsMsg:
			default:
				h.Logger.Warn("Broadcast channel full, dropping NATS chat message",
					"subject", msg.Subject)
			}
		}
	})
	if err != nil {
		h.Logger.Error("NATS chat subscription failed — hub cannot deliver messages", "err", err)
		os.Exit(1)
	}
	h.subs = append(h.subs, chatSub)

	notifSub, err := h.Nats.Subscribe("notifications.>", func(msg *nats.Msg) {
		// RZ-03 (audit 2026-03-15 Wave 7): panic recovery — same rationale as chat callback.
		defer func() {
			if r := recover(); r != nil {
				h.Logger.Error("NATS notifications callback panic recovered",
					"panic", r,
					"subject", msg.Subject)
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
		if err := json.Unmarshal(msg.Data, &wsMsg); err == nil {
			wsMsg.Type = "notification"
			select {
			case h.Broadcast <- &wsMsg:
			default:
				h.Logger.Warn("Broadcast channel full, dropping NATS notification",
					"subject", msg.Subject)
			}
		}
	})
	if err != nil {
		h.Logger.Error("NATS notifications subscription failed — hub cannot deliver messages", "err", err)
		os.Exit(1)
	}
	h.subs = append(h.subs, notifSub)

	// M-007 (audit 2026-03-10): Distributed cache invalidation subscription.
	// Receives events from the Python backend when a participant is removed.
	invSub, err := h.Nats.Subscribe("cache.invalidate", func(msg *nats.Msg) {
		// RZ-03 (audit 2026-03-15 Wave 7): panic recovery — same rationale as chat callback.
		defer func() {
			if r := recover(); r != nil {
				h.Logger.Error("NATS cache.invalidate callback panic recovered",
					"panic", r,
					"subject", msg.Subject)
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

		if err := json.Unmarshal(msg.Data, &payload); err == nil {
			// TD-NEW-07: Validate HMAC signature before performing invalidation.
			// Python side uses json.dumps(sort_keys=True, separators=(',', ':')).
			// In Go, struct field order determines JSON key order in Marshal.
			// We define the struct with RoomID, Timestamp, UserID (alphabetical)
			// to match Python's sort_keys=True.
			dataBytes, _ := json.Marshal(payload.Data)

			hFunc := hmac.New(sha256.New, []byte(h.internalSecret))
			hFunc.Write(dataBytes)
			expectedSigBytes := hFunc.Sum(nil)

			// RZ-W9-02: Use constant-time comparison to prevent timing-based HMAC
			// recovery.  String equality (!=) short-circuits on the first differing
			// byte, leaking how many leading bytes of the signature are correct.
			// Decode both sides to raw bytes so hmac.Equal (which calls
			// subtle.ConstantTimeCompare) operates on equal-length slices.
			payloadSigBytes, decodeErr := hex.DecodeString(payload.Signature)
			if decodeErr != nil || !hmac.Equal(payloadSigBytes, expectedSigBytes) {
				h.Logger.Warn("Invalid internal NATS signature — dropping event",
					"room_id", payload.Data.RoomID,
					"user_id", payload.Data.UserID)
				// MOD-02 fix: assign and end the span — bare Start() discards the span,
				// causing an OTel span leak on every invalid-signature drop.
				_, sigSpan := otel.Tracer("hub").Start(msgCtx, "InvalidInternalSignature")
				sigSpan.End()
				return
			}

			if h.authClient != nil {
				h.authClient.Invalidate(payload.Data.UserID, payload.Data.RoomID)
				// MOD-02 fix: same — assign and end to avoid unfinished span leak.
				_, invSpan := otel.Tracer("hub").Start(msgCtx, "CacheInvalidated")
				invSpan.End()
			}
		}
	})
	if err != nil {
		h.Logger.Error("NATS cache invalidation subscription failed", "err", err)
		os.Exit(1)
	}
	h.subs = append(h.subs, invSub)

	h.Logger.Info("Subscribed to NATS topics")
}

// StartLimiterCleanup launches a background goroutine that periodically
// removes orphaned rate.Limiter entries from msgLimiters.
//
// PERF-W9-06: msgLimiters entries are normally deleted in the defer inside
// client.ReadPump().  When a goroutine panics before the defer executes, the
// entry is never removed.  At ~10k connections/day with a 1% crash rate this
// accumulates ~100 orphaned limiters/day (~100 KB/day).  The cleanup goroutine
// performs a reconciliation sweep every 5 minutes: any entry whose client ID
// is no longer in h.Clients is deleted.  The goroutine exits when ctx is done.
func (h *Hub) StartLimiterCleanup(ctx context.Context) {
	go func() {
		ticker := time.NewTicker(5 * time.Minute)
		defer ticker.Stop()
		for {
			select {
			case <-ctx.Done():
				return
			case <-ticker.C:
				// Snapshot the active client IDs under the read lock so the
				// subsequent sync.Map walk does not need to hold the lock.
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
					h.Logger.Info("Cleaned up orphaned msgLimiters",
						"removed", removed)
				}
			}
		}
	}()
}

// Stop drains all NATS subscriptions (flushing in-flight messages), stops
// the per-IP upgrade rate limiter GC goroutine, and cancels the JWKS
// cache refresh goroutine.  Call this from the application shutdown path
// before closing the NATS connection.
//
// TD-02 (audit 2026-03-15 Wave 7): cancel jwksCacheCancel so the
// jwk.Cache internal goroutine exits promptly on shutdown.
// Stop drains all NATS subscriptions, stops the per-IP upgrade rate limiter
// GC goroutine, and cancels the JWKS cache refresh goroutine.
//
// WSH-P1-01 (audit Wave 10): wrapped in sync.Once so repeated calls (e.g.
// SIGTERM handler + defer) are idempotent — the JWKS goroutine is cancelled
// exactly once regardless of how many times Stop() is called.
func (h *Hub) Stop() {
	h.stopOnce.Do(func() {
		for _, sub := range h.subs {
			if err := sub.Drain(); err != nil {
				h.Logger.Warn("NATS subscription drain error", "err", err)
			}
		}
		if h.UpgradeLimiter != nil {
			h.UpgradeLimiter.Stop()
		}
		if h.jwksCacheCancel != nil {
			h.jwksCacheCancel()
		}
	})
}

// AuthorizeRoomJoin verifies that userID is a participant of the given room
// by delegating to the configured RoomAuthClient.
// Fails closed: returns false when no client is configured or the check fails.
// WSH-05 (audit 2026-03-08 Wave 5): ctx propagated to CanJoinRoom so that
// the backend HTTP check is cancelled on context expiry / client disconnect.
func (h *Hub) AuthorizeRoomJoin(ctx context.Context, userID, room string) bool {
	if h.authClient == nil {
		// No auth client configured — deny by default (fail-closed).
		h.Logger.Warn("AuthorizeRoomJoin: no auth client configured, denying",
			"user", userID, "room", room)
		return false
	}
	return h.authClient.CanJoinRoom(ctx, userID, room)
}
