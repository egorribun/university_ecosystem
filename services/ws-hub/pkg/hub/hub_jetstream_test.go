package hub

import (
	"context"
	"encoding/json"
	"testing"

	"github.com/nats-io/nats.go"
	"github.com/prometheus/client_golang/prometheus/testutil"
	"github.com/stretchr/testify/assert"
	"github.com/university-ecosystem/ws-hub/pkg/config"
)

func TestJetStreamConfigOptions(t *testing.T) {
	t.Setenv("NATS_STREAM_CHAT", "CUSTOM_CHAT")
	t.Setenv("NATS_STREAM_NOTIFICATIONS", "CUSTOM_NOTIF")
	t.Setenv("NATS_DURABLE_CHAT", "custom-durable-chat")
	t.Setenv("NATS_DURABLE_NOTIFICATIONS", "custom-durable-notif")
	t.Setenv("ENABLE_JETSTREAM", "true")

	cfg := config.LoadConfig()
	assert.Equal(t, "CUSTOM_CHAT", cfg.NatsStreamChat)
	assert.Equal(t, "CUSTOM_NOTIF", cfg.NatsStreamNotifications)
	assert.Equal(t, "custom-durable-chat", cfg.NatsDurableChat)
	assert.Equal(t, "custom-durable-notif", cfg.NatsDurableNotifications)
	assert.True(t, cfg.EnableJetStream)
}

func TestHandleChat_Deduplication(t *testing.T) {
	h := newNatsTestHub(&mockAuthClient{allowed: true}, "", 10)
	handler := h.handleChat(context.Background())

	header := make(nats.Header)
	header.Set("Nats-Msg-Id", "unique-msg-100")

	payload := []byte(`{"type":"new_message","room":"room-dedup","payload":{"text":"test"}}`)
	msg1 := &nats.Msg{
		Subject: "chat.room-dedup",
		Header:  header,
		Data:    payload,
	}

	beforeHits := testutil.ToFloat64(JetStreamDedupHitsTotal)

	// First time: message should be accepted and broadcast
	handler(msg1)
	out1 := recvBroadcast(t, h)
	assert.Equal(t, "new_message", out1.Type)
	assert.Equal(t, "room-dedup", out1.Room)

	// Second time with same Nats-Msg-Id: message should be dropped as duplicate
	msg2 := &nats.Msg{
		Subject: "chat.room-dedup",
		Header:  header,
		Data:    payload,
	}
	handler(msg2)

	// Ensure dedup counter incremented
	afterHits := testutil.ToFloat64(JetStreamDedupHitsTotal)
	assert.Equal(t, beforeHits+1, afterHits, "JetStreamDedupHitsTotal should increment on duplicate message")

	// Ensure no second broadcast message was queued
	select {
	case msg := <-h.Broadcast:
		t.Fatalf("expected duplicate message to be dropped, but received: %+v", msg)
	default:
	}
}

func TestHandleNotifications_Deduplication(t *testing.T) {
	h := newNatsTestHub(&mockAuthClient{allowed: true}, "", 10)
	handler := h.handleNotifications(context.Background())

	header := make(nats.Header)
	header.Set("Nats-Msg-Id", "notif-msg-200")

	payload := []byte(`{"to":"user-10","payload":{"title":"alert"}}`)
	msg1 := &nats.Msg{
		Subject: "notifications.user-10",
		Header:  header,
		Data:    payload,
	}

	beforeHits := testutil.ToFloat64(JetStreamDedupHitsTotal)

	handler(msg1)
	out1 := recvBroadcast(t, h)
	assert.Equal(t, "notification", out1.Type)

	// Second delivery of duplicate notification
	msg2 := &nats.Msg{
		Subject: "notifications.user-10",
		Header:  header,
		Data:    payload,
	}
	handler(msg2)

	afterHits := testutil.ToFloat64(JetStreamDedupHitsTotal)
	assert.Equal(t, beforeHits+1, afterHits)

	select {
	case msg := <-h.Broadcast:
		t.Fatalf("expected duplicate notification to be dropped, got: %+v", msg)
	default:
	}
}

func TestHandleJoin_WithLastSeqAndMsgID(t *testing.T) {
	h := newNatsTestHub(&mockAuthClient{allowed: true}, "", 10)
	client := &Client{
		ID:     "client-replay",
		UserID: "user-replay",
		Rooms:  make(map[string]bool),
		Send:   make(chan []byte, 10),
		Hub:    h,
		ctx:    context.Background(),
	}

	// Joining with room and last_seq parameter inside payload JSON
	joinMsg := Message{
		Type:    "join",
		Room:    "room-replay",
		Payload: json.RawMessage(`{"last_seq": 42, "last_msg_id": "msg-42"}`),
	}

	client.handleJoin(joinMsg)

	client.mu.Lock()
	inRoom := client.Rooms["room-replay"]
	client.mu.Unlock()
	assert.True(t, inRoom, "client should be registered in room-replay")
}

func TestHandleChat_BroadcastFull_NotCachedAndNaked(t *testing.T) {
	h := newNatsTestHub(&mockAuthClient{allowed: true}, "", 1)
	handler := h.handleChat(context.Background())

	header := make(nats.Header)
	header.Set("Nats-Msg-Id", "full-queue-msg-1")

	payload := []byte(`{"type":"new_message","room":"room-full","payload":{"text":"test"}}`)
	msg1 := &nats.Msg{
		Subject: "chat.room-full",
		Header:  header,
		Data:    payload,
	}

	// Fill the broadcast channel so it's full
	h.Broadcast <- &Message{Type: "dummy"}

	// Dispatch msg1 when broadcast buffer is full
	handler(msg1)

	// Verify msg1 was NOT added to dedupCache
	_, found := h.dedupCache.Get("full-queue-msg-1")
	assert.False(t, found, "msgID should NOT be cached when broadcast buffer is full")

	// Drain the dummy message
	dummy := <-h.Broadcast
	assert.Equal(t, "dummy", dummy.Type)

	// Redeliver msg1 (simulating NAK redelivery)
	handler(msg1)

	// Now msg1 should be in h.Broadcast and cached in dedupCache
	out := recvBroadcast(t, h)
	assert.Equal(t, "new_message", out.Type)
	assert.Equal(t, "room-full", out.Room)

	_, foundAfter := h.dedupCache.Get("full-queue-msg-1")
	assert.True(t, foundAfter, "msgID SHOULD be cached after successful push to Broadcast")
}

func TestHandleNotifications_BroadcastFull_NotCachedAndNaked(t *testing.T) {
	h := newNatsTestHub(&mockAuthClient{allowed: true}, "", 1)
	handler := h.handleNotifications(context.Background())

	header := make(nats.Header)
	header.Set("Nats-Msg-Id", "notif-full-msg-1")

	payload := []byte(`{"to":"user-full","payload":{"title":"alert"}}`)
	msg1 := &nats.Msg{
		Subject: "notifications.user-full",
		Header:  header,
		Data:    payload,
	}

	// Fill broadcast buffer
	h.Broadcast <- &Message{Type: "dummy"}

	handler(msg1)

	_, found := h.dedupCache.Get("notif-full-msg-1")
	assert.False(t, found, "notification msgID should NOT be cached when broadcast buffer is full")

	<-h.Broadcast // drain dummy

	handler(msg1) // redelivery

	out := recvBroadcast(t, h)
	assert.Equal(t, "notification", out.Type)

	_, foundAfter := h.dedupCache.Get("notif-full-msg-1")
	assert.True(t, foundAfter, "notification msgID SHOULD be cached after successful enqueue")
}

func TestClient_HandleMessage_JetStreamDisabledFallback(t *testing.T) {
	server := newMockNatsServer(t)
	nc, err := nats.Connect(server.Addr())
	assert.NoError(t, err)
	t.Cleanup(nc.Close)

	h := setupTestHub()
	h.Nats = nc
	h.enableJetStream = false // JetStream disabled

	c := &Client{
		ID:     "c-no-js",
		UserID: "u-no-js",
		Hub:    h,
		ctx:    context.Background(),
		Send:   make(chan []byte, 10),
	}

	msg := Message{Type: "message", Room: "room-fallback"}
	data := []byte(`{"text":"hello"}`)

	assert.NotPanics(t, func() {
		c.handleMessage(msg, data)
	})
}

func TestClient_ReplayOfflineMessages_ContextCancelled(t *testing.T) {
	h := setupTestHub()
	ctx, cancel := context.WithCancel(context.Background())
	cancel() // pre-cancelled context

	c := &Client{
		ID:     "c-cancelled",
		UserID: "u-cancelled",
		Hub:    h,
		ctx:    ctx,
		Send:   make(chan []byte, 10),
	}

	assert.NotPanics(t, func() {
		c.replayOfflineMessages("room-cancel", 0, "msg-1")
	})
}

