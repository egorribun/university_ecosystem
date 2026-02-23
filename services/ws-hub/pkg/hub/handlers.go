package hub

import (
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

	userID, err := h.ValidateToken(tokenStr, cfg.JWTSecret)
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

	client := &Client{
		ID:     clientID,
		UserID: userID,
		Conn:   conn,
		Rooms:  make(map[string]bool),
		Send:   make(chan []byte, 256),
		Hub:    h,
	}

	h.Register <- client

	go client.WritePump()
	go client.ReadPump()
}

func (h *Hub) ValidateToken(tokenStr, secret string) (string, error) {
	token, err := jwt.Parse(tokenStr, func(token *jwt.Token) (interface{}, error) {
		if _, ok := token.Method.(*jwt.SigningMethodHMAC); !ok {
			return nil, jwt.ErrSignatureInvalid
		}
		return []byte(secret), nil
	})

	if err != nil {
		return "", err
	}

	if claims, ok := token.Claims.(jwt.MapClaims); ok && token.Valid {
		if sub, ok := claims["sub"].(string); ok {
			return sub, nil
		}
		return "", jwt.ErrTokenInvalidClaims
	}

	return "", jwt.ErrTokenInvalidClaims
}
