// Hub lifecycle, metrics, JetStream, and tracing contracts.
package hub

import (
	"context"
	"encoding/json"
	"errors"
	"hash"
	"log/slog"
	"os"
	"strings"
	"sync"
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

// AUD-477: a sequenced chat message that cannot be broadcast must not be
// acknowledged. The ACK would advance JetStream past a message no client
// receives, leaving a silent gap in the replay sequence.
func TestEnqueueChatDelivery_UndeliverableSequencedMessageIsNotAcknowledged(t *testing.T) {
	sequencedMessage := func(payloadBytes int) (*nats.Msg, *Message) {
		payload := json.RawMessage(`"` + strings.Repeat("x", payloadBytes) + `"`)
		wsMsg := &Message{
			Type:                  "chat_message",
			Room:                  "room-1",
			Payload:               payload,
			MessageReplayMetadata: &MessageReplayMetadata{Seq: 42, Stream: "CHAT_EVENTS"},
		}
		natsMsg := &nats.Msg{
			Subject: "chat.room-1",
			Reply:   "$JS.ACK.CHAT_EVENTS.ws-hub-chat.1.42.42.1700000000000000000.0",
		}
		return natsMsg, wsMsg
	}

	newHub := func(t *testing.T) *Hub {
		t.Helper()
		h := NewHub(nil, slog.New(slog.NewTextHandler(os.Stderr, nil)), nil,
			&config.Config{BroadcastBufferSize: 4, InternalSecret: strings.Repeat("cfg-", 16)}, nil)
		t.Cleanup(h.Stop)
		return h
	}

	t.Run("oversized sequenced message is terminated and never acknowledged", func(t *testing.T) {
		oldAck, oldTerm := jetStreamAckFunc, jetStreamTermFunc
		t.Cleanup(func() { jetStreamAckFunc, jetStreamTermFunc = oldAck, oldTerm })
		var acks, terms int
		jetStreamAckFunc = func(*nats.Msg) error { acks++; return nil }
		jetStreamTermFunc = func(*nats.Msg) error { terms++; return nil }

		h := newHub(t)
		// 60 KB payload plus the Message envelope exceeds the broadcast limit.
		natsMsg, wsMsg := sequencedMessage(60 * 1024)
		before := testutil.ToFloat64(BroadcastDropsTotal)
		h.enqueueChatDelivery(t.Context(), natsMsg, wsMsg, "", true)

		assert.Equal(t, 0, acks, "an undeliverable sequenced message must not be acknowledged")
		assert.Equal(t, 1, terms, "the poison message must be terminated, not redelivered")
		assert.Empty(t, h.Broadcast, "an undeliverable message must not reach the broadcast queue")
		assert.Equal(t, before+1, testutil.ToFloat64(BroadcastDropsTotal))
	})

	t.Run("deliverable sequenced message is enqueued and acknowledged", func(t *testing.T) {
		oldAck, oldTerm := jetStreamAckFunc, jetStreamTermFunc
		t.Cleanup(func() { jetStreamAckFunc, jetStreamTermFunc = oldAck, oldTerm })
		var acks, terms int
		jetStreamAckFunc = func(*nats.Msg) error { acks++; return nil }
		jetStreamTermFunc = func(*nats.Msg) error { terms++; return nil }

		h := newHub(t)
		natsMsg, wsMsg := sequencedMessage(1024)
		h.enqueueChatDelivery(t.Context(), natsMsg, wsMsg, "", true)

		assert.Equal(t, 1, acks)
		assert.Equal(t, 0, terms)
		assert.Len(t, h.Broadcast, 1)
	})

	t.Run("sequenced message that cannot be marshaled fails closed", func(t *testing.T) {
		oldAck, oldTerm, oldMarshal := jetStreamAckFunc, jetStreamTermFunc, hubJSONMarshalFunc
		t.Cleanup(func() {
			jetStreamAckFunc, jetStreamTermFunc, hubJSONMarshalFunc = oldAck, oldTerm, oldMarshal
		})
		var acks, terms int
		jetStreamAckFunc = func(*nats.Msg) error { acks++; return nil }
		jetStreamTermFunc = func(*nats.Msg) error { terms++; return nil }
		hubJSONMarshalFunc = func(any) ([]byte, error) { return nil, errors.New("synthetic marshal failure") }

		h := newHub(t)
		natsMsg, wsMsg := sequencedMessage(16)
		h.enqueueChatDelivery(t.Context(), natsMsg, wsMsg, "", true)

		assert.Equal(t, 0, acks)
		assert.Equal(t, 1, terms)
		assert.Empty(t, h.Broadcast)
	})
}

func TestNewHub_UsesConfiguredJetStreamAndRateSettings(t *testing.T) {
	cfg := &config.Config{
		BroadcastBufferSize:     7,
		MaxClients:              9,
		BroadcastWorkers:        3,
		InternalSecret:          strings.Repeat("cfg-", 16),
		ClientMsgRateLimit:      2,
		ClientMsgRateBurst:      4,
		NatsStreamChat:          "chat-stream",
		NatsStreamNotifications: "notification-stream",
		EnableJetStream:         true,
	}
	h := NewHub(nil, slog.New(slog.NewTextHandler(os.Stderr, nil)), nil, cfg, nil)
	t.Cleanup(h.Stop)
	assert.Equal(t, 7, cap(h.Broadcast))
	assert.Equal(t, 9, h.maxClients)
	assert.Equal(t, 3, h.broadcastWorkers)
	assert.Equal(t, strings.Repeat("cfg-", 16), h.internalSecret)
	assert.Equal(t, 2.0, h.clientMsgRateLimit)
	assert.Equal(t, 4, h.clientMsgRateBurst)
	assert.Equal(t, "chat-stream", h.streamChat)
	assert.Equal(t, "notification-stream", h.streamNotif)
	assert.True(t, h.enableJetStream)
}

func TestNewHub_LoadsJetStreamContextWhenAvailable(t *testing.T) {
	server := newMockNatsServer(t)
	nc, err := nats.Connect(server.Addr())
	require.NoError(t, err)
	t.Cleanup(nc.Close)

	oldJetStream := jetStreamContextFunc
	t.Cleanup(func() { jetStreamContextFunc = oldJetStream })
	_, jetStreamErr := oldJetStream(nc)
	require.NoError(t, jetStreamErr)
	jetStreamContextFunc = func(*nats.Conn) (nats.JetStreamContext, error) {
		return &scriptedJetStream{}, nil
	}
	h := NewHub(nc, slog.New(slog.NewTextHandler(os.Stderr, nil)), nil, &config.Config{EnableJetStream: true}, nil)
	t.Cleanup(h.Stop)
	assert.NotNil(t, h.js)
}

// hubLifecycleContext returns the hub's lifecycle context under lifecycleMu so
// tests can wait for Run to publish it without racing the writer.
func hubLifecycleContext(h *Hub) context.Context {
	h.lifecycleMu.Lock()
	defer h.lifecycleMu.Unlock()
	return h.ctx
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
	require.Eventually(t, func() bool { return hubLifecycleContext(h) != nil }, time.Second, time.Millisecond)
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
	require.Eventually(t, func() bool { return hubLifecycleContext(h) != nil }, time.Second, time.Millisecond)
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

func TestHubRun_DropsSequencedBroadcastAndCleansRoomWithoutBlocking(t *testing.T) {
	baseline := testutil.ToFloat64(ActiveConnections)
	t.Cleanup(func() { ActiveConnections.Set(baseline) })

	h := setupTestHub()
	t.Cleanup(h.Stop)
	h.Broadcast = make(chan *Message, 1)
	h.broadcastWorkers = 1
	room := "sequenced-overflow-room"
	clientCtx, cancelClient := context.WithCancel(context.Background())
	t.Cleanup(cancelClient)
	client := &Client{
		ID:     "sequenced-overflow-client",
		UserID: "sequenced-overflow-user",
		Hub:    h,
		Rooms:  make(map[string]bool),
		Send:   make(chan []byte, 1),
		ctx:    clientCtx,
		cancel: cancelClient,
	}
	h.handleRegister(context.Background(), client)
	client.JoinRoom(room)

	workerStarted := make(chan struct{})
	workerRelease := make(chan struct{})
	var releaseOnce sync.Once
	releaseWorker := func() { releaseOnce.Do(func() { close(workerRelease) }) }

	oldBroadcast := broadcastMessageFunc
	t.Cleanup(func() { broadcastMessageFunc = oldBroadcast })
	broadcastMessageFunc = func(_ *Hub, _ context.Context, msg *Message) {
		if msg.Seq == 1 {
			close(workerStarted)
			<-workerRelease
		}
	}

	ctx, cancelRun := context.WithCancel(context.Background())
	runDone := make(chan struct{})
	go func() {
		h.Run(ctx)
		close(runDone)
	}()
	t.Cleanup(func() {
		releaseWorker()
		cancelRun()
		select {
		case <-runDone:
		case <-time.After(time.Second):
			t.Error("hub run loop did not exit during test cleanup")
		}
	})
	require.Eventually(t, func() bool { return hubLifecycleContext(h) != nil }, time.Second, time.Millisecond)

	broadcast := func(sequence uint64) *Message {
		return &Message{
			Type: "new_message",
			Room: room,
			MessageReplayMetadata: &MessageReplayMetadata{
				Seq:    sequence,
				Stream: "CHAT_EVENTS",
			},
		}
	}
	dropsBefore := testutil.ToFloat64(BroadcastDropsTotal)
	h.Broadcast <- broadcast(1)
	select {
	case <-workerStarted:
	case <-time.After(time.Second):
		t.Fatal("sequenced broadcast worker did not start")
	}
	h.Broadcast <- broadcast(2)
	h.Broadcast <- broadcast(3)

	require.Eventually(t, func() bool {
		h.mu.RLock()
		defer h.mu.RUnlock()
		_, registered := h.Clients[client.ID]
		return !registered && len(h.Rooms[room]) == 0 &&
			testutil.ToFloat64(BroadcastDropsTotal) >= dropsBefore+1
	}, time.Second, time.Millisecond, "overflow must evict affected room clients without blocking Run")

	releaseWorker()
	cancelRun()
	select {
	case <-runDone:
	case <-time.After(time.Second):
		t.Fatal("hub run loop did not stop after context cancellation")
	}
	_, sendOpen := <-client.Send
	assert.False(t, sendOpen, "overflow cleanup must close the evicted client's send queue")
	assert.Equal(t, baseline, testutil.ToFloat64(ActiveConnections))
}

type blockedRoomJoinAuth struct {
	started chan struct{}
	allow   chan struct{}
}

func (a *blockedRoomJoinAuth) CanJoinRoom(context.Context, string, string) bool {
	close(a.started)
	<-a.allow
	return true
}

func (*blockedRoomJoinAuth) Invalidate(string, string) {}

func TestFailRoomClientsFencesInFlightAuthorizedJoin(t *testing.T) {
	activeBefore := testutil.ToFloat64(ActiveConnections)
	t.Cleanup(func() { ActiveConnections.Set(activeBefore) })

	h := setupTestHub()
	auth := &blockedRoomJoinAuth{started: make(chan struct{}), allow: make(chan struct{})}
	h.authClient = auth
	var releaseOnce sync.Once
	releaseAuthorization := func() { releaseOnce.Do(func() { close(auth.allow) }) }
	joinFinished := make(chan struct{})
	failDone := make(chan struct{})
	failStarted := false
	t.Cleanup(func() {
		releaseAuthorization()
		select {
		case <-joinFinished:
		case <-time.After(time.Second):
			t.Error("authorized join did not finish during cleanup")
		}
		if failStarted {
			select {
			case <-failDone:
			case <-time.After(time.Second):
				t.Error("room failure cleanup did not finish during cleanup")
			}
		}
	})

	clientCtx, cancelClient := context.WithCancel(context.Background())
	t.Cleanup(cancelClient)
	client := &Client{
		ID:               "overflow-join-race",
		UserID:           "overflow-join-user",
		SessionJTI:       "overflow-join-session",
		SessionExpiresAt: time.Now().Add(time.Hour),
		Hub:              h,
		Rooms:            make(map[string]bool),
		Send:             make(chan []byte, 1),
		ctx:              clientCtx,
		cancel:           cancelClient,
	}
	h.handleRegister(context.Background(), client)
	client.JoinRoom("overflow-room")

	joinDone := make(chan error, 1)
	go func() {
		joinDone <- client.authorizeAndHandleIncomingMessage(
			clientCtx,
			Message{Type: "join", Room: "new-room"},
			nil,
		)
		close(joinFinished)
	}()
	select {
	case <-auth.started:
	case <-time.After(time.Second):
		t.Fatal("room authorization did not enter the controlled join")
	}

	failStarted = true
	go func() {
		h.failRoomClients("overflow-room")
		close(failDone)
	}()
	require.Eventually(t, func() bool {
		if client.sessionGate.TryRLock() {
			client.sessionGate.RUnlock()
			return false
		}
		return true
	}, time.Second, time.Millisecond, "room failure must fence the active authorized action")

	releaseAuthorization()
	select {
	case err := <-joinDone:
		require.NoError(t, err)
	case <-time.After(time.Second):
		t.Fatal("authorized join did not finish after its authorization was released")
	}
	select {
	case <-failDone:
	case <-time.After(time.Second):
		t.Fatal("room failure cleanup remained blocked after the action finished")
	}

	require.Error(t, client.ctx.Err(), "room failure must cancel the client's session")
	require.True(t, client.sessionRevoked.Load(), "room failure must revoke future authorized actions")

	h.mu.RLock()
	_, registered := h.Clients[client.ID]
	_, failedRoomPresent := h.Rooms["overflow-room"]
	_, newRoomPresent := h.Rooms["new-room"]
	h.mu.RUnlock()
	assert.False(t, registered, "failed client must leave the client registry")
	assert.False(t, failedRoomPresent, "failed room membership must be removed")
	assert.False(t, newRoomPresent, "an in-flight join must not reinsert the failed client")

	client.mu.Lock()
	assert.Empty(t, client.Rooms)
	client.mu.Unlock()
	_, sendOpen := <-client.Send
	assert.False(t, sendOpen, "failed client's send queue must be closed")
	assert.Equal(t, activeBefore, testutil.ToFloat64(ActiveConnections))
}

func TestHubBroadcast_TraceAndMarshalErrorBranches(t *testing.T) {
	h := setupTestHub()
	_, span := otel.Tracer("hub-lifecycle").Start(context.Background(), "lifecycle")
	assert.Nil(t, h.collectRecipients(&Message{To: "missing"}, span))
	span.End()

	oldMarshal := hubJSONMarshalFunc
	t.Cleanup(func() { hubJSONMarshalFunc = oldMarshal })
	hubJSONMarshalFunc = func(any) ([]byte, error) { return nil, errors.New("marshal failed") }
	h.broadcastMessage(context.Background(), &Message{TraceCtx: map[string]string{"traceparent": "00-invalid"}})
}

func TestHubNATSHandlers_RecoverPanicsAndContainHMACFailures(t *testing.T) {
	//nolint:gosec // test-only HMAC secret
	const secret = "handler-lifecycle-secret" // pragma: allowlist secret
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
	cachePayload := signedInvalidationPayload(t, secret, invalidationData{
		RoomID: "22222222-2222-2222-2222-222222222222",
		UserID: "11111111-1111-1111-1111-111111111111",
	})
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
	require.Eventually(t, func() bool { return hubLifecycleContext(h) != nil }, time.Second, time.Millisecond)
	cancelled := false
	h.jwksCacheCancel = func() { cancelled = true }
	h.StartLimiterCleanup(context.Background())
	h.Stop()
	assert.True(t, cancelled)
	assert.Nil(t, h.limiterCancel)
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

	for _, subject := range []string{"notifications.*", "ws_hub.control"} {
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
