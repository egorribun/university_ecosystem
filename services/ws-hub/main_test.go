package main

import (
	"bufio"
	"context"
	"net"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/alicebob/miniredis/v2"
	"github.com/nats-io/nats.go"
	"github.com/redis/go-redis/v9"
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
	http.DefaultServeMux = http.NewServeMux()

	cfg := &config.Config{
		Port:           "8081",
		BackendURL:     "http://localhost:1",
		AllowedOrigins: []string{"http://localhost:3000"},
	}
	logger := initLogger()

	h, err := setupHub(context.Background(), cfg, logger, nil, nil)
	require.NoError(t, err)
	assert.NotNil(t, h)

	mux := http.NewServeMux()
	setupHandlers(mux, h, cfg, logger, nil, nil)

	t.Run("liveness endpoint", func(t *testing.T) {
		rec := httptest.NewRecorder()
		req, err := http.NewRequestWithContext(t.Context(), http.MethodGet, "/health/live", nil)
		require.NoError(t, err)
		mux.ServeHTTP(rec, req)
		assert.Equal(t, http.StatusOK, rec.Code)
		assert.Contains(t, rec.Body.String(), "alive")
	})

	t.Run("readiness endpoint degraded", func(t *testing.T) {
		rec := httptest.NewRecorder()
		req, err := http.NewRequestWithContext(t.Context(), http.MethodGet, "/health/ready", nil)
		require.NoError(t, err)
		mux.ServeHTTP(rec, req)
		// Expecting 502/503 because NATS/Redis/JWKS are not initialized/configured
		assert.Equal(t, http.StatusServiceUnavailable, rec.Code)
		assert.Contains(t, rec.Body.String(), "degraded")
	})

	t.Run("legacy health endpoint", func(t *testing.T) {
		rec := httptest.NewRecorder()
		req, err := http.NewRequestWithContext(t.Context(), http.MethodGet, "/health", nil)
		require.NoError(t, err)
		mux.ServeHTTP(rec, req)
		assert.Equal(t, http.StatusOK, rec.Code)
		assert.Contains(t, rec.Body.String(), "healthy")
	})

	t.Run("websocket endpoint rejects non-upgrade", func(t *testing.T) {
		rec := httptest.NewRecorder()
		req, err := http.NewRequestWithContext(t.Context(), http.MethodGet, "/ws", nil)
		require.NoError(t, err)
		mux.ServeHTTP(rec, req)
		// websocket upgrade should fail with unauthorized due to missing ticket
		assert.Equal(t, http.StatusUnauthorized, rec.Code)
	})

	t.Run("metrics endpoint", func(t *testing.T) {
		rec := httptest.NewRecorder()
		req, err := http.NewRequestWithContext(t.Context(), http.MethodGet, "/metrics", nil)
		require.NoError(t, err)
		mux.ServeHTTP(rec, req)
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
	h, err := setupHub(context.Background(), cfg, logger, nil, nil)
	require.NoError(t, err)
	assert.NotNil(t, h)
	assert.True(t, h.HasJWKSCache())
}

func TestRunServer_Error(t *testing.T) {
	cfg := &config.Config{
		Port:             "-1",
		WebTransportPort: "-1",
	}
	logger := initLogger()
	h := hub.NewHub(nil, logger, nil, cfg, nil)
	mux := http.NewServeMux()
	runServer(cfg, logger, h, mux)
}

func TestSetupHubAndHandlers_ReadinessHealthy(t *testing.T) {
	lc := net.ListenConfig{}
	l, err := lc.Listen(t.Context(), "tcp", "127.0.0.1:0")
	require.NoError(t, err)
	defer func() { _ = l.Close() }() //nolint:errcheck // test listener cleanup

	go func() {
		conn, err := l.Accept()
		if err != nil {
			return
		}
		defer func() { _ = conn.Close() }() //nolint:errcheck // test conn cleanup
		if _, writeErr := conn.Write([]byte(`INFO {"server_id":"MOCK","version":"2.0.0","host":"127.0.0.1","port":4222,"auth_required":false}` + "\r\n")); writeErr != nil {
			t.Logf("mock NATS INFO write failed: %v", writeErr)
			return
		}

		reader := bufio.NewReader(conn)
		for {
			line, err := reader.ReadString('\n')
			if err != nil {
				return
			}
			if strings.HasPrefix(line, "PING") {
				if _, writeErr := conn.Write([]byte("PONG\r\n")); writeErr != nil {
					t.Logf("mock NATS PONG write failed: %v", writeErr)
					return
				}
			}
		}
	}()

	nc, err := nats.Connect("nats://" + l.Addr().String())
	require.NoError(t, err)
	defer nc.Close()

	mr := miniredis.RunT(t)
	rdb := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	defer func() { _ = rdb.Close() }() //nolint:errcheck // test cleanup

	cfg := &config.Config{
		Port:           "8081",
		BackendURL:     "http://localhost:1",
		AllowedOrigins: []string{"http://localhost:3000"},
		JWKSURL:        "http://127.0.0.1:1/jwks",
	}
	logger := initLogger()

	h, err := setupHub(context.Background(), cfg, logger, nc, rdb)
	require.NoError(t, err)
	mux := http.NewServeMux()
	setupHandlers(mux, h, cfg, logger, nc, rdb)

	rec := httptest.NewRecorder()
	req, err := http.NewRequestWithContext(context.Background(), http.MethodGet, "/health/ready", nil)
	require.NoError(t, err)
	mux.ServeHTTP(rec, req)
	assert.Equal(t, http.StatusOK, rec.Code)
	assert.Contains(t, rec.Body.String(), "ready")
}

func TestSetupHubAndHandlers_ReadinessRedisPingError(t *testing.T) {
	rdb := redis.NewClient(&redis.Options{Addr: "127.0.0.1:1"})
	defer func() { _ = rdb.Close() }() //nolint:errcheck // test cleanup

	cfg := &config.Config{
		Port:           "8081",
		BackendURL:     "http://localhost:1",
		AllowedOrigins: []string{"http://localhost:3000"},
	}
	logger := initLogger()

	h, err := setupHub(context.Background(), cfg, logger, nil, rdb)
	require.NoError(t, err)
	mux := http.NewServeMux()
	setupHandlers(mux, h, cfg, logger, nil, rdb)

	rec := httptest.NewRecorder()
	req, err := http.NewRequestWithContext(context.Background(), http.MethodGet, "/health/ready", nil)
	require.NoError(t, err)
	mux.ServeHTTP(rec, req)
	assert.Equal(t, http.StatusServiceUnavailable, rec.Code)
	assert.Contains(t, rec.Body.String(), "degraded")
}
