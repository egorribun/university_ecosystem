package main

import (
	"os"
	"testing"

	"github.com/stretchr/testify/assert"
)

func TestGetEnv_ReturnsDefaultWhenNotSet(t *testing.T) {
	key := "TEST_WS_UNSET_VAR"
	os.Unsetenv(key)

	result := getEnv(key, "default_value")

	assert.Equal(t, "default_value", result)
}

func TestGetEnv_ReturnsEnvValueWhenSet(t *testing.T) {
	key := "TEST_WS_SET_VAR"
	os.Setenv(key, "custom_value")
	defer os.Unsetenv(key)

	result := getEnv(key, "default")

	assert.Equal(t, "custom_value", result)
}

func TestLoadConfig_ReturnsDefaultValues(t *testing.T) {
	originalPort := os.Getenv("WS_HUB_PORT")
	originalNats := os.Getenv("NATS_URL")
	originalJWT := os.Getenv("JWT_SECRET")

	os.Unsetenv("WS_HUB_PORT")
	os.Unsetenv("NATS_URL")
	os.Unsetenv("JWT_SECRET")

	defer func() {
		if originalPort != "" {
			os.Setenv("WS_HUB_PORT", originalPort)
		}
		if originalNats != "" {
			os.Setenv("NATS_URL", originalNats)
		}
		if originalJWT != "" {
			os.Setenv("JWT_SECRET", originalJWT)
		}
	}()

	config := loadConfig()

	assert.Equal(t, "8081", config.Port)
	assert.Equal(t, "nats://nats:4222", config.NatsURL)
	assert.Empty(t, config.JWTSecret)
}

func TestLoadConfig_ReadsEnvValues(t *testing.T) {
	os.Setenv("WS_HUB_PORT", "9999")
	os.Setenv("NATS_URL", "nats://custom:4222")
	os.Setenv("JWT_SECRET", "super-secret")

	defer func() {
		os.Unsetenv("WS_HUB_PORT")
		os.Unsetenv("NATS_URL")
		os.Unsetenv("JWT_SECRET")
	}()

	config := loadConfig()

	assert.Equal(t, "9999", config.Port)
	assert.Equal(t, "nats://custom:4222", config.NatsURL)
	assert.Equal(t, "super-secret", config.JWTSecret)
}

func TestGenerateID_ReturnsNonEmptyString(t *testing.T) {
	id := generateID()

	assert.NotEmpty(t, id)
}

func TestGenerateID_HasExpectedFormat(t *testing.T) {
	id := generateID()

	assert.Len(t, id, 21) // Format: 20060102150405.000000 (14 + 1 + 6 = 21)
	assert.Contains(t, id, ".")
}

func TestMessage_JSONTags(t *testing.T) {
	msg := Message{
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

func TestMessage_EmptyOptionalFields(t *testing.T) {
	msg := Message{
		Type:    "broadcast",
		Payload: []byte(`{}`),
	}

	assert.Empty(t, msg.Room)
	assert.Empty(t, msg.From)
	assert.Empty(t, msg.To)
}

func TestConfig_StructFields(t *testing.T) {
	config := Config{
		Port:      "8080",
		NatsURL:   "nats://localhost:4222",
		JWTSecret: "secret",
	}

	assert.Equal(t, "8080", config.Port)
	assert.Equal(t, "nats://localhost:4222", config.NatsURL)
	assert.Equal(t, "secret", config.JWTSecret)
}

func TestClient_InitialState(t *testing.T) {
	client := &Client{
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
	hub := &Hub{
		clients:    make(map[string]*Client),
		rooms:      make(map[string]map[*Client]bool),
		register:   make(chan *Client),
		unregister: make(chan *Client),
		broadcast:  make(chan *Message, 256),
	}

	assert.Empty(t, hub.clients)
	assert.Empty(t, hub.rooms)
	assert.NotNil(t, hub.register)
	assert.NotNil(t, hub.unregister)
	assert.NotNil(t, hub.broadcast)
}
