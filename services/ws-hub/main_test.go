package main

import (
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/university-ecosystem/ws-hub/pkg/config"
	"github.com/university-ecosystem/ws-hub/pkg/hub"
)

func TestLoadConfig_ReturnsDefaultValues(t *testing.T) {
	t.Setenv("WS_HUB_PORT", "")
	t.Setenv("NATS_URL", "")
	t.Setenv("JWT_SECRET", "")

	cfg := config.LoadConfig()

	assert.Equal(t, "8081", cfg.Port)
	assert.Equal(t, "nats://nats:4222", cfg.NatsURL)
	assert.Empty(t, cfg.JWTSecret)
}

func TestLoadConfig_ReadsEnvValues(t *testing.T) {
	t.Setenv("WS_HUB_PORT", "9999")
	t.Setenv("NATS_URL", "nats://custom:4222")
	t.Setenv("JWT_SECRET", "super-secret")

	cfg := config.LoadConfig()

	assert.Equal(t, "9999", cfg.Port)
	assert.Equal(t, "nats://custom:4222", cfg.NatsURL)
	assert.Equal(t, "super-secret", cfg.JWTSecret)
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

func TestConfig_StructFields(t *testing.T) {
	cfg := config.Config{
		Port:      "8080",
		NatsURL:   "nats://localhost:4222",
		JWTSecret: "secret",
	}

	assert.Equal(t, "8080", cfg.Port)
	assert.Equal(t, "nats://localhost:4222", cfg.NatsURL)
	assert.Equal(t, "secret", cfg.JWTSecret)
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
