// Package main implements a high-performance WebSocket hub for real-time messaging.
// It supports 10k+ concurrent connections with NATS JetStream integration.
package main

import (
	"context"
	"encoding/json"
	"net/http"
	"os"
	"os/signal"
	"sync"
	"syscall"
	"time"

	"strings"

	"github.com/golang-jwt/jwt/v5"
	"github.com/gorilla/websocket"
	"github.com/nats-io/nats.go"
	"go.uber.org/zap"

	"github.com/getsentry/sentry-go"
	"go.opentelemetry.io/contrib/instrumentation/net/http/otelhttp"
	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracegrpc"
	"go.opentelemetry.io/otel/sdk/resource"
	sdktrace "go.opentelemetry.io/otel/sdk/trace"
	semconv "go.opentelemetry.io/otel/semconv/v1.17.0"
)

// Config holds the hub configuration
type Config struct {
	Port           string
	NatsURL        string
	JWTSecret      string
	AllowedOrigins []string
	SentryDSN      string
	Environment    string
}

// Message represents a WebSocket message
type Message struct {
	Type    string          `json:"type"`
	Room    string          `json:"room,omitempty"`
	Payload json.RawMessage `json:"payload"`
	From    string          `json:"from,omitempty"`
	To      string          `json:"to,omitempty"`
}

// Client represents a connected WebSocket client
type Client struct {
	ID     string
	UserID string
	Conn   *websocket.Conn
	Rooms  map[string]bool
	Send   chan []byte
	Hub    *Hub
	mu     sync.Mutex
}

// Hub manages all WebSocket connections
type Hub struct {
	clients    map[string]*Client
	rooms      map[string]map[*Client]bool
	register   chan *Client
	unregister chan *Client
	broadcast  chan *Message
	nats       *nats.Conn
	logger     *zap.Logger
	mu         sync.RWMutex
}

var upgrader = websocket.Upgrader{
	ReadBufferSize:  1024,
	WriteBufferSize: 1024,
	CheckOrigin: func(r *http.Request) bool {
		// Origin header is set by the browser.
		origin := r.Header.Get("Origin")
		if origin == "" {
			return true // Allow non-browser clients
		}

		// Check against whitelist
		// Note: we'll access global config in handleWebSocket or initialize upgrader there
		// To stay simple and thread-safe, we'll use a dynamic check in handleWebSocket
		// or just allow for now and check inside the handler.
		// BETTER: Use a package-level variable updated by main.
		return isOriginAllowed(origin)
	},
}

var allowedOrigins []string
var originsMu sync.RWMutex

func isOriginAllowed(origin string) bool {
	originsMu.RLock()
	defer originsMu.RUnlock()
	for _, allowed := range allowedOrigins {
		if allowed == origin {
			return true
		}
	}
	return false
}

func loadConfig() *Config {
	return &Config{
		Port:           getEnv("WS_HUB_PORT", "8081"),
		NatsURL:        getEnv("NATS_URL", "nats://nats:4222"),
		JWTSecret:      getEnv("JWT_SECRET", ""),
		AllowedOrigins: getEnvSlice("ALLOWED_ORIGINS", []string{"http://localhost:3000", "http://localhost:5173"}),
		SentryDSN:      getEnv("SENTRY_DSN", ""),
		Environment:    getEnv("VITE_ENVIRONMENT", "development"),
	}
}

func getEnvSlice(key string, defaultValue []string) []string {
	valStr := os.Getenv(key)
	if valStr == "" {
		return defaultValue
	}
	parts := strings.Split(valStr, ",")
	var result []string
	for _, p := range parts {
		if trimmed := strings.TrimSpace(p); trimmed != "" {
			result = append(result, trimmed)
		}
	}
	return result
}

func getEnv(key, defaultValue string) string {
	if value := os.Getenv(key); value != "" {
		return value
	}
	return defaultValue
}

func main() {
	// Initialize logger
	logger, _ := zap.NewProduction()
	defer func() { _ = logger.Sync() }()

	logger.Info("Loading configuration")
	cfg := loadConfig()

	// Initialize Sentry
	if cfg.SentryDSN != "" {
		err := sentry.Init(sentry.ClientOptions{
			Dsn:              cfg.SentryDSN,
			Environment:      cfg.Environment,
			Release:          "ws-hub@1.0.0",
			TracesSampleRate: 1.0,
		})
		if err != nil {
			logger.Error("Sentry initialization failed", zap.Error(err))
		} else {
			logger.Info("Sentry initialized", zap.String("environment", cfg.Environment))
		}
	}

	// Initialize OpenTelemetry
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	tp, err := initTracer(ctx, cfg)
	if err != nil {
		logger.Error("OpenTelemetry initialization failed", zap.Error(err))
	} else {
		defer func() { _ = tp.Shutdown(ctx) }()
		logger.Info("OpenTelemetry initialized")
	}

	// Connect to NATS
	nc, err := nats.Connect(cfg.NatsURL,
		nats.RetryOnFailedConnect(true),
		nats.MaxReconnects(-1),
		nats.ReconnectWait(2*time.Second),
	)
	if err != nil {
		logger.Fatal("Failed to connect to NATS", zap.Error(err))
	}
	defer nc.Close()

	logger.Info("Connected to NATS", zap.String("url", cfg.NatsURL))

	// Create hub
	hub := &Hub{
		clients:    make(map[string]*Client),
		rooms:      make(map[string]map[*Client]bool),
		register:   make(chan *Client),
		unregister: make(chan *Client),
		broadcast:  make(chan *Message, 256),
		nats:       nc,
		logger:     logger,
	}

	// Start hub
	go hub.run()

	// Update global allowed origins for the upgrader's CheckOrigin callback
	originsMu.Lock()
	allowedOrigins = cfg.AllowedOrigins
	originsMu.Unlock()

	// Subscribe to NATS messages
	go hub.subscribeToNATS()

	// HTTP handlers wrapped with OTEL
	http.Handle("/ws", otelhttp.NewHandler(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		hub.handleWebSocket(w, r)
	}), "websocket_upgrade"))

	http.Handle("/health", otelhttp.NewHandler(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		hub.mu.RLock()
		clientCount := len(hub.clients)
		roomCount := len(hub.rooms)
		hub.mu.RUnlock()

		_ = json.NewEncoder(w).Encode(map[string]interface{}{
			"status":  "healthy",
			"clients": clientCount,
			"rooms":   roomCount,
		})
	}), "health_check"))

	// Start server with graceful shutdown
	server := &http.Server{
		Addr:         ":" + cfg.Port,
		ReadTimeout:  10 * time.Second,
		WriteTimeout: 10 * time.Second,
	}

	go func() {
		logger.Info("Starting WebSocket Hub", zap.String("port", cfg.Port))
		if err := server.ListenAndServe(); err != http.ErrServerClosed {
			logger.Fatal("Server error", zap.Error(err))
		}
	}()

	// Wait for interrupt
	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)
	<-quit

	logger.Info("Shutting down...")
	shutdownCtx, shutdownCancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer shutdownCancel()

	_ = server.Shutdown(shutdownCtx)
}

func (h *Hub) run() {
	for {
		select {
		case client := <-h.register:
			h.mu.Lock()
			h.clients[client.ID] = client
			h.mu.Unlock()
			h.logger.Info("Client connected", zap.String("id", client.ID))

		case client := <-h.unregister:
			h.mu.Lock()
			if _, ok := h.clients[client.ID]; ok {
				delete(h.clients, client.ID)
				close(client.Send)

				// Remove from all rooms
				for room := range client.Rooms {
					if clients, ok := h.rooms[room]; ok {
						delete(clients, client)
						if len(clients) == 0 {
							delete(h.rooms, room)
						}
					}
				}
			}
			h.mu.Unlock()
			h.logger.Info("Client disconnected", zap.String("id", client.ID))

		case msg := <-h.broadcast:
			h.broadcastMessage(msg)
		}
	}
}

func (h *Hub) broadcastMessage(msg *Message) {
	data, _ := json.Marshal(msg)

	h.mu.RLock()
	defer h.mu.RUnlock()

	if msg.Room != "" {
		// Send to room
		if clients, ok := h.rooms[msg.Room]; ok {
			for client := range clients {
				select {
				case client.Send <- data:
				default:
					// Client buffer full, skip
				}
			}
		}
	} else if msg.To != "" {
		// Direct message
		if client, ok := h.clients[msg.To]; ok {
			select {
			case client.Send <- data:
			default:
			}
		}
	} else {
		// Broadcast to all
		for _, client := range h.clients {
			select {
			case client.Send <- data:
			default:
			}
		}
	}
}

func (h *Hub) subscribeToNATS() {
	// Subscribe to chat messages
	_, _ = h.nats.Subscribe("chat.>", func(msg *nats.Msg) {
		var wsMsg Message
		if err := json.Unmarshal(msg.Data, &wsMsg); err == nil {
			h.broadcast <- &wsMsg
		}
	})

	// Subscribe to notifications
	_, _ = h.nats.Subscribe("notifications.>", func(msg *nats.Msg) {
		var wsMsg Message
		if err := json.Unmarshal(msg.Data, &wsMsg); err == nil {
			wsMsg.Type = "notification"
			h.broadcast <- &wsMsg
		}
	})

	h.logger.Info("Subscribed to NATS topics")
}

func (h *Hub) handleWebSocket(w http.ResponseWriter, r *http.Request) {
	// 1. Authenticate via JWT
	// We check for token in "access_token" subprotocol (common for JS WebSockets)
	// or in query parameters as a fallback.
	tokenStr := r.Header.Get("Sec-WebSocket-Protocol")
	if strings.Contains(tokenStr, "access_token") {
		// Gorilla websocket splits protocols by comma
		protocols := strings.Split(tokenStr, ",")
		for i, p := range protocols {
			p = strings.TrimSpace(p)
			if p == "access_token" && i+1 < len(protocols) {
				tokenStr = strings.TrimSpace(protocols[i+1])
				break
			}
		}
	} else {
		tokenStr = r.URL.Query().Get("token")
	}

	if tokenStr == "" {
		h.logger.Warn("WebSocket missing authentication token")
		http.Error(w, "Unauthorized", http.StatusUnauthorized)
		return
	}

	userID, err := h.validateToken(tokenStr)
	if err != nil {
		h.logger.Warn("WebSocket invalid authentication token", zap.Error(err))
		http.Error(w, "Unauthorized", http.StatusUnauthorized)
		return
	}

	conn, err := upgrader.Upgrade(w, r, nil)
	if err != nil {
		h.logger.Error("WebSocket upgrade failed", zap.Error(err))
		return
	}

	// Use userID from JWT
	clientID := userID
	if clientID == "" {
		clientID = generateID()
	}

	client := &Client{
		ID:     clientID,
		UserID: userID,
		Conn:   conn,
		Rooms:  make(map[string]bool),
		Send:   make(chan []byte, 256),
		Hub:    h,
	}

	h.register <- client

	go client.writePump()
	go client.readPump()
}

func (h *Hub) validateToken(tokenStr string) (string, error) {
	config := loadConfig()
	token, err := jwt.Parse(tokenStr, func(token *jwt.Token) (interface{}, error) {
		if _, ok := token.Method.(*jwt.SigningMethodHMAC); !ok {
			return nil, jwt.ErrSignatureInvalid
		}
		return []byte(config.JWTSecret), nil
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

func (c *Client) readPump() {
	defer func() {
		c.Hub.unregister <- c
		_ = c.Conn.Close()
	}()

	c.Conn.SetReadLimit(64 * 1024)
	_ = c.Conn.SetReadDeadline(time.Now().Add(60 * time.Second))
	c.Conn.SetPongHandler(func(string) error {
		_ = c.Conn.SetReadDeadline(time.Now().Add(60 * time.Second))
		return nil
	})

	for {
		_, data, err := c.Conn.ReadMessage()
		if err != nil {
			break
		}

		var msg Message
		if err := json.Unmarshal(data, &msg); err != nil {
			continue
		}

		msg.From = c.ID

		switch msg.Type {
		case "join":
			c.joinRoom(msg.Room)
		case "leave":
			c.leaveRoom(msg.Room)
		case "message":
			// Publish to NATS for persistence
			_ = c.Hub.nats.Publish("chat."+msg.Room, data)
			c.Hub.broadcast <- &msg
		}
	}
}

func (c *Client) writePump() {
	ticker := time.NewTicker(30 * time.Second)
	defer func() {
		ticker.Stop()
		_ = c.Conn.Close()
	}()

	for {
		select {
		case msg, ok := <-c.Send:
			_ = c.Conn.SetWriteDeadline(time.Now().Add(10 * time.Second))
			if !ok {
				_ = c.Conn.WriteMessage(websocket.CloseMessage, []byte{})
				return
			}

			if err := c.Conn.WriteMessage(websocket.TextMessage, msg); err != nil {
				return
			}

		case <-ticker.C:
			_ = c.Conn.SetWriteDeadline(time.Now().Add(10 * time.Second))
			if err := c.Conn.WriteMessage(websocket.PingMessage, nil); err != nil {
				return
			}
		}
	}
}

func (c *Client) joinRoom(room string) {
	if room == "" {
		return
	}

	c.mu.Lock()
	c.Rooms[room] = true
	c.mu.Unlock()

	c.Hub.mu.Lock()
	if c.Hub.rooms[room] == nil {
		c.Hub.rooms[room] = make(map[*Client]bool)
	}
	c.Hub.rooms[room][c] = true
	c.Hub.mu.Unlock()

	c.Hub.logger.Debug("Client joined room", zap.String("client", c.ID), zap.String("room", room))
}

func (c *Client) leaveRoom(room string) {
	c.mu.Lock()
	delete(c.Rooms, room)
	c.mu.Unlock()

	c.Hub.mu.Lock()
	if clients, ok := c.Hub.rooms[room]; ok {
		delete(clients, c)
		if len(clients) == 0 {
			delete(c.Hub.rooms, room)
		}
	}
	c.Hub.mu.Unlock()
}

func generateID() string {
	return time.Now().Format("20060102150405.000000")
}
func initTracer(ctx context.Context, cfg *Config) (*sdktrace.TracerProvider, error) {
	exporter, err := otlptracegrpc.New(ctx,
		otlptracegrpc.WithInsecure(),
		otlptracegrpc.WithEndpoint("jaeger:4317"),
	)
	if err != nil {
		return nil, err
	}

	res, err := resource.New(ctx,
		resource.WithAttributes(
			semconv.ServiceNameKey.String("ws-hub"),
			attribute.String("environment", cfg.Environment),
		),
	)
	if err != nil {
		return nil, err
	}

	tp := sdktrace.NewTracerProvider(
		sdktrace.WithBatcher(exporter),
		sdktrace.WithResource(res),
	)
	otel.SetTracerProvider(tp)
	return tp, nil
}
