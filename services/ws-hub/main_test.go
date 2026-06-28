package main

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"github.com/university-ecosystem/ws-hub/pkg/config"
	"github.com/university-ecosystem/ws-hub/pkg/hub"
)

func TestLoadConfig_ReturnsDefaultValues(t *testing.T) {
	t.Setenv("WS_HUB_PORT", "")
	t.Setenv("NATS_URL", "")
	t.Setenv("JWT_SECRET", "")
	t.Setenv("JWT_SECRETS", "")

	cfg := config.LoadConfig()

	assert.Equal(t, "8081", cfg.Port)
	assert.Equal(t, "nats://nats:4222", cfg.NatsURL)
	assert.Empty(t, cfg.JWTSecrets)
}

func TestLoadConfig_ReadsLegacyJWTSecret(t *testing.T) {
	t.Setenv("WS_HUB_PORT", "9999")
	t.Setenv("NATS_URL", "nats://custom:4222")
	t.Setenv("JWT_SECRETS", "")
	t.Setenv("JWT_SECRET", "super-secret")

	cfg := config.LoadConfig()

	assert.Equal(t, "9999", cfg.Port)
	assert.Equal(t, "nats://custom:4222", cfg.NatsURL)
	assert.Equal(t, []string{"super-secret"}, cfg.JWTSecrets)
}

func TestLoadConfig_ReadsMultipleJWTSecrets(t *testing.T) {
	t.Setenv("JWT_SECRETS", "new-key, old-key")
	t.Setenv("JWT_SECRET", "")

	cfg := config.LoadConfig()

	// JWT_SECRETS takes precedence; both secrets loaded for rotation support.
	assert.Equal(t, []string{"new-key", "old-key"}, cfg.JWTSecrets)
}

func TestConfig_StructFields(t *testing.T) {
	cfg := config.Config{
		Port:       "8080",
		NatsURL:    "nats://localhost:4222",
		JWTSecrets: []string{"secret"},
	}

	assert.Equal(t, "8080", cfg.Port)
	assert.Equal(t, "nats://localhost:4222", cfg.NatsURL)
	assert.Equal(t, []string{"secret"}, cfg.JWTSecrets)
}

func TestMessage_JSONTags(t *testing.T) {
	msg := hub.Message{
		Type:    "chat",
		Room:    "room-1",
		Payload: []byte(`{"text":"hello"}`),
		From:    "user-1",
		To:      "user-2",
	}

	assert.Equal(t, "chat", msg.Type)
	assert.Equal(t, "room-1", msg.Room)
	assert.Equal(t, "user-1", msg.From)
	assert.Equal(t, "user-2", msg.To)
}

func TestClient_InitialState(t *testing.T) {
	client := &hub.Client{
		ID:     "client-123",
		UserID: "user-456",
		Rooms:  make(map[string]bool),
		Send:   make(chan []byte, 256),
	}

	assert.Equal(t, "client-123", client.ID)
	assert.Equal(t, "user-456", client.UserID)
	assert.Empty(t, client.Rooms)
	assert.NotNil(t, client.Send)
}

func TestHub_InitialState(t *testing.T) {
	h := &hub.Hub{
		Clients:    make(map[string]*hub.Client),
		Rooms:      make(map[string]map[*hub.Client]bool),
		Register:   make(chan *hub.Client),
		Unregister: make(chan *hub.Client),
		Broadcast:  make(chan *hub.Message, 256),
	}

	assert.Empty(t, h.Clients)
	assert.Empty(t, h.Rooms)
	assert.NotNil(t, h.Register)
	assert.NotNil(t, h.Unregister)
	assert.NotNil(t, h.Broadcast)
}

func TestInitLogger(t *testing.T) {
	logger := initLogger()
	assert.NotNil(t, logger)
}

func TestInitRedis_FailsGracefully(t *testing.T) {
	cfg := &config.Config{
		RedisURL: "localhost:9999", // invalid/unreachable
	}
	logger := initLogger()
	rdb := initRedis(context.Background(), cfg, logger)
	assert.Nil(t, rdb)
}

func TestSetupHubAndHandlers_ProbesHealth(t *testing.T) {
	cfg := &config.Config{
		Port:           "8081",
		BackendURL:     "http://localhost:1",
		AllowedOrigins: []string{"http://localhost:3000"},
	}
	logger := initLogger()

	// Create hub and handlers
	h := setupHub(context.Background(), cfg, logger, nil, nil)
	assert.NotNil(t, h)

	setupHandlers(h, cfg, logger, nil, nil)

	t.Run("liveness endpoint", func(t *testing.T) {
		rec := httptest.NewRecorder()
		req, err := http.NewRequest(http.MethodGet, "/health/live", nil)
		require.NoError(t, err)
		http.DefaultServeMux.ServeHTTP(rec, req)
		assert.Equal(t, http.StatusOK, rec.Code)
		assert.Contains(t, rec.Body.String(), "alive")
	})

	t.Run("readiness endpoint degraded", func(t *testing.T) {
		rec := httptest.NewRecorder()
		req, err := http.NewRequest(http.MethodGet, "/health/ready", nil)
		require.NoError(t, err)
		http.DefaultServeMux.ServeHTTP(rec, req)
		// Expecting 502/503 because NATS/Redis/JWKS are not initialized/configured
		assert.Equal(t, http.StatusServiceUnavailable, rec.Code)
		assert.Contains(t, rec.Body.String(), "degraded")
	})

	t.Run("legacy health endpoint", func(t *testing.T) {
		rec := httptest.NewRecorder()
		req, err := http.NewRequest(http.MethodGet, "/health", nil)
		require.NoError(t, err)
		http.DefaultServeMux.ServeHTTP(rec, req)
		assert.Equal(t, http.StatusOK, rec.Code)
		assert.Contains(t, rec.Body.String(), "healthy")
	})

	t.Run("websocket endpoint rejects non-upgrade", func(t *testing.T) {
		rec := httptest.NewRecorder()
		req, err := http.NewRequest(http.MethodGet, "/ws", nil)
		require.NoError(t, err)
		http.DefaultServeMux.ServeHTTP(rec, req)
		// websocket upgrade should fail with unauthorized due to missing ticket
		assert.Equal(t, http.StatusUnauthorized, rec.Code)
	})

	t.Run("metrics endpoint", func(t *testing.T) {
		rec := httptest.NewRecorder()
		req, err := http.NewRequest(http.MethodGet, "/metrics", nil)
		require.NoError(t, err)
		http.DefaultServeMux.ServeHTTP(rec, req)
		assert.Equal(t, http.StatusOK, rec.Code)
	})
}

func TestSetupHub_JWKS(t *testing.T) {
	cfg := &config.Config{
		Port:           "8081",
		BackendURL:     "http://localhost:1",
		AllowedOrigins: []string{"http://localhost:3000"},
		JWKSURL:        "http://127.0.0.1:1/jwks",
	}
	logger := initLogger()
	h := setupHub(context.Background(), cfg, logger, nil, nil)
	assert.NotNil(t, h)
	assert.True(t, h.HasJWKSCache())
}

func TestRunServer_Error(t *testing.T) {
	cfg := &config.Config{
		Port: "-1",
	}
	logger := initLogger()
	h := hub.NewHub(nil, logger, nil, cfg, nil)
	runServer(cfg, logger, h)
}
