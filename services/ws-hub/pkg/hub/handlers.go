package hub

import (
	"context"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"net/http"
	"os"
	"strings"
	"sync"
	"sync/atomic"
	"time"

	"github.com/golang-jwt/jwt/v5"
	"github.com/gorilla/websocket"
	"github.com/quic-go/webtransport-go"
	goredis "github.com/redis/go-redis/v9"
	"github.com/university-ecosystem/ws-hub/pkg/config"
	"go.opentelemetry.io/otel/trace"
)

// PERF-W15-03 (audit 2026-03-23 Wave 15): Rate-limit forced JWKS refreshes.
// When a kid is not found in the cached JWKS, we trigger an immediate refresh —
// this handles key rotation without waiting for the 1-hour cache TTL.
// Rate-limited to once per 30s to prevent amplification under burst traffic
// (e.g., 10 000 reconnects after a deploy with rotated keys).
var _lastJWKSForceRefreshUnix atomic.Int64 // unix seconds, zero = never refreshed

const _jwksForceRefreshCooldown = 30 * time.Second

type contextKey string

const tenantIDKey contextKey = "tenant_id"

// wsTicketKeyPrefix matches the Python backend's TICKET_KEY_PREFIX in app/api/ws/ticket.py.
// Both services must use the same prefix — see contracts/redis-keys.md.
const wsTicketKeyPrefix = "ott:ws:"

var (
	allowedOrigins []string
	originsMu      sync.RWMutex
	upgrader       = websocket.Upgrader{
		ReadBufferSize:  1024,
		WriteBufferSize: 1024,
		CheckOrigin: func(r *http.Request) bool {
			origin := r.Header.Get("Origin")
			if origin == "" {
				return true
			}

			// Check configured slice (populated via SetAllowedOrigins from config).
			originsMu.RLock()
			defer originsMu.RUnlock()
			for _, allowed := range allowedOrigins {
				if allowed == origin {
					return true
				}
			}

			// Check WS_ALLOWED_ORIGINS env var (comma-separated) as a secondary source.
			// This allows runtime overrides without redeployment.
			for _, allowed := range strings.Split(os.Getenv("WS_ALLOWED_ORIGINS"), ",") {
				if strings.TrimSpace(allowed) == origin {
					return true
				}
			}

			// In non-production environments allow all origins to ease local development.
			// In production this returns false so unrecognised origins are rejected.
			env := os.Getenv("ENVIRONMENT")
			return env != "production"
		},
	}
	wtUpgrader = webtransport.Server{
		CheckOrigin: func(r *http.Request) bool {
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

			env := os.Getenv("ENVIRONMENT")
			return env != "production"
		},
	}
)

// SetAllowedOrigins configures the origins allowed for WebSocket upgrades.
func SetAllowedOrigins(origins []string) {
	originsMu.Lock()
	defer originsMu.Unlock()
	allowedOrigins = origins
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
	// Phase 2 — clientCtx: detached from r.Context() via context.Background()
	//   so that the long-lived WebSocket connection is not cancelled when the
	//   HTTP handler returns (which happens immediately after upgrader.Upgrade).
	//   The OTel span from the originating HTTP request is carried forward via
	//   trace.ContextWithSpan so that ReadPump/WritePump activity remains
	//   correlated with the upgrade request in distributed traces.
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
	//   4. The ticket stores "{user_id}:{jti}"; we extract userID from it.
	ticket := r.URL.Query().Get("ticket")
	if ticket == "" {
		h.Logger.WarnContext(setupCtx, "WebSocket connection rejected: missing upgrade ticket")
		http.Error(w, "Unauthorized", http.StatusUnauthorized)
		return
	}

	userID, tenantID, err := h.validateUpgradeTicket(setupCtx, ticket)
	if err != nil {
		h.Logger.WarnContext(setupCtx, "WebSocket upgrade ticket invalid", "err", err)
		http.Error(w, "Unauthorized", http.StatusUnauthorized)
		return
	}

	// RZ-W14-07 (audit 2026-03-23 Wave 14): reject empty sub rather than
	// generating a predictable nanosecond-timestamp fallback clientID.
	if userID == "" {
		h.Logger.WarnContext(setupCtx, "WebSocket rejected: JWT sub claim is empty after validation")
		http.Error(w, "Unauthorized", http.StatusUnauthorized)
		return
	}

	// TD-31-05: Pre-check capacity before WebSocket upgrade and goroutine spawn.
	// This is a racy check (another client may register concurrently), but it
	// prevents the upgrade + goroutine spawn in the common case.  The authoritative
	// check remains in handleRegister inside the Run loop.
	h.mu.RLock()
	atCapacity := h.maxClients > 0 && len(h.Clients) >= h.maxClients
	h.mu.RUnlock()
	if atCapacity {
		h.Logger.WarnContext(setupCtx, "WebSocket rejected: hub at capacity",
			"max_clients", h.maxClients)
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
	clientCtx, clientCancel := context.WithCancel(context.Background())
	clientCtx = trace.ContextWithSpan(clientCtx, trace.SpanFromContext(r.Context()))
	if tenantID != "" {
		clientCtx = context.WithValue(clientCtx, tenantIDKey, tenantID)
	}

	client := &Client{
		ID:       userID,
		UserID:   userID,
		TenantID: tenantID,
		Conn:     NewWebSocketSession(conn),
		Rooms:    make(map[string]bool),
		Send:     make(chan []byte, cfg.SendBufferSize),
		Hub:      h,
		ctx:      clientCtx,
		cancel:   clientCancel,
	}

	h.Register <- client
	go client.WritePump()
	go client.ReadPump()
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

	userID, tenantID, err := h.validateUpgradeTicket(setupCtx, ticket)
	if err != nil {
		h.Logger.WarnContext(setupCtx, "WebTransport upgrade ticket invalid", "err", err)
		http.Error(w, "Unauthorized", http.StatusUnauthorized)
		return
	}

	if userID == "" {
		h.Logger.WarnContext(setupCtx, "WebTransport rejected: empty user_id")
		http.Error(w, "Unauthorized", http.StatusUnauthorized)
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

	if wtUpgrader.CheckOrigin != nil && !wtUpgrader.CheckOrigin(r) {
		h.Logger.WarnContext(setupCtx, "WebTransport connection rejected: origin not allowed", "origin", r.Header.Get("Origin"))
		http.Error(w, "Forbidden", http.StatusForbidden)
		return
	}

	sess, err := upgradeWT(&wtUpgrader, w, r)
	if err != nil {
		h.Logger.ErrorContext(setupCtx, "WebTransport upgrade failed", "err", err)
		return
	}

	clientCtx, clientCancel := context.WithCancel(context.Background())
	clientCtx = trace.ContextWithSpan(clientCtx, trace.SpanFromContext(r.Context()))
	if tenantID != "" {
		clientCtx = context.WithValue(clientCtx, tenantIDKey, tenantID)
	}

	client := &Client{
		ID:       userID,
		UserID:   userID,
		TenantID: tenantID,
		Conn:     NewWebTransportSession(sess),
		Rooms:    make(map[string]bool),
		Send:     make(chan []byte, cfg.SendBufferSize),
		Hub:      h,
		ctx:      clientCtx,
		cancel:   clientCancel,
	}

	h.Register <- client
	go client.WritePump()
	go client.ReadPump()
}

// validateUpgradeTicket atomically consumes a one-time WS upgrade ticket from
// Redis and returns the associated userID and tenantID.
//
// The ticket was issued by the Python backend (POST /ws/ticket) and stored as:
//
//	Key  : "ott:ws:{ticket}"
//	Value: "{user_id}:{jti}:{tenant_id}" or "{user_id}:{jti}"
//	TTL  : WS_TICKET_TTL_SECONDS (default 15s, configurable via Config.TicketTTLSeconds)
//
// GETDEL makes the ticket single-use: if two concurrent upgrade requests race
// with the same ticket, only the first succeeds.
func (h *Hub) validateUpgradeTicket(ctx context.Context, ticket string) (string, string, error) {
	if h.redisClient == nil {
		return "", "", fmt.Errorf("redis not available for ticket validation")
	}
	if len(ticket) != 64 {
		// tickets are always 64-char hex strings (secrets.token_hex(32))
		return "", "", fmt.Errorf("invalid ticket length: %d", len(ticket))
	}
	// RZ-W16-06: Validate hex charset — tickets are secrets.token_hex(32) = 64 lowercase hex chars.
	for _, c := range ticket {
		if (c < '0' || c > '9') && (c < 'a' || c > 'f') {
			return "", "", fmt.Errorf("invalid ticket charset")
		}
	}

	key := wsTicketKeyPrefix + ticket
	raw, err := h.redisClient.GetDel(ctx, key).Result()
	if err == goredis.Nil {
		return "", "", fmt.Errorf("ticket not found or already used")
	}
	if err != nil {
		return "", "", fmt.Errorf("redis error during ticket validation: %w", err)
	}

	// Format: "{user_id}:{jti}:{tenant_id}" or "{user_id}:{jti}"
	parts := strings.Split(raw, ":")
	if len(parts) < 2 || parts[0] == "" {
		return "", "", fmt.Errorf("malformed ticket payload")
	}
	userID := parts[0]
	tenantID := ""
	if len(parts) >= 3 {
		tenantID = parts[2]
	}

	if userID == "" {
		return "", "", fmt.Errorf("empty user_id in ticket payload")
	}
	return userID, tenantID, nil
}

// extractAlgFromHeader reads the "alg" field from a JWT's base64url-encoded
// header without fully parsing the token.  Returns an error if the header is
// malformed or the alg claim is absent.
func extractAlgFromHeader(tokenStr string) (string, error) {
	parts := strings.SplitN(tokenStr, ".", 3)
	if len(parts) != 3 {
		return "", fmt.Errorf("malformed JWT: expected 3 parts, got %d", len(parts))
	}
	headerJSON, err := base64.RawURLEncoding.DecodeString(parts[0])
	if err != nil {
		return "", fmt.Errorf("malformed JWT header encoding: %w", err)
	}
	var header struct {
		Alg string `json:"alg"`
	}
	if err := json.Unmarshal(headerJSON, &header); err != nil {
		return "", fmt.Errorf("malformed JWT header JSON: %w", err)
	}
	if header.Alg == "" {
		return "", fmt.Errorf("JWT header missing alg claim")
	}
	return header.Alg, nil
}

// ValidateToken verifies tokenStr by routing to the correct algorithm path
// based on the token's own "alg" header claim.
//
// RZ-W14-02 (audit 2026-03-23 Wave 14): the previous implementation tried
// RS256 first and fell back to HMAC on any RS256 failure.  An attacker who
// could craft a token with alg=HS256 (signed with the known HMAC secret)
// would be routed to HMAC validation after RS256 rejected it — a textbook
// algorithm-confusion / downgrade attack.
//
// The fix: parse the alg header BEFORE validating, and commit to exactly one
// path.  RS256 tokens never fall through to HMAC; HS256 tokens never attempt
// RS256.  Any other algorithm is rejected immediately.
func (h *Hub) ValidateToken(ctx context.Context, tokenStr string, secrets []string) (string, error) {
	alg, err := extractAlgFromHeader(tokenStr)
	if err != nil {
		return "", fmt.Errorf("token header parse error: %w", err)
	}

	switch alg {
	case "RS256":
		// RS256 tokens must validate via JWKS — no HMAC fallback regardless of
		// whether HMAC secrets are configured.
		return h.validateRS256(ctx, tokenStr)
	case "HS256":
		return h.validateHMAC(tokenStr, secrets)
	default:
		return "", fmt.Errorf("unsupported JWT algorithm %q: only RS256 and HS256 are accepted", alg)
	}
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
	if !_lastJWKSForceRefreshUnix.CompareAndSwap(last, now) {
		return // another goroutine won the CAS race
	}
	h.Logger.InfoContext(ctx, "JWKS: unknown kid — forcing cache refresh", "url", h.jwksURL)
	if _, err := h.jwksCache.Refresh(ctx, h.jwksURL); err != nil {
		h.Logger.ErrorContext(ctx, "JWKS force-refresh failed", "err", err)
	}
}

func (h *Hub) validateRS256(ctx context.Context, tokenStr string) (string, error) {
	if h.jwksCache == nil || h.jwksURL == "" {
		return "", fmt.Errorf("JWKS not configured")
	}

	keySet, err := h.jwksCache.Get(ctx, h.jwksURL)
	if err != nil {
		// RZ-W18-04 (audit 2026-03-23 Wave 18): no HMAC fallback occurs — this
		// function returns the error immediately. Log message corrected.
		h.Logger.ErrorContext(ctx, "JWKS fetch failed — RS256 validation cannot proceed",
			"jwks_url", h.jwksURL, "err", err)
		return "", err
	}

	// PERF-W15-03: keyFunc that triggers force-refresh on kid mismatch.
	// On first parse attempt, if the kid is not found, we refresh and retry once.
	kidMissed := false
	keyFunc := func(t *jwt.Token) (interface{}, error) {
		if t.Method != jwt.SigningMethodRS256 {
			return nil, fmt.Errorf("unexpected signing method for JWKS: %v", t.Header["alg"])
		}
		kid, _ := t.Header["kid"].(string)
		key, ok := keySet.LookupKeyID(kid)
		if !ok {
			kidMissed = true
			return nil, fmt.Errorf("kid %q not found in JWKS", kid)
		}
		var pubKey interface{}
		if err := key.Raw(&pubKey); err != nil {
			return nil, fmt.Errorf("failed to extract raw public key: %w", err)
		}
		return pubKey, nil
	}

	token, parseErr := jwt.Parse(tokenStr, keyFunc)

	// kid not found → may be a key rotation — refresh and retry once.
	if kidMissed {
		h.tryForceRefreshJWKS(ctx)
		if refreshedSet, getErr := h.jwksCache.Get(ctx, h.jwksURL); getErr == nil {
			keySet = refreshedSet
			kidMissed = false
			token, parseErr = jwt.Parse(tokenStr, keyFunc)
		}
	}

	if parseErr == nil && token.Valid {
		if claims, ok := token.Claims.(jwt.MapClaims); ok {
			if sub, ok := claims["sub"].(string); ok {
				return sub, nil
			}
		}
	}

	if parseErr != nil {
		// RZ-W19-03 (audit 2026-03-24 Wave 19): corrected misleading log message.
		// No HMAC fallback occurs — RS256 failures are terminal (see line 248).
		h.Logger.WarnContext(ctx, "RS256 JWT validation failed — rejecting token (no HMAC fallback)", "err", parseErr)
	}
	return "", fmt.Errorf("invalid RS256 token")
}

func (h *Hub) validateHMAC(tokenStr string, secrets []string) (string, error) {
	if len(secrets) == 0 {
		return "", jwt.ErrTokenSignatureInvalid
	}

	var lastErr error
	for _, secret := range secrets {
		token, err := jwt.Parse(tokenStr, func(t *jwt.Token) (interface{}, error) {
			if t.Method != jwt.SigningMethodHS256 {
				return nil, fmt.Errorf("unexpected signing method: %v", t.Header["alg"])
			}
			return []byte(secret), nil
		})
		if err != nil {
			lastErr = err
			continue
		}
		if claims, ok := token.Claims.(jwt.MapClaims); ok && token.Valid {
			if sub, ok := claims["sub"].(string); ok {
				return sub, nil
			}
			return "", jwt.ErrTokenInvalidClaims
		}
	}
	if lastErr != nil {
		return "", lastErr
	}
	return "", jwt.ErrTokenInvalidClaims
}

// upgradeWT wraps WebTransport srv.Upgrade to differentiate from gorilla.websocket.Upgrader.
func upgradeWT(srv *webtransport.Server, w http.ResponseWriter, r *http.Request) (*webtransport.Session, error) {
	var upgradeFn = (*webtransport.Server).Upgrade
	return upgradeFn(srv, w, r)
}
