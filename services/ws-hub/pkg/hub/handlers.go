package hub

import (
	"context"
	"fmt"
	"net/http"
	"os"
	"strings"
	"sync"
	"sync/atomic"
	"time"

	"github.com/google/uuid"
	"github.com/gorilla/websocket"
	"github.com/quic-go/quic-go/http3"
	"github.com/quic-go/webtransport-go"
	goredis "github.com/redis/go-redis/v9"
	"github.com/university-ecosystem/ws-hub/pkg/config"
)

// PERF-W15-03 (audit 2026-03-23 Wave 15): Rate-limit forced JWKS refreshes.
// When a kid is not found in the cached JWKS, we trigger an immediate refresh —
// this handles key rotation without waiting for the 1-hour cache TTL.
// Rate-limited to once per 30s to prevent amplification under burst traffic
// (e.g., 10 000 reconnects after a deploy with rotated keys).
var _lastJWKSForceRefreshUnix atomic.Int64 // unix seconds, zero = never refreshed

const _jwksForceRefreshCooldown = 30 * time.Second

var jwksForceRefreshCASFunc = func(old, updated int64) bool {
	return _lastJWKSForceRefreshUnix.CompareAndSwap(old, updated)
}

type contextKey string

const tenantIDKey contextKey = "tenant_id"

type upgradeTicketIdentity struct {
	UserID     string
	TenantID   string
	SessionJTI string
}

const (
	// wsTicketKeyPrefix matches the Python backend's TICKET_KEY_PREFIX in app/api/ws/ticket.py.
	// Both services must use the same prefix — see contracts/redis-keys.md.
	wsTicketKeyPrefix = "ott:ws:"
	// revokedJTIKeyPrefix is written by the Python session service on logout.
	// Checking it closes the issue-to-upgrade revocation window.
	revokedJTIKeyPrefix = "revoked:jti:"
)

var (
	allowedOrigins []string
	originsMu      sync.RWMutex
	upgrader       = websocket.Upgrader{
		ReadBufferSize:  1024,
		WriteBufferSize: 1024,
		CheckOrigin:     isUpgradeOriginAllowed,
	}
	upgradeWTFunc                     = upgradeWT
	newWebTransportSessionFunc        = func(sess *webtransport.Session) Session { return NewWebTransportSession(sess) }
	validateUpgradeTicketIdentityFunc = func(h *Hub, ctx context.Context, ticket string) (upgradeTicketIdentity, error) {
		return h.validateUpgradeTicketIdentity(ctx, ticket)
	}
)

func isUpgradeOriginAllowed(r *http.Request) bool {
	origin := r.Header.Get("Origin")
	if origin == "" {
		return true
	}

	originsMu.RLock()
	defer originsMu.RUnlock()
	for _, allowed := range allowedOrigins {
		if allowed == origin {
			return true
		}
	}

	for _, allowed := range strings.Split(os.Getenv("WS_ALLOWED_ORIGINS"), ",") {
		if strings.TrimSpace(allowed) == origin {
			return true
		}
	}

	return false
}

func newConnectionID() string {
	return uuid.NewString()
}

// SetAllowedOrigins configures the origins allowed for WebSocket upgrades.
func SetAllowedOrigins(origins []string) {
	originsMu.Lock()
	defer originsMu.Unlock()
	allowedOrigins = origins
}

// ConfigureWebTransportServer binds the exact server used for upgrades to the
// HTTP/3 listener. Keeping one server instance is required by webtransport-go;
// upgrading with a different instance leaves sessions detached from the QUIC
// server that accepted the request.
func (h *Hub) ConfigureWebTransportServer(addr string, handler http.Handler) *webtransport.Server {
	h.webTransportServer.H3 = &http3.Server{Addr: addr, Handler: handler}
	return h.webTransportServer
}

// HandleWebSocket upgrades HTTP connections to WebSocket and registers clients.
func (h *Hub) HandleWebSocket(w http.ResponseWriter, r *http.Request, cfg *config.Config) {
	// RZ-W14-06 (audit 2026-03-23 Wave 14): two-phase context design.
	//
	// Phase 1 — setupCtx: inherits r.Context() with a 5s hard deadline.
	//   All pre-upgrade work (rate limiting, Redis GETDEL ticket validation,
	//   and the HTTP→WebSocket upgrade itself) runs under this bounded context.
	//   If the client stalls, the upgrade is aborted cleanly within 5 seconds
	//   rather than holding a goroutine open indefinitely.
	//
	// Phase 2 — clientCtx: context.WithoutCancel preserves request-scoped values,
	//   including the OTel span, while detaching the long-lived connection from
	//   request cancellation when the HTTP handler returns. The explicit cancel
	//   remains owned by the client lifecycle.
	setupCtx, setupCancel := context.WithTimeout(r.Context(), 5*time.Second)
	defer setupCancel()

	// RZ-2: per-IP token-bucket check BEFORE any cryptographic work.
	clientIP := RealIP(r, cfg.TrustedProxiesSet, cfg.TrustedCIDRs)
	if !h.UpgradeLimiter.Allow(clientIP) {
		h.Logger.WarnContext(setupCtx, "WebSocket upgrade rate limit exceeded", "ip", clientIP)
		http.Error(w, "Too Many Requests", http.StatusTooManyRequests)
		return
	}

	// RZ-W14-01 (audit 2026-03-23 Wave 14): authenticate via one-time upgrade
	// ticket (?ticket=<ott>) instead of JWT in Sec-WebSocket-Protocol header.
	//
	// The old Sec-WebSocket-Protocol path is permanently removed because:
	//   • WebSocket upgrade headers are written verbatim to proxy access logs
	//     (nginx/Caddy) and stored in Grafana Loki / ELK.
	//   • The browser WS API cannot set arbitrary headers, so Sec-WebSocket-Protocol
	//     was the only workaround — but it leaks the JWT silently.
	//
	// New flow:
	//   1. Client calls POST /ws/ticket (cookie-authenticated) → gets a 15s OTT ticket.
	//   2. Client opens wss://host/ws?ticket=<ott>.
	//   3. ws-hub validates the ticket via Redis GETDEL (atomic, single-use).
	//   4. The ticket stores "{user_id}:{jti}"; we reject revoked JTI values.
	ticket := r.URL.Query().Get("ticket")
	if ticket == "" {
		h.Logger.WarnContext(setupCtx, "WebSocket connection rejected: missing upgrade ticket")
		http.Error(w, "Unauthorized", http.StatusUnauthorized)
		return
	}

	// Reject requests that can never be upgraded before consuming the one-time
	// ticket. Otherwise a blocked origin or a full hub can burn a valid ticket.
	if upgrader.CheckOrigin != nil && !upgrader.CheckOrigin(r) {
		h.Logger.WarnContext(setupCtx, "WebSocket connection rejected: origin not allowed", "origin", r.Header.Get("Origin"))
		http.Error(w, "Forbidden", http.StatusForbidden)
		return
	}

	h.mu.RLock()
	atCapacity := h.maxClients > 0 && len(h.Clients) >= h.maxClients
	h.mu.RUnlock()
	if atCapacity {
		h.Logger.WarnContext(setupCtx, "WebSocket rejected: hub at capacity",
			"max_clients", h.maxClients)
		http.Error(w, "Service Unavailable", http.StatusServiceUnavailable)
		return
	}

	identity, err := validateUpgradeTicketIdentityFunc(h, setupCtx, ticket)
	if err != nil {
		h.Logger.WarnContext(setupCtx, "WebSocket upgrade ticket invalid", "err", err)
		http.Error(w, "Unauthorized", http.StatusUnauthorized)
		return
	}

	// RZ-W14-07 (audit 2026-03-23 Wave 14): reject empty sub rather than
	// generating a predictable nanosecond-timestamp fallback clientID.
	if identity.UserID == "" || identity.SessionJTI == "" {
		h.Logger.WarnContext(setupCtx, "WebSocket rejected: JWT sub claim is empty after validation")
		http.Error(w, "Unauthorized", http.StatusUnauthorized)
		return
	}
	if h.stopped.Load() {
		http.Error(w, "Service Unavailable", http.StatusServiceUnavailable)
		return
	}

	// CheckOrigin is configured on the package-level upgrader and validates
	// the request Origin against the configured allow-list before upgrading.
	// nosemgrep: go.gorilla.security.audit.websocket-missing-origin-check.websocket-missing-origin-check
	conn, err := upgrader.Upgrade(w, r, nil)
	if err != nil {
		h.Logger.ErrorContext(setupCtx, "WebSocket upgrade failed", "err", err)
		return
	}

	// Phase 2: long-lived client context, detached from the HTTP request
	// but with the OTel span propagated for distributed trace correlation.
	clientCtx, clientCancel := context.WithCancel(context.WithoutCancel(r.Context()))
	if identity.TenantID != "" {
		clientCtx = context.WithValue(clientCtx, tenantIDKey, identity.TenantID)
	}

	client := &Client{
		ID:         newConnectionID(),
		UserID:     identity.UserID,
		SessionJTI: identity.SessionJTI,
		Identity:   &ClientIdentity{TenantID: identity.TenantID},
		Conn:       NewWebSocketSession(conn),
		Rooms:      make(map[string]bool),
		Send:       make(chan []byte, cfg.SendBufferSize),
		Hub:        h,
		ctx:        clientCtx,
		cancel:     clientCancel,
	}

	if !h.registerClient(client) {
		client.cancelConnection()
		client.closeTransportWithControlFrame(websocket.CloseTryAgainLater, "hub is shutting down")
		client.closeOnce.Do(func() { safeClose(client.Send) })
		return
	}
	h.startClientPumps(client, clientCtx)
}

// HandleWebTransport upgrades HTTP/3 connections to WebTransport and registers clients.
func (h *Hub) HandleWebTransport(w http.ResponseWriter, r *http.Request, cfg *config.Config) {
	setupCtx, setupCancel := context.WithTimeout(r.Context(), 5*time.Second)
	defer setupCancel()

	clientIP := RealIP(r, cfg.TrustedProxiesSet, cfg.TrustedCIDRs)
	if !h.UpgradeLimiter.Allow(clientIP) {
		h.Logger.WarnContext(setupCtx, "WebTransport upgrade rate limit exceeded", "ip", clientIP)
		http.Error(w, "Too Many Requests", http.StatusTooManyRequests)
		return
	}

	ticket := r.URL.Query().Get("ticket")
	if ticket == "" {
		h.Logger.WarnContext(setupCtx, "WebTransport connection rejected: missing upgrade ticket")
		http.Error(w, "Unauthorized", http.StatusUnauthorized)
		return
	}

	// Reject impossible upgrades before consuming the one-time ticket.
	if h.webTransportServer.CheckOrigin != nil && !h.webTransportServer.CheckOrigin(r) {
		h.Logger.WarnContext(setupCtx, "WebTransport connection rejected: origin not allowed", "origin", r.Header.Get("Origin"))
		http.Error(w, "Forbidden", http.StatusForbidden)
		return
	}

	h.mu.RLock()
	atCapacity := h.maxClients > 0 && len(h.Clients) >= h.maxClients
	h.mu.RUnlock()
	if atCapacity {
		h.Logger.WarnContext(setupCtx, "WebTransport rejected: hub at capacity",
			"max_clients", h.maxClients)
		http.Error(w, "Service Unavailable", http.StatusServiceUnavailable)
		return
	}

	identity, err := validateUpgradeTicketIdentityFunc(h, setupCtx, ticket)
	if err != nil {
		h.Logger.WarnContext(setupCtx, "WebTransport upgrade ticket invalid", "err", err)
		http.Error(w, "Unauthorized", http.StatusUnauthorized)
		return
	}

	if identity.UserID == "" || identity.SessionJTI == "" {
		h.Logger.WarnContext(setupCtx, "WebTransport rejected: empty user_id")
		http.Error(w, "Unauthorized", http.StatusUnauthorized)
		return
	}
	if h.stopped.Load() {
		http.Error(w, "Service Unavailable", http.StatusServiceUnavailable)
		return
	}

	sess, err := upgradeWTFunc(h.webTransportServer, w, r)
	if err != nil {
		h.Logger.ErrorContext(setupCtx, "WebTransport upgrade failed", "err", err)
		return
	}

	clientCtx, clientCancel := context.WithCancel(context.WithoutCancel(r.Context()))
	if identity.TenantID != "" {
		clientCtx = context.WithValue(clientCtx, tenantIDKey, identity.TenantID)
	}

	client := &Client{
		ID:         newConnectionID(),
		UserID:     identity.UserID,
		SessionJTI: identity.SessionJTI,
		Identity:   &ClientIdentity{TenantID: identity.TenantID},
		Conn:       newWebTransportSessionFunc(sess),
		Rooms:      make(map[string]bool),
		Send:       make(chan []byte, cfg.SendBufferSize),
		Hub:        h,
		ctx:        clientCtx,
		cancel:     clientCancel,
	}

	if !h.registerClient(client) {
		client.cancelConnection()
		client.closeTransportWithControlFrame(websocket.CloseTryAgainLater, "hub is shutting down")
		client.closeOnce.Do(func() { safeClose(client.Send) })
		return
	}
	h.startClientPumps(client, clientCtx)
}

func validateTicketFormat(ticket string) error {
	if len(ticket) != 64 {
		// tickets are always 64-char hex strings (secrets.token_hex(32))
		return fmt.Errorf("invalid ticket length: %d", len(ticket))
	}
	// RZ-W16-06: Validate hex charset — tickets are secrets.token_hex(32) = 64 lowercase hex chars.
	for _, c := range ticket {
		if (c < '0' || c > '9') && (c < 'a' || c > 'f') {
			return fmt.Errorf("invalid ticket charset")
		}
	}
	return nil
}

func parseTicketPayload(raw string) (string, string, error) {
	// Canonical format: exactly "{user_id}:{jti}". Tenant identity is not part
	// of the OTT until the issuer can resolve membership server-side.
	parts := strings.Split(raw, ":")
	if len(parts) != 2 || parts[0] == "" || parts[1] == "" {
		return "", "", fmt.Errorf("malformed ticket payload")
	}
	return parts[0], parts[1], nil
}

func (h *Hub) checkJTINotRevoked(ctx context.Context, jti string) error {
	if h.revocationRedisClient == nil {
		return fmt.Errorf("revocation redis not available for ticket validation")
	}
	revoked, err := h.revocationRedisClient.Exists(ctx, revokedJTIKeyPrefix+jti).Result()
	if err != nil {
		return fmt.Errorf("session revocation check failed: %w", err)
	}
	if revoked > 0 {
		return fmt.Errorf("ticket session is revoked")
	}
	return nil
}

// validateUpgradeTicketIdentity atomically consumes a one-time WS upgrade
// ticket from Redis and returns the associated user ID and session JTI.
//
// The ticket was issued by the Python backend (POST /ws/ticket) and stored as:
//
//	Key  : "ott:ws:{ticket}"
//	Value: "{user_id}:{jti}"
//	TTL  : WS_TICKET_TTL_SECONDS (default 15s, configurable via Config.TicketTTLSeconds)
//
// GETDEL makes the ticket single-use: if two concurrent upgrade requests race
// with the same ticket, only the first succeeds. The consumed JTI is then
// checked against revoked:jti:{jti}; lookup failure rejects the upgrade.
func (h *Hub) validateUpgradeTicketIdentity(ctx context.Context, ticket string) (upgradeTicketIdentity, error) {
	if h.redisClient == nil {
		return upgradeTicketIdentity{}, fmt.Errorf("redis not available for ticket validation")
	}
	if err := validateTicketFormat(ticket); err != nil {
		return upgradeTicketIdentity{}, err
	}

	key := wsTicketKeyPrefix + ticket
	raw, err := h.redisClient.GetDel(ctx, key).Result()
	if err == goredis.Nil {
		return upgradeTicketIdentity{}, fmt.Errorf("ticket not found or already used")
	}
	if err != nil {
		return upgradeTicketIdentity{}, fmt.Errorf("redis error during ticket validation: %w", err)
	}

	userID, jti, err := parseTicketPayload(raw)
	if err != nil {
		return upgradeTicketIdentity{}, err
	}
	// Access-token JTIs are UUIDs. Reject malformed Redis ticket data before
	// accepting a transport: Pub/Sub intentionally ignores malformed events,
	// so treating such a JTI as valid could otherwise create a connection that
	// no canonical revocation publisher can target.
	if !isValidSessionRevocationJTI(jti) {
		return upgradeTicketIdentity{}, fmt.Errorf("invalid session JTI in ticket payload")
	}
	if err := h.checkJTINotRevoked(ctx, jti); err != nil {
		return upgradeTicketIdentity{}, err
	}
	return upgradeTicketIdentity{UserID: userID, SessionJTI: jti}, nil
}

// tryForceRefreshJWKS triggers an immediate JWKS refresh when a kid is not
// found in the cached key set (key rotation scenario).  Rate-limited to once
// per _jwksForceRefreshCooldown to prevent amplification under burst traffic.
func (h *Hub) tryForceRefreshJWKS(ctx context.Context) {
	now := time.Now().Unix()
	last := _lastJWKSForceRefreshUnix.Load()
	if now-last < int64(_jwksForceRefreshCooldown.Seconds()) {
		return // rate-limited — another goroutine refreshed recently
	}
	if !jwksForceRefreshCASFunc(last, now) {
		return // another goroutine won the CAS race
	}
	h.Logger.InfoContext(ctx, "JWKS: unknown kid — forcing cache refresh", "url", h.jwksURL)
	if _, err := h.jwksCache.Refresh(ctx, h.jwksURL); err != nil {
		h.Logger.ErrorContext(ctx, "JWKS force-refresh failed", "err", err)
	}
}

// upgradeWT wraps WebTransport srv.Upgrade to differentiate from gorilla.websocket.Upgrader.
func upgradeWT(srv *webtransport.Server, w http.ResponseWriter, r *http.Request) (*webtransport.Session, error) {
	var upgradeFn = (*webtransport.Server).Upgrade
	return upgradeFn(srv, w, r)
}
