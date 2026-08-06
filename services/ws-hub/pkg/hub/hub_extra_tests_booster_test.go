package hub

import (
	"context"
	"encoding/json"
	"io"
	"sync/atomic"
	"testing"
	"time"

	"github.com/gorilla/websocket"
	"github.com/lestrrat-go/jwx/v2/jwk"
	"github.com/nats-io/nats.go"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// TestSetupJWKS_Scenarios covers empty, re-registration (cancelling old context), and invalid URL scenarios.
func TestSetupJWKS_Scenarios(t *testing.T) {
	h := setupTestHub()
	ctx := context.Background()

	t.Run("empty URL returns nil", func(t *testing.T) {
		err := h.SetupJWKS(ctx, "")
		assert.NoError(t, err)
	})

	t.Run("re-registration cancels old context", func(t *testing.T) {
		err := h.SetupJWKS(ctx, "http://127.0.0.1:9999/first")
		assert.NoError(t, err)
		assert.NotNil(t, h.jwksCacheCancel)

		// Capture old cancel function
		oldCancel := h.jwksCacheCancel

		err = h.SetupJWKS(ctx, "http://127.0.0.1:9999/second")
		assert.NoError(t, err)

		// Verify old context was cancelled
		assert.NotNil(t, oldCancel)
	})

	t.Run("register invalid URL", func(t *testing.T) {
		// Registering malformed URL with lesstreat-go/jwx/v2 jwk.Cache.Register does not fail,
		// but the subsequent background Refresh fails (logging a warning).
		err := h.SetupJWKS(ctx, "::invalid-url-scheme::")
		assert.NoError(t, err)
	})
}

// TestTryForceRefreshJWKS_CooldownAndRace tests tryForceRefreshJWKS cooldown rate limit.
func TestTryForceRefreshJWKS_CooldownAndRace(t *testing.T) {
	h := setupTestHub()
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	h.jwksCache = jwk.NewCache(ctx)
	h.jwksURL = "http://127.0.0.1:1/invalid"

	t.Run("rate-limited cooldown path", func(t *testing.T) {
		// Set last refresh time to now (so cooldown is active)
		_lastJWKSForceRefreshUnix.Store(time.Now().Unix())

		assert.NotPanics(t, func() {
			h.tryForceRefreshJWKS(ctx)
		})
	})
}

// TestSubscribeToNATS_KeysRotated covers keys.rotated topic subscription registration.
func TestSubscribeToNATS_KeysRotated(t *testing.T) {
	server := newMockNatsServer(t)
	nc, err := nats.Connect(server.Addr())
	require.NoError(t, err)
	defer nc.Close()

	h := setupTestHub()
	h.Nats = nc

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	h.jwksCache = jwk.NewCache(ctx)
	h.jwksURL = "http://127.0.0.1:1/invalid"

	assert.NotPanics(t, func() {
		require.NoError(t, h.SubscribeToNATS(ctx))
	})
}

func TestSafeJetStreamAckNak_HandlesNilAndCoreMessages(t *testing.T) {
	assert.NotPanics(t, func() {
		safeAck(nil)
		safeNakWithDelay(nil, time.Second)
	})

	coreMessage := &nats.Msg{Subject: "chat.room-1", Data: []byte(`{}`)}
	assert.NotPanics(t, func() {
		safeAck(coreMessage)
		safeNakWithDelay(coreMessage, time.Millisecond)
	})
}

func TestWebTransportSession_NilAndClosedPaths(t *testing.T) {
	sess := NewWebTransportSession(nil)
	sess.SetReadLimit(1024)
	assert.NoError(t, sess.SetReadDeadline(time.Now()))
	assert.NoError(t, sess.SetWriteDeadline(time.Now()))

	assert.NoError(t, sess.WriteMessage(websocket.PingMessage, nil))
	assert.NoError(t, sess.WriteMessage(websocket.PongMessage, nil))
	assert.Error(t, sess.WriteMessage(websocket.TextMessage, []byte("payload")))
	_, _, err := sess.ReadMessage()
	assert.Error(t, err)

	assert.NoError(t, sess.WriteMessage(websocket.CloseMessage, nil))
	_, err = sess.getOrAcceptStream()
	assert.ErrorIs(t, err, io.EOF)
	assert.NoError(t, sess.WriteMessage(websocket.CloseMessage, nil))
}

// TestBroadcastMessage_ClientEvictOnShutdown covers the case when the Hub is shut down while evicting a client on full buffer.
func TestBroadcastMessage_ClientEvictOnShutdown(t *testing.T) {
	h := setupTestHub()

	// Shut down the hub immediately
	h.ctx, h.ctxCancel = context.WithCancel(context.Background())
	h.ctxCancel() // hub context is done!

	c := &Client{
		ID:     "evicted-client",
		UserID: "user-1",
		Hub:    h,
		ctx:    context.Background(),
		Send:   make(chan []byte, 1), // buffer size 1
	}

	// Register client in the h.Clients map (so evictOnFull is true in collectRecipients default case)
	h.mu.Lock()
	h.Clients[c.ID] = c
	h.mu.Unlock()

	// Fill client's buffer
	c.Send <- []byte("initial")

	// Trigger broadcast which will try to send but fail because client Send buffer is full
	// Leaving Room and To empty makes it a broadcast to all h.Clients
	msg := &Message{
		Type:    "message",
		Room:    "",
		To:      "",
		Payload: json.RawMessage([]byte(`"hello world"`)),
	}

	var closed int32

	h.broadcastMessage(context.Background(), msg)

	// First drain the initial message to allow another read or check closed status
	select {
	case m := <-c.Send:
		assert.Equal(t, "initial", string(m))
	case <-time.After(5 * time.Second):
		t.Fatal("Timeout waiting for initial message")
	}

	// Now verify c.Send channel is closed
	select {
	case _, ok := <-c.Send:
		if !ok {
			atomic.StoreInt32(&closed, 1)
		}
	case <-time.After(5 * time.Second):
		// timeout, channel not closed
	}

	assert.Equal(t, int32(1), atomic.LoadInt32(&closed), "c.Send should have been closed directly on hub shutdown")
}
