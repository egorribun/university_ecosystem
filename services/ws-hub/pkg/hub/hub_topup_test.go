package hub

import (
	"context"
	"encoding/json"
	"errors"
	"hash"
	"log/slog"
	"os"
	"testing"
	"time"

	"github.com/nats-io/nats.go"
	"github.com/prometheus/client_golang/prometheus/testutil"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"github.com/university-ecosystem/ws-hub/pkg/config"
	"go.opentelemetry.io/otel"
)

func TestSafeJetStreamHelpers_RecordSuccessfulOperations(t *testing.T) {
	oldAck := jetStreamAckFunc
	oldNak := jetStreamNakFunc
	t.Cleanup(func() {
		jetStreamAckFunc = oldAck
		jetStreamNakFunc = oldNak
	})
	jetStreamAckFunc = func(*nats.Msg) error { return nil }
	jetStreamNakFunc = func(*nats.Msg, time.Duration) error { return nil }

	beforeAck := testutil.ToFloat64(JetStreamAcksTotal)
	beforeNak := testutil.ToFloat64(JetStreamNaksTotal)
	safeAck(&nats.Msg{})
	safeNakWithDelay(&nats.Msg{}, time.Second)
	assert.Equal(t, beforeAck+1, testutil.ToFloat64(JetStreamAcksTotal))
	assert.Equal(t, beforeNak+1, testutil.ToFloat64(JetStreamNaksTotal))
}

func TestNewHub_UsesConfiguredJetStreamAndRateSettings(t *testing.T) {
	cfg := &config.Config{
		BroadcastBufferSize:      7,
		MaxClients:               9,
		BroadcastWorkers:         3,
		InternalSecret:           "configured-secret",
		ClientMsgRateLimit:       2,
		ClientMsgRateBurst:       4,
		NatsStreamChat:           "chat-stream",
		NatsStreamNotifications:  "notification-stream",
		NatsDurableChat:          "chat-durable",
		NatsDurableNotifications: "notification-durable",
		EnableJetStream:          true,
	}
	h := NewHub(nil, slog.New(slog.NewTextHandler(os.Stderr, nil)), nil, cfg, nil)
	t.Cleanup(h.Stop)
	assert.Equal(t, 7, cap(h.Broadcast))
	assert.Equal(t, 9, h.maxClients)
	assert.Equal(t, 3, h.broadcastWorkers)
	assert.Equal(t, "configured-secret", h.internalSecret)
	assert.Equal(t, 2.0, h.clientMsgRateLimit)
	assert.Equal(t, 4, h.clientMsgRateBurst)
	assert.Equal(t, "chat-stream", h.streamChat)
	assert.Equal(t, "notification-stream", h.streamNotif)
	assert.Equal(t, "chat-durable", h.durableChat)
	assert.Equal(t, "notification-durable", h.durableNotif)
	assert.True(t, h.enableJetStream)
}

func TestNewHub_LoadsJetStreamContextWhenAvailable(t *testing.T) {
	server := newMockNatsServer(t)
	nc, err := nats.Connect(server.Addr())
	require.NoError(t, err)
	t.Cleanup(nc.Close)

	oldJetStream := jetStreamContextFunc
	t.Cleanup(func() { jetStreamContextFunc = oldJetStream })
	_, _ = oldJetStream(nc)
	jetStreamContextFunc = func(*nats.Conn) (nats.JetStreamContext, error) {
		return &scriptedJetStream{}, nil
	}
	h := NewHub(nc, slog.New(slog.NewTextHandler(os.Stderr, nil)), nil, &config.Config{EnableJetStream: true}, nil)
	t.Cleanup(h.Stop)
	assert.NotNil(t, h.js)
}

func TestHubContext_NilReceiverIsSafe(t *testing.T) {
	var h *Hub
	assert.Nil(t, h.Context())
}

func TestHubRun_UsesSafeWorkerMinimumAndQueueTicker(t *testing.T) {
	h := setupTestHub()
	h.broadcastWorkers = 0
	oldInterval := queueDepthInterval
	queueDepthInterval = time.Millisecond
	t.Cleanup(func() { queueDepthInterval = oldInterval })

	ctx, cancel := context.WithCancel(context.Background())
	done := make(chan struct{})
	go func() { h.Run(ctx); close(done) }()
	require.Eventually(t, func() bool { return h.Context() != nil }, time.Second, time.Millisecond)
	select {
	case <-time.After(20 * time.Millisecond):
	case <-done:
		t.Fatal("hub stopped before ticker branch could run")
	}
	cancel()
	select {
	case <-done:
	case <-time.After(time.Second):
		t.Fatal("hub did not stop after context cancellation")
	}
}

func TestHubRun_DropsWhenWorkerQueueIsFull(t *testing.T) {
	h := setupTestHub()
	h.Broadcast = make(chan *Message, 1)
	started := make(chan struct{})
	release := make(chan struct{})
	oldBroadcast := broadcastMessageFunc
	t.Cleanup(func() { broadcastMessageFunc = oldBroadcast })
	broadcastMessageFunc = func(*Hub, context.Context, *Message) {
		select {
		case <-started:
		default:
			close(started)
		}
		<-release
	}

	ctx, cancel := context.WithCancel(context.Background())
	done := make(chan struct{})
	go func() { h.Run(ctx); close(done) }()
	require.Eventually(t, func() bool { return h.Context() != nil }, time.Second, time.Millisecond)
	h.Broadcast <- &Message{Type: "first"}
	select {
	case <-started:
	case <-time.After(time.Second):
		t.Fatal("worker did not receive the first message")
	}
	before := testutil.ToFloat64(BroadcastDropsTotal)
	h.Broadcast <- &Message{Type: "queued"}
	h.Broadcast <- &Message{Type: "dropped"}
	require.Eventually(t, func() bool { return testutil.ToFloat64(BroadcastDropsTotal) >= before+1 }, time.Second, time.Millisecond)
	close(release)
	cancel()
	select {
	case <-done:
	case <-time.After(time.Second):
		t.Fatal("hub did not stop after queue test")
	}
}

func TestHubBroadcast_TraceAndMarshalErrorBranches(t *testing.T) {
	h := setupTestHub()
	_, span := otel.Tracer("hub-topup").Start(context.Background(), "topup")
	assert.Nil(t, h.collectRecipients(&Message{To: "missing"}, span))
	span.End()

	oldMarshal := hubJSONMarshalFunc
	t.Cleanup(func() { hubJSONMarshalFunc = oldMarshal })
	hubJSONMarshalFunc = func(any) ([]byte, error) { return nil, errors.New("marshal failed") }
	h.broadcastMessage(context.Background(), &Message{TraceCtx: map[string]string{"traceparent": "00-invalid"}})
}

func TestHubNATSHandlers_RecoverPanicsAndContainHMACFailures(t *testing.T) {
	const secret = "handler-topup-secret" // pragma: allowlist secret
	h := newNatsTestHub(nil, secret, 10)
	ctx := context.Background()
	oldUnmarshal := hubJSONUnmarshalFunc
	oldMarshal := hubJSONMarshalFunc
	oldHMACWrite := hmacWriteFunc
	t.Cleanup(func() {
		hubJSONUnmarshalFunc = oldUnmarshal
		hubJSONMarshalFunc = oldMarshal
		hmacWriteFunc = oldHMACWrite
	})

	hubJSONUnmarshalFunc = func([]byte, any) error { panic("synthetic decoder panic") }
	assert.NotPanics(t, func() {
		h.handleChat(ctx)(&nats.Msg{Subject: "chat.room", Data: []byte(`{"type":"message"}`)})
		h.handleNotifications(ctx)(&nats.Msg{Subject: "notifications.user", Data: []byte(`{"type":"message"}`)})
		h.handleCacheInvalidation(ctx)(&nats.Msg{Subject: "cache.invalidate", Data: []byte(`{"data":{},"signature":""}`)})
		h.handleControlMessage(ctx)(&nats.Msg{Subject: "ws_hub.control", Data: []byte(`{"data":{},"signature":""}`)})
	})

	hubJSONUnmarshalFunc = json.Unmarshal
	hubJSONMarshalFunc = func(any) ([]byte, error) { return nil, errors.New("synthetic marshal failure") }
	cachePayload := signedInvalidationPayload(t, secret, invalidationData{RoomID: "room", UserID: "user"})
	controlPayload := signedControlPayload(t, secret, testControlData{Action: "refresh", UserID: "user"})
	h.handleCacheInvalidation(ctx)(&nats.Msg{Subject: "cache.invalidate", Data: cachePayload})
	h.handleControlMessage(ctx)(&nats.Msg{Subject: "ws_hub.control", Data: controlPayload})

	hubJSONMarshalFunc = json.Marshal
	hmacWriteFunc = func(hash.Hash, []byte) (int, error) { return 0, errors.New("synthetic HMAC write failure") }
	h.handleCacheInvalidation(ctx)(&nats.Msg{Subject: "cache.invalidate", Data: cachePayload})
	h.handleControlMessage(ctx)(&nats.Msg{Subject: "ws_hub.control", Data: controlPayload})

	h.DisconnectUser("", 4401, "ignored")
}

func TestHubHandleRegister_LogsConnectionCloseFailureAtCapacity(t *testing.T) {
	h := setupTestHub()
	h.maxClients = 1
	h.Clients["existing"] = &Client{}
	c := &Client{ID: "rejected", Send: make(chan []byte, 1), Conn: &recordingSession{closeErr: errors.New("close failed")}}
	h.handleRegister(context.Background(), c)
	_, open := <-c.Send
	assert.False(t, open)
}

func TestHubLimiterCleanup_DefaultIntervalAndPanicRecovery(t *testing.T) {
	h := setupTestHub()
	h.limiterCleanupInterval = 0
	ctx, cancel := context.WithCancel(context.Background())
	h.StartLimiterCleanup(ctx)
	time.Sleep(5 * time.Millisecond)
	cancel()

	h.limiterCleanupInterval = time.Millisecond
	h.msgLimiters.Store("orphan", "valid-key-type")
	ctx, cancel = context.WithCancel(context.Background())
	h.StartLimiterCleanup(ctx)
	require.Eventually(t, func() bool {
		_, loaded := h.msgLimiters.Load("orphan")
		return !loaded
	}, time.Second, time.Millisecond)
	cancel()

	panicHub := setupTestHub()
	panicHub.limiterCleanupInterval = time.Millisecond
	panicHub.msgLimiters.Store(123, "wrong-key-type")
	panicCtx, panicCancel := context.WithCancel(context.Background())
	panicHub.StartLimiterCleanup(panicCtx)
	time.Sleep(20 * time.Millisecond)
	panicCancel()
}

func TestHubStop_CancelsLifecycleAndJWKS(t *testing.T) {
	h := setupTestHub()
	ctx := context.Background()
	done := make(chan struct{})
	go func() { h.Run(ctx); close(done) }()
	require.Eventually(t, func() bool { return h.Context() != nil }, time.Second, time.Millisecond)
	cancelled := false
	h.jwksCacheCancel = func() { cancelled = true }
	h.Stop()
	assert.True(t, cancelled)
	select {
	case <-done:
	case <-time.After(time.Second):
		t.Fatal("hub run loop did not stop")
	}
}

func TestSubscribeToNATS_CoreSubscriptionFailuresAndRotationCallback(t *testing.T) {
	server := newMockNatsServer(t)
	nc, err := nats.Connect(server.Addr())
	require.NoError(t, err)
	t.Cleanup(nc.Close)

	for _, subject := range []string{"notifications.*", "cache.invalidate", "ws_hub.control"} {
		t.Run(subject, func(t *testing.T) {
			oldSubscribe := coreNATSSubscribeFunc
			t.Cleanup(func() { coreNATSSubscribeFunc = oldSubscribe })
			coreNATSSubscribeFunc = func(conn *nats.Conn, candidate string, handler nats.MsgHandler) (*nats.Subscription, error) {
				if candidate == subject {
					return nil, errors.New("scripted subscription failure")
				}
				return conn.Subscribe(candidate, handler)
			}
			h := setupTestHub()
			h.Nats = nc
			err := h.SubscribeToNATS(context.Background())
			assert.Error(t, err)
			h.Stop()
		})
	}

	t.Run("keys rotation subscription failure is advisory", func(t *testing.T) {
		oldSubscribe := coreNATSSubscribeFunc
		t.Cleanup(func() { coreNATSSubscribeFunc = oldSubscribe })
		coreNATSSubscribeFunc = func(conn *nats.Conn, subject string, handler nats.MsgHandler) (*nats.Subscription, error) {
			if subject == "keys.rotated" {
				return nil, errors.New("rotation subscription unavailable")
			}
			return conn.Subscribe(subject, handler)
		}
		h := setupTestHub()
		h.Nats = nc
		require.NoError(t, h.SubscribeToNATS(context.Background()))
		h.Stop()
	})

	t.Run("keys rotation callback", func(t *testing.T) {
		oldSubscribe := coreNATSSubscribeFunc
		t.Cleanup(func() { coreNATSSubscribeFunc = oldSubscribe })
		var rotationHandler nats.MsgHandler
		coreNATSSubscribeFunc = func(conn *nats.Conn, subject string, handler nats.MsgHandler) (*nats.Subscription, error) {
			if subject == "keys.rotated" {
				rotationHandler = handler
			}
			return conn.Subscribe(subject, handler)
		}
		h := setupTestHub()
		h.Nats = nc
		_lastJWKSForceRefreshUnix.Store(time.Now().Unix())
		require.NoError(t, h.SubscribeToNATS(context.Background()))
		require.NotNil(t, rotationHandler)
		rotationHandler(&nats.Msg{})
		h.Stop()
	})
}
