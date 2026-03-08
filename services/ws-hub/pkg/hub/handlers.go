package hub

import (
	"context"
	"fmt"
	"net/http"
	"strings"
	"sync"
	"time"

	"github.com/golang-jwt/jwt/v5"
	"github.com/gorilla/websocket"
	"github.com/university-ecosystem/ws-hub/pkg/config"
	"go.uber.org/zap"
)

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
			originsMu.RLock()
			defer originsMu.RUnlock()
			for _, allowed := range allowedOrigins {
				if allowed == origin {
					return true
				}
			}
			return false
		},
	}
)

func SetAllowedOrigins(origins []string) {
	originsMu.Lock()
	defer originsMu.Unlock()
	allowedOrigins = origins
}

func (h *Hub) HandleWebSocket(w http.ResponseWriter, r *http.Request, cfg *config.Config) {
	// RZ-2: per-IP token-bucket check BEFORE any cryptographic work.
	// This prevents an attacker from exhausting the CPU with rapid upgrade
	// requests carrying invalid JWTs (each JWT.Parse call runs HMAC-SHA256).
	// requests carrying invalid JWTs (each JWT.Parse call runs HMAC-SHA256).
	clientIP := RealIP(r, cfg.TrustedProxiesSet)
	if !h.UpgradeLimiter.Allow(clientIP) {
		h.Logger.Warn("WebSocket upgrade rate limit exceeded", zap.String("ip", clientIP))
		http.Error(w, "Too Many Requests", http.StatusTooManyRequests)
		return
	}

	// Extract JWT exclusively from the Sec-WebSocket-Protocol header.
	// Format: "Sec-WebSocket-Protocol: access_token, <jwt>"
	// Query-string tokens (e.g. ?token=<jwt>) are intentionally not supported:
	// URL parameters appear verbatim in proxy access logs, browser history, and
	// OpenTelemetry spans — making any token in a URL effectively public.
	tokenStr := ""
	rawProtocol := r.Header.Get("Sec-WebSocket-Protocol")
	if strings.Contains(rawProtocol, "access_token") {
		protocols := strings.Split(rawProtocol, ",")
		for i, p := range protocols {
			p = strings.TrimSpace(p)
			if p == "access_token" && i+1 < len(protocols) {
				tokenStr = strings.TrimSpace(protocols[i+1])
				break
			}
		}
	}

	if tokenStr == "" {
		h.Logger.Warn("WebSocket connection rejected: missing or malformed Sec-WebSocket-Protocol token")
		http.Error(w, "Unauthorized", http.StatusUnauthorized)
		return
	}

	if len(cfg.JWTSecrets) == 0 {
		h.Logger.Error("No JWT secrets configured — rejecting connection")
		http.Error(w, "Service Unavailable", http.StatusServiceUnavailable)
		return
	}

	// WSH-02 (audit 2026-03-08 Wave 5): Pass request context so that JWKS
	// fetches are cancelled when the client disconnects, preventing goroutine
	// accumulation under rapid-reconnect / invalid-token attack patterns.
	userID, err := h.ValidateToken(r.Context(), tokenStr, cfg.JWTSecrets)
	if err != nil {
		h.Logger.Warn("WebSocket invalid authentication token", zap.Error(err))
		http.Error(w, "Unauthorized", http.StatusUnauthorized)
		return
	}

	conn, err := upgrader.Upgrade(w, r, nil)
	if err != nil {
		h.Logger.Error("WebSocket upgrade failed", zap.Error(err))
		return
	}

	clientID := userID
	if clientID == "" {
		clientID = fmt.Sprintf("%d", time.Now().UnixNano())
	}

	// Create a context for this specific client connection.
	// ReadPump calls cancel() on exit (disconnect), which propagates to any
	// in-flight AuthorizeRoomJoin / CanJoinRoom HTTP checks. (WSH-05)
	clientCtx, clientCancel := context.WithCancel(context.Background())

	client := &Client{
		ID:     clientID,
		UserID: userID,
		Conn:   conn,
		Rooms:  make(map[string]bool),
		Send:   make(chan []byte, cfg.SendBufferSize),
		Hub:    h,
		ctx:    clientCtx,
		cancel: clientCancel,
	}

	h.Register <- client

	go client.WritePump()
	go client.ReadPump()
}

// ValidateToken verifies tokenStr against JWKS (RS256) or HMAC secrets.
// Prefers RS256/JWKS if configured; falls back to HMAC for backward compatibility.
// ctx is used for JWKS cache access — pass r.Context() so that JWKS fetches
// are cancelled when the HTTP handler context is done (WSH-02).
// (RZ-3: audit 2026-02-24, MOD-1, WSH-02/03: audit 2026-03-08 Wave 5)
func (h *Hub) ValidateToken(ctx context.Context, tokenStr string, secrets []string) (string, error) {
	// ── Phase 1: Try RS256 via JWKS ──────────────────────────────────────────
	if h.jwksCache != nil && h.jwksURL != "" {
		// Use the caller's context so that JWKS fetches respect request
		// cancellation and don't accumulate goroutines on client disconnect.
		keySet, err := h.jwksCache.Get(ctx, h.jwksURL)
		if err != nil {
			// WSH-03: Log JWKS failure at ERROR level so operators are alerted.
			// A silent fall-through to HMAC without logging hides security
			// degradation (e.g. transient JWKS unreachability under DNS attack).
			h.Logger.Error("JWKS fetch failed, falling back to HMAC secrets",
				zap.String("jwks_url", h.jwksURL),
				zap.Error(err),
			)
			// If no HMAC secrets are configured, fail immediately rather than
			// returning an opaque signature error without context.
			if len(secrets) == 0 {
				return "", fmt.Errorf("JWKS unavailable and no HMAC secrets configured: %w", err)
			}
			// Fall through to Phase 2 with HMAC.
		} else {
			token, parseErr := jwt.Parse(tokenStr, func(t *jwt.Token) (interface{}, error) {
				// RZ-3: Pin to exactly RS256 for JWKS verification.
				if t.Method != jwt.SigningMethodRS256 {
					return nil, fmt.Errorf("unexpected signing method for JWKS: %v", t.Header["alg"])
				}
				// Use the kid from the token header to find the matching public key in the JWKS.
				kid, _ := t.Header["kid"].(string)
				key, ok := keySet.LookupKeyID(kid)
				if !ok {
					return nil, fmt.Errorf("kid %s not found in JWKS", kid)
				}
				var pubKey interface{}
				if err := key.Raw(&pubKey); err != nil {
					return nil, fmt.Errorf("failed to extract raw public key: %w", err)
				}
				return pubKey, nil
			})

			if parseErr == nil && token.Valid {
				if claims, ok := token.Claims.(jwt.MapClaims); ok {
					if sub, ok := claims["sub"].(string); ok {
						return sub, nil
					}
				}
			}
			// WSH-03: RS256 validation failed — log before falling back to HMAC
			// so that token format mismatches are visible in production logs.
			if parseErr != nil {
				h.Logger.Warn("RS256 JWT validation failed, falling back to HMAC",
					zap.Error(parseErr),
				)
			}
		}
	}

	// ── Phase 2: Fall back to HMAC secrets ───────────────────────────────────
	if len(secrets) == 0 {
		// No HMAC secrets configured and JWKS either not set or already handled.
		if h.jwksCache == nil {
			return "", jwt.ErrTokenSignatureInvalid
		}
		// JWKS was configured but failed and no HMAC fallback — error already
		// returned above in the err != nil branch. This path means JWKS failed
		// and caller has HMAC secrets; continue to Phase 2.
	}

	var lastErr error
	for _, secret := range secrets {
		token, err := jwt.Parse(tokenStr, func(t *jwt.Token) (interface{}, error) {
			// RZ-3: pin to exactly HS256 for symmetric secrets.
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
