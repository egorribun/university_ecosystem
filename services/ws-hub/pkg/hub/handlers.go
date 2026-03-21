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

// SetAllowedOrigins configures the origins allowed for WebSocket upgrades.
func SetAllowedOrigins(origins []string) {
	originsMu.Lock()
	defer originsMu.Unlock()
	allowedOrigins = origins
}

// HandleWebSocket upgrades HTTP connections to WebSocket and registers clients.
func (h *Hub) HandleWebSocket(w http.ResponseWriter, r *http.Request, cfg *config.Config) {
	ctx := r.Context()
	// RZ-2: per-IP token-bucket check BEFORE any cryptographic work.
	clientIP := RealIP(r, cfg.TrustedProxiesSet, cfg.TrustedCIDRs)
	if !h.UpgradeLimiter.Allow(clientIP) {
		h.Logger.WarnContext(ctx, "WebSocket upgrade rate limit exceeded", "ip", clientIP)
		http.Error(w, "Too Many Requests", http.StatusTooManyRequests)
		return
	}

	// Extract JWT exclusively from the Sec-WebSocket-Protocol header.
	tokenStr := h.extractToken(r.Header.Get("Sec-WebSocket-Protocol"))
	if tokenStr == "" {
		h.Logger.WarnContext(ctx, "WebSocket connection rejected: missing or malformed Sec-WebSocket-Protocol token")
		http.Error(w, "Unauthorized", http.StatusUnauthorized)
		return
	}

	if len(cfg.JWTSecrets) == 0 {
		h.Logger.ErrorContext(ctx, "No JWT secrets configured — rejecting connection")
		http.Error(w, "Service Unavailable", http.StatusServiceUnavailable)
		return
	}

	userID, err := h.ValidateToken(ctx, tokenStr, cfg.JWTSecrets)
	if err != nil {
		h.Logger.WarnContext(ctx, "WebSocket invalid authentication token", "err", err)
		http.Error(w, "Unauthorized", http.StatusUnauthorized)
		return
	}

	conn, err := upgrader.Upgrade(w, r, nil)
	if err != nil {
		h.Logger.ErrorContext(ctx, "WebSocket upgrade failed", "err", err)
		return
	}

	clientID := userID
	if clientID == "" {
		clientID = fmt.Sprintf("%d", time.Now().UnixNano())
	}

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

func (h *Hub) extractToken(rawProtocol string) string {
	if strings.Contains(rawProtocol, "access_token") {
		protocols := strings.Split(rawProtocol, ",")
		for i, p := range protocols {
			p = strings.TrimSpace(p)
			if p == "access_token" && i+1 < len(protocols) {
				return strings.TrimSpace(protocols[i+1])
			}
		}
	}
	return ""
}

// ValidateToken verifies tokenStr against JWKS (RS256) or HMAC secrets.
// Prefers RS256/JWKS if configured; falls back to HMAC for backward compatibility.
// (RZ-3: audit 2026-02-24, MOD-1, WSH-02/03: audit 2026-03-08 Wave 5).
func (h *Hub) ValidateToken(ctx context.Context, tokenStr string, secrets []string) (string, error) {
	// 1. Try RS256 via JWKS
	if sub, err := h.validateRS256(ctx, tokenStr); err == nil {
		return sub, nil
	} else if h.jwksCache != nil && h.jwksURL != "" && len(secrets) == 0 {
		// If JWKS was intended but failed and no HMAC fallback, return the error.
		return "", err
	}

	// 2. Fall back to HMAC
	return h.validateHMAC(tokenStr, secrets)
}

func (h *Hub) validateRS256(ctx context.Context, tokenStr string) (string, error) {
	if h.jwksCache == nil || h.jwksURL == "" {
		return "", fmt.Errorf("JWKS not configured")
	}

	keySet, err := h.jwksCache.Get(ctx, h.jwksURL)
	if err != nil {
		h.Logger.ErrorContext(ctx, "JWKS fetch failed, falling back to HMAC secrets",
			"jwks_url", h.jwksURL, "err", err)
		return "", err
	}

	token, parseErr := jwt.Parse(tokenStr, func(t *jwt.Token) (interface{}, error) {
		if t.Method != jwt.SigningMethodRS256 {
			return nil, fmt.Errorf("unexpected signing method for JWKS: %v", t.Header["alg"])
		}
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

	if parseErr != nil {
		h.Logger.WarnContext(ctx, "RS256 JWT validation failed, falling back to HMAC", "err", parseErr)
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
