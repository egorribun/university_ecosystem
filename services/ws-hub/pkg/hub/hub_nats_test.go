package hub

// Coverage tests (testing session 9) for the NATS message handlers, the
// Run loop + broadcastMessage fan-out and Stop idempotency.
//
// The NATS handler closures (handleChat / handleNotifications /
// handleCacheInvalidation) are invoked DIRECTLY with synthetic *nats.Msg
// values — no NATS connection is needed. msg.Reply is left empty so the
// JetStream NakWithDelay branch is never reached (it would require a live
// connection).

import (
	"context"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"log/slog"
	"os"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/nats-io/nats.go"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"github.com/university-ecosystem/ws-hub/pkg/config"
)

// recordingAuthClient records Invalidate calls; mutex-guarded for -race.
type recordingAuthClient struct {
	mu          sync.Mutex
	invalidated [][2]string
}

func (r *recordingAuthClient) CanJoinRoom(_ context.Context, _, _ string) bool { return true }

func (r *recordingAuthClient) Invalidate(userID, room string) {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.invalidated = append(r.invalidated, [2]string{userID, room})
}

func (r *recordingAuthClient) calls() [][2]string {
	r.mu.Lock()
	defer r.mu.Unlock()
	out := make([][2]string, len(r.invalidated))
	copy(out, r.invalidated)
	return out
}

func newNatsTestHub(auth RoomAuthClient, secret string, broadcastCap int) *Hub {
	logger := slog.New(slog.NewTextHandler(os.Stdout, nil))
	cfg := &config.Config{
		MaxClients:          10,
		BroadcastBufferSize: broadcastCap,
		BroadcastWorkers:    1,
		ClientMsgRateLimit:  10,
		ClientMsgRateBurst:  10,
		InternalSecret:      secret,
	}
	return NewHub(nil, logger, auth, cfg, nil)
}

func recvBroadcast(t *testing.T, h *Hub) *Message {
	t.Helper()
	select {
	case msg := <-h.Broadcast:
		return msg
	case <-time.After(2 * time.Second):
		t.Fatal("expected a message on h.Broadcast")
		return nil
	}
}

// ---------------------------------------------------------------------------
// handleChat
// ---------------------------------------------------------------------------

func TestHandleChat_ValidMessageLandsOnBroadcast(t *testing.T) {
	h := newNatsTestHub(&mockAuthClient{allowed: true}, "", 10)
	handler := h.handleChat(context.Background())

	payload := []byte(`{"type":"new_message","room":"room-1","payload":{"text":"hi"}}`)
	handler(&nats.Msg{Subject: "chat.room-1", Data: payload})

	msg := recvBroadcast(t, h)
	assert.Equal(t, "new_message", msg.Type)
	assert.Equal(t, "room-1", msg.Room)
}

func TestHandleChat_MalformedJSONDropped(t *testing.T) {
	h := newNatsTestHub(&mockAuthClient{allowed: true}, "", 10)
	handler := h.handleChat(context.Background())

	handler(&nats.Msg{Subject: "chat.room-1", Data: []byte("{not-json")})

	select {
	case msg := <-h.Broadcast:
		t.Fatalf("expected no broadcast for malformed payload, got %+v", msg)
	default:
	}
}

func TestHandleChat_CancelledContextReturnsEarly(t *testing.T) {
	h := newNatsTestHub(&mockAuthClient{allowed: true}, "", 10)
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	handler := h.handleChat(ctx)

	handler(&nats.Msg{Subject: "chat.room-1", Data: []byte(`{"type":"x"}`)})

	select {
	case msg := <-h.Broadcast:
		t.Fatalf("expected no broadcast after context cancel, got %+v", msg)
	default:
	}
}

func TestHandleChat_FullChannelDropsWithoutNak(t *testing.T) {
	h := newNatsTestHub(&mockAuthClient{allowed: true}, "", 1)
	handler := h.handleChat(context.Background())

	// Fill the capacity-1 channel, then deliver a second message.
	handler(&nats.Msg{Subject: "chat.a", Data: []byte(`{"type":"first","room":"a"}`)})
	handler(&nats.Msg{Subject: "chat.a", Data: []byte(`{"type":"second","room":"a"}`)})

	first := recvBroadcast(t, h)
	assert.Equal(t, "first", first.Type)
	select {
	case msg := <-h.Broadcast:
		t.Fatalf("second message should have been dropped, got %+v", msg)
	default:
	}
}

// ---------------------------------------------------------------------------
// handleNotifications
// ---------------------------------------------------------------------------

func TestHandleNotifications_OverridesType(t *testing.T) {
	h := newNatsTestHub(&mockAuthClient{allowed: true}, "", 10)
	handler := h.handleNotifications(context.Background())

	payload := []byte(`{"type":"whatever","to":"user-1","payload":{"title":"t"}}`)
	handler(&nats.Msg{Subject: "notifications.user-1", Data: payload})

	msg := recvBroadcast(t, h)
	assert.Equal(t, "notification", msg.Type)
	assert.Equal(t, "user-1", msg.To)
}

func TestHandleNotifications_MalformedDropped(t *testing.T) {
	h := newNatsTestHub(&mockAuthClient{allowed: true}, "", 10)
	handler := h.handleNotifications(context.Background())

	handler(&nats.Msg{Subject: "notifications.u", Data: []byte("not json")})

	select {
	case <-h.Broadcast:
		t.Fatal("expected malformed notification to be dropped")
	default:
	}
}

// ---------------------------------------------------------------------------
// handleCacheInvalidation — HMAC-signed internal events
// ---------------------------------------------------------------------------

type invalidationData struct {
	RoomID    string `json:"room_id"`
	Timestamp uint64 `json:"timestamp"`
	UserID    string `json:"user_id"`
}

func signedInvalidationPayload(t *testing.T, secret string, data invalidationData) []byte {
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

func TestHandleCacheInvalidation_ValidSignature(t *testing.T) {
	auth := &recordingAuthClient{}
	h := newNatsTestHub(auth, "internal-secret", 10) // pragma: allowlist secret
	handler := h.handleCacheInvalidation(context.Background())

	payload := signedInvalidationPayload(t, "internal-secret",
		invalidationData{RoomID: "room-9", Timestamp: 1234, UserID: "user-9"})
	handler(&nats.Msg{Subject: "cache.invalidate", Data: payload})

	calls := auth.calls()
	require.Len(t, calls, 1)
	assert.Equal(t, [2]string{"user-9", "room-9"}, calls[0])
}

func TestHandleCacheInvalidation_BadSignatureDropped(t *testing.T) {
	auth := &recordingAuthClient{}
	h := newNatsTestHub(auth, "internal-secret", 10) // pragma: allowlist secret
	handler := h.handleCacheInvalidation(context.Background())

	payload := signedInvalidationPayload(t, "WRONG-secret",
		invalidationData{RoomID: "room-9", Timestamp: 1234, UserID: "user-9"})
	handler(&nats.Msg{Subject: "cache.invalidate", Data: payload})

	assert.Empty(t, auth.calls())
}

func TestHandleCacheInvalidation_MalformedAndBadHexDropped(t *testing.T) {
	auth := &recordingAuthClient{}
	h := newNatsTestHub(auth, "internal-secret", 10) // pragma: allowlist secret
	handler := h.handleCacheInvalidation(context.Background())

	handler(&nats.Msg{Subject: "cache.invalidate", Data: []byte("{broken")})

	// Valid JSON but non-hex signature → hex decode error branch.
	data, err := json.Marshal(map[string]any{
		"data":      invalidationData{RoomID: "r", Timestamp: 1, UserID: "u"},
		"signature": "zz-not-hex",
	})
	require.NoError(t, err)
	handler(&nats.Msg{Subject: "cache.invalidate", Data: data})

	assert.Empty(t, auth.calls())
}

// ---------------------------------------------------------------------------
// Run loop + broadcastMessage fan-out
// ---------------------------------------------------------------------------

func startHubRunLoop(t *testing.T, h *Hub) (context.CancelFunc, chan struct{}) {
	t.Helper()
	ctx, cancel := context.WithCancel(context.Background())
	done := make(chan struct{})
	go func() {
		defer close(done)
		h.Run(ctx)
	}()
	return cancel, done
}

func registerLoopClient(t *testing.T, h *Hub, id string, sendCap int) *Client {
	t.Helper()
	client := &Client{
		ID:    id,
		Rooms: make(map[string]bool),
		Send:  make(chan []byte, sendCap),
		Hub:   h,
		ctx:   context.Background(),
	}
	select {
	case h.Register <- client:
	case <-time.After(2 * time.Second):
		t.Fatal("Run loop did not consume Register")
	}
	require.Eventually(t, func() bool {
		h.mu.RLock()
		defer h.mu.RUnlock()
		_, ok := h.Clients[id]
		return ok
	}, 2*time.Second, 10*time.Millisecond)
	return client
}

func recvSend(t *testing.T, c *Client) Message {
	t.Helper()
	select {
	case data := <-c.Send:
		var msg Message
		require.NoError(t, json.Unmarshal(data, &msg))
		return msg
	case <-time.After(2 * time.Second):
		t.Fatalf("client %s did not receive a message", c.ID)
		return Message{}
	}
}

func TestRunLoop_RoomDirectAndGlobalDelivery(t *testing.T) {
	h := newNatsTestHub(&mockAuthClient{allowed: true}, "", 10)
	cancel, done := startHubRunLoop(t, h)
	defer func() { cancel(); <-done }()

	alice := registerLoopClient(t, h, "alice", 8)
	bob := registerLoopClient(t, h, "bob", 8)

	// Join alice to a room directly under the documented lock hierarchy.
	h.mu.Lock()
	h.Rooms["room-1"] = map[*Client]bool{alice: true}
	h.mu.Unlock()
	alice.mu.Lock()
	alice.Rooms["room-1"] = true
	alice.mu.Unlock()

	// Room-scoped: only alice receives.
	h.Broadcast <- &Message{Type: "room-msg", Room: "room-1", Payload: []byte(`{}`)}
	got := recvSend(t, alice)
	assert.Equal(t, "room-msg", got.Type)

	// Direct: only bob receives.
	h.Broadcast <- &Message{Type: "direct-msg", To: "bob", Payload: []byte(`{}`)}
	got = recvSend(t, bob)
	assert.Equal(t, "direct-msg", got.Type)

	// Global: both receive.
	h.Broadcast <- &Message{Type: "global-msg", Payload: []byte(`{}`)}
	assert.Equal(t, "global-msg", recvSend(t, alice).Type)
	assert.Equal(t, "global-msg", recvSend(t, bob).Type)
}

func TestRunLoop_OversizedBroadcastDropped(t *testing.T) {
	h := newNatsTestHub(&mockAuthClient{allowed: true}, "", 10)
	cancel, done := startHubRunLoop(t, h)
	defer func() { cancel(); <-done }()

	alice := registerLoopClient(t, h, "alice", 8)

	// Oversized (>60 KB once marshalled) then a small follow-up: only the
	// follow-up must arrive, proving the oversized one was dropped.
	big := strings.Repeat("x", 61*1024)
	payload, err := json.Marshal(map[string]string{"blob": big})
	require.NoError(t, err)
	h.Broadcast <- &Message{Type: "oversized", Payload: payload}
	h.Broadcast <- &Message{Type: "small", Payload: []byte(`{}`)}

	got := recvSend(t, alice)
	assert.Equal(t, "small", got.Type)
}

func TestRunLoop_GlobalBroadcastEvictsFullClient(t *testing.T) {
	h := newNatsTestHub(&mockAuthClient{allowed: true}, "", 10)
	cancel, done := startHubRunLoop(t, h)
	defer func() { cancel(); <-done }()

	healthy := registerLoopClient(t, h, "healthy", 8)
	// Unbuffered Send channel with no reader → safeSend fails → evictOnFull.
	stuck := registerLoopClient(t, h, "stuck", 0)
	_ = stuck

	h.Broadcast <- &Message{Type: "global", Payload: []byte(`{}`)}
	assert.Equal(t, "global", recvSend(t, healthy).Type)

	require.Eventually(t, func() bool {
		h.mu.RLock()
		defer h.mu.RUnlock()
		_, ok := h.Clients["stuck"]
		return !ok
	}, 2*time.Second, 10*time.Millisecond, "stuck client should be evicted")
}

// ---------------------------------------------------------------------------
// Stop / HasJWKSCache
// ---------------------------------------------------------------------------

func TestStop_IsIdempotent(t *testing.T) {
	h := newNatsTestHub(&mockAuthClient{allowed: true}, "", 10)
	h.Stop()
	h.Stop() // second call must be a no-op (stopOnce)
}

func TestHasJWKSCache_FalseWithoutSetup(t *testing.T) {
	h := newNatsTestHub(&mockAuthClient{allowed: true}, "", 10)
	assert.False(t, h.HasJWKSCache())
}
