package hub

import (
	"context"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"log/slog"
	"os"
	"testing"
	"time"

	"github.com/gorilla/websocket"
	"github.com/nats-io/nats.go"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"github.com/university-ecosystem/ws-hub/pkg/config"
)

type testControlData struct {
	Action    string `json:"action"`
	Reason    string `json:"reason"`
	Timestamp uint64 `json:"timestamp"`
	UserID    string `json:"user_id"`
}

func signedControlPayload(t *testing.T, secret string, data testControlData) []byte {
	t.Helper()
	dataBytes, err := json.Marshal(data)
	require.NoError(t, err)

	mac := hmac.New(sha256.New, []byte(secret))
	_, err = mac.Write(dataBytes)
	require.NoError(t, err)
	signature := hex.EncodeToString(mac.Sum(nil))

	full, err := json.Marshal(map[string]any{
		"data":      data,
		"signature": signature,
	})
	require.NoError(t, err)
	return full
}

func TestHandleControlMessage_ValidSignature_DisconnectsClient(t *testing.T) {
	secret := "control-test-secret-32-bytes-long!!" // pragma: allowlist secret
	logger := slog.New(slog.NewTextHandler(os.Stdout, nil))
	cfg := &config.Config{
		MaxClients:          10,
		BroadcastBufferSize: 10,
		BroadcastWorkers:    1,
		InternalSecret:      secret,
	}
	mockAuth := &mockAuthClient{allowed: true}
	h := trackTestHub(NewHub(nil, logger, mockAuth, cfg, nil))

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	go h.Run(ctx)

	serverConn, clientConn := newConnPair(t)
	sess := NewWebSocketSession(serverConn)

	clientCtx, clientCancel := context.WithCancel(ctx)
	defer clientCancel()

	c := &Client{
		ID:       "client-101",
		UserID:   "user-101",
		TenantID: "tenant-1",
		Conn:     sess,
		Rooms:    make(map[string]bool),
		Send:     make(chan []byte, 10),
		Hub:      h,
		ctx:      clientCtx,
		cancel:   clientCancel,
	}

	h.handleRegister(ctx, c)

	h.mu.RLock()
	_, exists := h.Clients["client-101"]
	h.mu.RUnlock()
	require.True(t, exists, "client should be registered initially")

	payload := signedControlPayload(t, secret, testControlData{
		Action:    "disconnect",
		Reason:    "access_revoked",
		Timestamp: 1700000000000,
		UserID:    "user-101",
	})

	handler := h.handleControlMessage(ctx)
	handler(&nats.Msg{
		Subject: "ws_hub.control",
		Data:    payload,
	})

	// Client socket should receive close frame 4401 with reason "Access Revoked"
	//nolint:errcheck
	_ = clientConn.SetReadDeadline(time.Now().Add(2 * time.Second))
	_, _, err := clientConn.ReadMessage()
	require.Error(t, err)

	closeErr, isCloseErr := err.(*websocket.CloseError)
	require.True(t, isCloseErr, "expected *websocket.CloseError, got %T: %v", err, err)
	assert.Equal(t, 4401, closeErr.Code, "close code should be 4401")
	assert.Contains(t, closeErr.Text, "Access Revoked", "close text should indicate Access Revoked")

	// Client should be evicted from Hub.Clients
	require.Eventually(t, func() bool {
		h.mu.RLock()
		defer h.mu.RUnlock()
		_, ok := h.Clients["client-101"]
		return !ok
	}, 2*time.Second, 20*time.Millisecond, "client should be evicted from Hub.Clients")
}

func TestHandleControlMessage_InvalidSignature_MessageRejected(t *testing.T) {
	secret := "correct-internal-secret" // pragma: allowlist secret
	logger := slog.New(slog.NewTextHandler(os.Stdout, nil))
	cfg := &config.Config{
		MaxClients:          10,
		BroadcastBufferSize: 10,
		BroadcastWorkers:    1,
		InternalSecret:      secret,
	}
	h := trackTestHub(NewHub(nil, logger, &mockAuthClient{allowed: true}, cfg, nil))

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	go h.Run(ctx)

	serverConn, clientConn := newConnPair(t)
	sess := NewWebSocketSession(serverConn)

	clientCtx, clientCancel := context.WithCancel(ctx)
	defer clientCancel()

	c := &Client{
		ID:     "client-202",
		UserID: "user-202",
		Conn:   sess,
		Rooms:  make(map[string]bool),
		Send:   make(chan []byte, 10),
		Hub:    h,
		ctx:    clientCtx,
		cancel: clientCancel,
	}

	h.handleRegister(ctx, c)

	payload := signedControlPayload(t, "WRONG-SECRET", testControlData{
		Action:    "disconnect",
		Reason:    "access_revoked",
		Timestamp: 1700000000000,
		UserID:    "user-202",
	})

	handler := h.handleControlMessage(ctx)
	handler(&nats.Msg{
		Subject: "ws_hub.control",
		Data:    payload,
	})

	// Verify client connection remains active in Hub.Clients
	h.mu.RLock()
	_, exists := h.Clients["client-202"]
	h.mu.RUnlock()
	assert.True(t, exists, "client with bad signature should NOT be evicted")

	// Connection socket remains open
	err := serverConn.WriteMessage(websocket.TextMessage, []byte(`{"type":"ping"}`))
	assert.NoError(t, err)

	//nolint:errcheck
	_ = clientConn.SetReadDeadline(time.Now().Add(1 * time.Second))
	msgType, data, err := clientConn.ReadMessage()
	assert.NoError(t, err)
	assert.Equal(t, websocket.TextMessage, msgType)
	assert.Equal(t, `{"type":"ping"}`, string(data))
}

func TestHandleControlMessage_MalformedJSON_NoPanic(t *testing.T) {
	secret := "control-test-secret" // pragma: allowlist secret
	logger := slog.New(slog.NewTextHandler(os.Stdout, nil))
	cfg := &config.Config{
		InternalSecret: secret,
	}
	h := trackTestHub(NewHub(nil, logger, &mockAuthClient{allowed: true}, cfg, nil))

	ctx := context.Background()
	handler := h.handleControlMessage(ctx)

	// Should not panic on garbage bytes
	assert.NotPanics(t, func() {
		handler(&nats.Msg{
			Subject: "ws_hub.control",
			Data:    []byte("invalid json data string"),
		})
	})

	// Should not panic on bad hex signature
	badHexPayload, err := json.Marshal(map[string]any{
		"data": testControlData{
			Action:    "disconnect",
			Reason:    "access_revoked",
			Timestamp: 1700000000000,
			UserID:    "user-300",
		},
		"signature": "NOT-HEX-GGGG",
	})
	require.NoError(t, err)
	assert.NotPanics(t, func() {
		handler(&nats.Msg{
			Subject: "ws_hub.control",
			Data:    badHexPayload,
		})
	})
}

func TestDisconnectUser_MultipleSessionsForUser(t *testing.T) {
	logger := slog.New(slog.NewTextHandler(os.Stdout, nil))
	cfg := &config.Config{
		MaxClients:          10,
		BroadcastBufferSize: 10,
		BroadcastWorkers:    1,
	}
	h := trackTestHub(NewHub(nil, logger, &mockAuthClient{allowed: true}, cfg, nil))

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	go h.Run(ctx)

	srv1, cli1 := newConnPair(t)
	srv2, cli2 := newConnPair(t)

	c1Ctx, cancel1 := context.WithCancel(ctx)
	defer cancel1()
	c2Ctx, cancel2 := context.WithCancel(ctx)
	defer cancel2()

	c1 := &Client{
		ID:     "c-301a",
		UserID: "user-301",
		Conn:   NewWebSocketSession(srv1),
		Rooms:  make(map[string]bool),
		Send:   make(chan []byte, 10),
		Hub:    h,
		ctx:    c1Ctx,
		cancel: cancel1,
	}
	c2 := &Client{
		ID:     "c-301b",
		UserID: "user-301",
		Conn:   NewWebSocketSession(srv2),
		Rooms:  make(map[string]bool),
		Send:   make(chan []byte, 10),
		Hub:    h,
		ctx:    c2Ctx,
		cancel: cancel2,
	}

	h.handleRegister(ctx, c1)
	h.handleRegister(ctx, c2)

	h.mu.RLock()
	assert.Len(t, h.Clients, 2)
	h.mu.RUnlock()

	h.DisconnectUser("user-301", 4401, "Access Revoked")

	// Both client sockets should receive close frame 4401
	assert.NoError(t, cli1.SetReadDeadline(time.Now().Add(2*time.Second)))
	_, _, err1 := cli1.ReadMessage()
	require.Error(t, err1)
	closeErr1, ok1 := err1.(*websocket.CloseError)
	require.True(t, ok1)
	assert.Equal(t, 4401, closeErr1.Code)

	assert.NoError(t, cli2.SetReadDeadline(time.Now().Add(2*time.Second)))
	_, _, err2 := cli2.ReadMessage()
	require.Error(t, err2)
	closeErr2, ok2 := err2.(*websocket.CloseError)
	require.True(t, ok2)
	assert.Equal(t, 4401, closeErr2.Code)

	// Both clients should be evicted
	require.Eventually(t, func() bool {
		h.mu.RLock()
		defer h.mu.RUnlock()
		return len(h.Clients) == 0
	}, 2*time.Second, 20*time.Millisecond)
}
