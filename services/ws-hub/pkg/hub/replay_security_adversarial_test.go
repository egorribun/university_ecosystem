package hub

import (
	"bytes"
	"context"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"errors"
	"log/slog"
	"strings"
	"testing"
	"time"

	"github.com/nats-io/nats.go"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func signedTokenPart(secret, payload string) string {
	mac := hmac.New(sha256.New, []byte(secret))
	_, _ = mac.Write([]byte(payload))
	return payload + "." + base64.RawURLEncoding.EncodeToString(mac.Sum(nil))
}

func TestServerOwnedReplayMetadataCannotBeInjected(t *testing.T) {
	t.Run("client ingress strips replay fields", func(t *testing.T) {
		message := Message{
			Type: "message",
			MessageReplayMetadata: &MessageReplayMetadata{
				Seq:         99,
				ResumeToken: "attacker-token",
				Stream:      "CHAT_EVENTS",
			},
		}
		stripClientReplayMetadata(&message)
		assert.Nil(t, message.MessageReplayMetadata)
	})

	t.Run("core fallback strips publisher replay fields", func(t *testing.T) {
		h := setupTestHub()
		message := &nats.Msg{
			Subject: "chat.room",
			Data: []byte(`{"type":"new_message","room":"room","payload":{"chat_id":"room"},` +
				`"seq":99,"resume_token":"attacker-token"}`),
		}
		h.processChatDelivery(context.Background(), message, false)

		select {
		case delivered := <-h.Broadcast:
			assert.Nil(t, delivered.MessageReplayMetadata)
			encoded, err := json.Marshal(delivered)
			require.NoError(t, err)
			assert.NotContains(t, string(encoded), `"seq"`)
			assert.NotContains(t, string(encoded), `"resume_token"`)
		default:
			t.Fatal("core fallback message was not delivered")
		}
	})
}

func newReplayState() *roomReplayState {
	ctx, cancel := context.WithCancel(context.Background())
	return &roomReplayState{ctx: ctx, cancel: cancel, buffered: make(map[uint64][]byte)}
}

func TestResumeTokensFailClosedForIncompleteAndMalformedInputs(t *testing.T) {
	var nilHub *Hub
	_, err := nilHub.issueResumeToken("user", "room", "CHAT_EVENTS", 1)
	assert.Error(t, err)

	for _, mutate := range []func(*Hub){
		func(h *Hub) { h.internalSecret = "" },
		func(h *Hub) { h.chatStreamIncarnation = "" },
		func(h *Hub) { h.streamChat = "" },
	} {
		h := setupTestHub()
		enableSecureReplayForTest(h)
		mutate(h)
		_, err = h.issueResumeToken("user", "room", h.streamChat, 1)
		assert.Error(t, err)
	}
	h := setupTestHub()
	enableSecureReplayForTest(h)
	for _, args := range []struct {
		user, room, stream string
		sequence           uint64
	}{
		{room: "room", stream: h.streamChat, sequence: 1},
		{user: "user", stream: h.streamChat, sequence: 1},
		{user: "user", room: "room", sequence: 1},
		{user: "user", room: "room", stream: h.streamChat},
	} {
		_, err = h.issueResumeToken(args.user, args.room, args.stream, args.sequence)
		assert.Error(t, err)
	}

	_, err = nilHub.verifyResumeToken("token", "user", "room")
	assert.Error(t, err)
	for _, token := range []string{"", strings.Repeat("a", 4097), "missing-dot", ".signature", "payload.", "payload.signature.extra", "payload.%%%"} {
		_, err = h.verifyResumeToken(token, "user", "room")
		assert.Error(t, err, token)
	}
	invalidPayload := signedTokenPart(h.internalSecret, "%%%")
	_, err = h.verifyResumeToken(invalidPayload, "user", "room")
	assert.Error(t, err)
	invalidClaimsPart := base64.RawURLEncoding.EncodeToString([]byte("not-json"))
	_, err = h.verifyResumeToken(signedTokenPart(h.internalSecret, invalidClaimsPart), "user", "room")
	assert.Error(t, err)

	originalMarshal := hubJSONMarshalFunc
	t.Cleanup(func() { hubJSONMarshalFunc = originalMarshal })
	hubJSONMarshalFunc = func(any) ([]byte, error) { return nil, errors.New("claims marshal failed") }
	_, err = h.issueResumeToken("user", "room", h.streamChat, 1)
	assert.EqualError(t, err, "claims marshal failed")
}

func TestChatBindingsRejectAmbiguousOrCrossRoomPayloads(t *testing.T) {
	assert.False(t, chatPayloadMatchesRoom("room", "not-an-object"))
	assert.False(t, chatPayloadMatchesRoom("room", map[string]any{"message": "not-an-object"}))
	assert.False(t, validateLiveChatBinding("chat.room", &Message{Room: "room", Payload: json.RawMessage(`{`)}))
	assert.False(t, validateReplayChatBinding("chat.other", "room", map[string]any{
		"room": "room", "payload": map[string]any{"chat_id": "room"},
	}))
}

func TestClientInvalidResumeTokenKeepsOnlyLiveMembership(t *testing.T) {
	h := setupTestHub()
	enableSecureReplayForTest(h)
	ctx, cancel := context.WithCancel(context.Background())
	t.Cleanup(cancel)
	client := &Client{UserID: "user", Hub: h, Rooms: make(map[string]bool), Send: make(chan []byte, 1), ctx: ctx, cancel: cancel}
	token, err := h.issueResumeToken(client.UserID, "room", h.streamChat, 7)
	require.NoError(t, err)
	payload, err := json.Marshal(joinPayload{ResumeToken: token + "tampered"})
	require.NoError(t, err)

	client.handleJoin(client.ctx, Message{Type: "join", Room: "room", Payload: payload})

	client.mu.Lock()
	assert.True(t, client.Rooms["room"])
	client.mu.Unlock()
	var frame map[string]any
	require.NoError(t, json.Unmarshal(<-client.Send, &frame))
	assert.Equal(t, "invalid_resume_token", frame["code"])
}

func TestReplayDeliveryFailsClosedAcrossPoisonAndMarshalFailures(t *testing.T) {
	originalAck := ackOfflineMessageFunc
	originalNak := nakOfflineMessageFunc
	originalTerm := termOfflineMessageFunc
	originalMarshal := hubJSONMarshalFunc
	t.Cleanup(func() {
		ackOfflineMessageFunc = originalAck
		nakOfflineMessageFunc = originalNak
		termOfflineMessageFunc = originalTerm
		hubJSONMarshalFunc = originalMarshal
	})

	t.Run("cross-room poison term failure is delayed", func(t *testing.T) {
		h := setupTestHub()
		enableSecureReplayForTest(h)
		client := &Client{UserID: "user", Hub: h, Send: make(chan []byte, 1), ctx: context.Background()}
		poison := replayMessage(10)
		poison.Subject = "chat.other"
		poison.Data = []byte("not-json")
		termOfflineMessageFunc = func(*nats.Msg) error { return errors.New("term failed") }
		naks := 0
		nakOfflineMessageFunc = func(*nats.Msg, time.Duration) error { naks++; return nil }
		found, maxSequence := true, uint64(9)
		assert.False(t, client.deliverOfflineMessageBatch(context.Background(), "room", []*nats.Msg{poison}, "", &found, &maxSequence))
		assert.Equal(t, 1, naks)
	})

	t.Run("cross-room poison is terminated without advancing", func(t *testing.T) {
		h := setupTestHub()
		enableSecureReplayForTest(h)
		client := &Client{UserID: "user", Hub: h, Send: make(chan []byte, 1), ctx: context.Background()}
		poison := replayMessage(10)
		poison.Subject = "chat.other"
		poison.Data = []byte("not-json")
		termOfflineMessageFunc = func(*nats.Msg) error { return nil }
		nakOfflineMessageFunc = func(*nats.Msg, time.Duration) error {
			t.Fatal("permanent cross-room poison must not be redelivered")
			return nil
		}
		found, maxSequence := true, uint64(9)
		assert.True(t, client.deliverOfflineMessageBatch(context.Background(), "room", []*nats.Msg{poison}, "", &found, &maxSequence))
		assert.Equal(t, uint64(9), maxSequence)
	})

	t.Run("poison checkpoint token prerequisites fail closed", func(t *testing.T) {
		h := setupTestHub()
		client := &Client{UserID: "user", Hub: h, Send: make(chan []byte, 1), ctx: context.Background()}
		poison := replayMessage(11)
		poison.Data = []byte("not-json")
		termOfflineMessageFunc = func(*nats.Msg) error { return nil }
		found, maxSequence := true, uint64(10)
		assert.False(t, client.deliverOfflineMessageBatch(context.Background(), "room", []*nats.Msg{poison}, "", &found, &maxSequence))
	})

	t.Run("poison checkpoint marshal failure is contained", func(t *testing.T) {
		h := setupTestHub()
		enableSecureReplayForTest(h)
		client := &Client{UserID: "user", Hub: h, Send: make(chan []byte, 1), ctx: context.Background()}
		poison := replayMessage(12)
		poison.Data = []byte("not-json")
		termOfflineMessageFunc = func(*nats.Msg) error { return nil }
		hubJSONMarshalFunc = func(value any) ([]byte, error) {
			if claims, ok := value.(resumeTokenClaims); ok {
				return json.Marshal(claims)
			}
			return nil, errors.New("checkpoint marshal failed")
		}
		found, maxSequence := true, uint64(11)
		assert.False(t, client.deliverOfflineMessageBatch(context.Background(), "room", []*nats.Msg{poison}, "", &found, &maxSequence))
	})

	t.Run("terminated poison is delayed when checkpoint queue is full", func(t *testing.T) {
		h := setupTestHub()
		enableSecureReplayForTest(h)
		client := &Client{UserID: "user", Hub: h, Send: make(chan []byte, 1), ctx: context.Background()}
		client.Send <- []byte("full")
		poison := replayMessage(13)
		poison.Data = []byte("not-json")
		termOfflineMessageFunc = func(*nats.Msg) error { return nil }
		naks := 0
		nakOfflineMessageFunc = func(*nats.Msg, time.Duration) error { naks++; return nil }
		hubJSONMarshalFunc = json.Marshal
		found, maxSequence := true, uint64(12)
		assert.False(t, client.deliverOfflineMessageBatch(context.Background(), "room", []*nats.Msg{poison}, "", &found, &maxSequence))
		assert.Equal(t, 1, naks)
	})

	t.Run("valid replay marshal failure is terminal", func(t *testing.T) {
		h := setupTestHub()
		enableSecureReplayForTest(h)
		client := &Client{UserID: "user", Hub: h, Send: make(chan []byte, 1), ctx: context.Background()}
		terms := 0
		termOfflineMessageFunc = func(*nats.Msg) error { terms++; return nil }
		hubJSONMarshalFunc = func(value any) ([]byte, error) {
			if claims, ok := value.(resumeTokenClaims); ok {
				return json.Marshal(claims)
			}
			return nil, errors.New("frame marshal failed")
		}
		found, maxSequence := true, uint64(13)
		assert.True(t, client.deliverOfflineMessageBatch(context.Background(), "room", []*nats.Msg{replayMessage(14)}, "", &found, &maxSequence))
		assert.Equal(t, 1, terms)
	})

	t.Run("cross-room valid frame term failure is delayed", func(t *testing.T) {
		h := setupTestHub()
		enableSecureReplayForTest(h)
		client := &Client{UserID: "user", Hub: h, Send: make(chan []byte, 1), ctx: context.Background()}
		message := replayMessage(15)
		message.Data = []byte(`{"type":"new_message","room":"other","payload":{"chat_id":"other"}}`)
		termOfflineMessageFunc = func(*nats.Msg) error { return errors.New("term failed") }
		naks := 0
		nakOfflineMessageFunc = func(*nats.Msg, time.Duration) error { naks++; return nil }
		hubJSONMarshalFunc = json.Marshal
		found, maxSequence := true, uint64(14)
		assert.False(t, client.deliverOfflineMessageBatch(context.Background(), "room", []*nats.Msg{message}, "", &found, &maxSequence))
		assert.Equal(t, 1, naks)
	})

	t.Run("valid replay without token prerequisites fails closed", func(t *testing.T) {
		h := setupTestHub()
		client := &Client{UserID: "user", Hub: h, Send: make(chan []byte, 1), ctx: context.Background()}
		hubJSONMarshalFunc = json.Marshal
		found, maxSequence := true, uint64(15)
		assert.False(t, client.deliverOfflineMessageBatch(context.Background(), "room", []*nats.Msg{replayMessage(16)}, "", &found, &maxSequence))
	})

	t.Run("frame marshal and term failures preserve redelivery", func(t *testing.T) {
		h := setupTestHub()
		enableSecureReplayForTest(h)
		client := &Client{UserID: "user", Hub: h, Send: make(chan []byte, 1), ctx: context.Background()}
		termOfflineMessageFunc = func(*nats.Msg) error { return errors.New("term failed") }
		naks := 0
		nakOfflineMessageFunc = func(*nats.Msg, time.Duration) error { naks++; return nil }
		hubJSONMarshalFunc = func(value any) ([]byte, error) {
			if claims, ok := value.(resumeTokenClaims); ok {
				return json.Marshal(claims)
			}
			return nil, errors.New("frame marshal failed")
		}
		found, maxSequence := true, uint64(16)
		assert.False(t, client.deliverOfflineMessageBatch(context.Background(), "room", []*nats.Msg{replayMessage(17)}, "", &found, &maxSequence))
		assert.Equal(t, 1, naks)
	})
}

func TestReplayQueueAndFlushAdversarialStateTransitions(t *testing.T) {
	h := setupTestHub()
	enableSecureReplayForTest(h)
	ctx, cancel := context.WithCancel(context.Background())
	t.Cleanup(cancel)
	client := &Client{UserID: "user", Hub: h, Send: make(chan []byte, 8), replays: make(map[string]*roomReplayState), ctx: ctx, cancel: cancel}

	assert.Equal(t, roomEnqueueReplayFatal, (&Client{Hub: setupTestHub(), Send: make(chan []byte, 1), ctx: context.Background()}).enqueueRoomBroadcast(
		&Message{Room: "room", MessageReplayMetadata: &MessageReplayMetadata{Seq: 1, Stream: "CHAT_EVENTS"}}, []byte(`{}`),
	))
	assert.Equal(t, roomEnqueueReplayFatal, client.enqueueRoomBroadcast(
		&Message{Room: "room", MessageReplayMetadata: &MessageReplayMetadata{Seq: 1, Stream: h.streamChat}}, []byte(`not-json`),
	))

	state := newReplayState()
	client.replays["room"] = state
	assert.Equal(t, roomEnqueueReplayFatal, client.enqueueRoomBroadcast(&Message{Room: "room"}, []byte(`{}`)))
	assert.Error(t, state.ctx.Err())

	state = newReplayState()
	state.buffered[2] = []byte("old")
	state.bufferedBytes = len("old")
	client.replays["room"] = state
	assert.Equal(t, roomEnqueueBuffered, client.enqueueRoomBroadcast(
		&Message{Room: "room", MessageReplayMetadata: &MessageReplayMetadata{Seq: 2, Stream: h.streamChat}}, []byte(`{"type":"new_message"}`),
	))
	assert.NotEqual(t, "old", string(state.buffered[2]))

	state = newReplayState()
	for sequence := uint64(1); sequence <= replayLiveBufferLimit; sequence++ {
		state.buffered[sequence] = []byte("x")
	}
	state.bufferedBytes = replayLiveBufferLimit
	client.replays["room"] = state
	assert.Equal(t, roomEnqueueReplayFatal, client.enqueueRoomBroadcast(
		&Message{Room: "room", MessageReplayMetadata: &MessageReplayMetadata{Seq: replayLiveBufferLimit + 1, Stream: h.streamChat}}, []byte(`{}`),
	))

	state = newReplayState()
	state.bufferedBytes = replayLiveBufferBytes
	client.replays["room"] = state
	assert.Equal(t, roomEnqueueReplayFatal, client.enqueueRoomBroadcast(
		&Message{Room: "room", MessageReplayMetadata: &MessageReplayMetadata{Seq: 1, Stream: h.streamChat}}, []byte(`{}`),
	))

	originalMarshal := hubJSONMarshalFunc
	t.Cleanup(func() { hubJSONMarshalFunc = originalMarshal })
	hubJSONMarshalFunc = func(value any) ([]byte, error) {
		if claims, ok := value.(resumeTokenClaims); ok {
			return json.Marshal(claims)
		}
		return nil, errors.New("personalization marshal failed")
	}
	assert.Equal(t, roomEnqueueReplayFatal, client.enqueueRoomBroadcast(
		&Message{Room: "other", MessageReplayMetadata: &MessageReplayMetadata{Seq: 1, Stream: h.streamChat}}, []byte(`{}`),
	))
	hubJSONMarshalFunc = json.Marshal

	stale := newReplayState()
	client.replays["flush"] = newReplayState()
	assert.False(t, client.flushRoomReplay("flush", stale, 0))
	assert.False(t, client.detachRoomReplay("flush", stale))
	matching := client.replays["flush"]
	assert.True(t, client.detachRoomReplay("flush", matching))

	ordered := newReplayState()
	ordered.buffered = map[uint64][]byte{1: []byte(`{"seq":1}`), 3: []byte(`{"seq":3}`), 2: []byte(`{"seq":2}`)}
	ordered.bufferedBytes = len(ordered.buffered[1]) + len(ordered.buffered[2]) + len(ordered.buffered[3])
	client.replays["ordered"] = ordered
	assert.True(t, client.flushRoomReplay("ordered", ordered, 1))
	assert.Equal(t, `{"seq":2}`, string(<-client.Send))
	assert.Equal(t, `{"seq":3}`, string(<-client.Send))

	blockedCtx, blockedCancel := context.WithCancel(context.Background())
	blocked := &roomReplayState{ctx: blockedCtx, cancel: blockedCancel, buffered: map[uint64][]byte{1: []byte("blocked")}, bufferedBytes: len("blocked")}
	blockedCancel()
	blockedClient := &Client{Send: make(chan []byte), replays: map[string]*roomReplayState{"blocked": blocked}}
	assert.False(t, blockedClient.flushRoomReplay("blocked", blocked, 0))
	assert.Empty(t, blockedClient.replays)
}

func TestReplayCancellationAdaptersAndConnectionFailurePaths(t *testing.T) {
	originalNak := nakOfflineMessageFunc
	originalTerm := termOfflineMessageFunc
	originalJetStreamTerm := jetStreamTermFunc
	originalJetStreamNak := jetStreamNakFunc
	t.Cleanup(func() {
		nakOfflineMessageFunc = originalNak
		termOfflineMessageFunc = originalTerm
		jetStreamTermFunc = originalJetStreamTerm
		jetStreamNakFunc = originalJetStreamNak
	})
	assert.Error(t, nakOfflineMessageFunc(&nats.Msg{}, time.Millisecond))
	assert.Error(t, termOfflineMessageFunc(&nats.Msg{}))
	assert.Error(t, jetStreamTermFunc(&nats.Msg{}))
	termCalls := 0
	jetStreamTermFunc = func(msg *nats.Msg) error {
		require.NotNil(t, msg)
		termCalls++
		return nil
	}
	require.NoError(t, safeTerm(nil))
	assert.Zero(t, termCalls, "nil poison messages must not reach the NATS adapter")
	require.NoError(t, safeTerm(&nats.Msg{}))
	assert.Equal(t, 1, termCalls)

	var logs bytes.Buffer
	h := setupTestHub()
	h.Logger = slog.New(slog.NewJSONHandler(&logs, nil))
	jetStreamTermFunc = func(*nats.Msg) error { return errors.New("term unavailable") }
	jetStreamNakCalls := 0
	jetStreamNakFunc = func(msg *nats.Msg, delay time.Duration) error {
		require.NotNil(t, msg)
		assert.Equal(t, 5*time.Second, delay)
		jetStreamNakCalls++
		return nil
	}
	h.terminateChatMessage(context.Background(), &nats.Msg{Subject: "chat.room"}, "binding mismatch")
	assert.Contains(t, logs.String(), "Failed to terminate rejected NATS chat message")
	assert.Contains(t, logs.String(), "term unavailable")
	assert.Equal(t, 1, jetStreamNakCalls, "failed TERM must request bounded redelivery")
	jetStreamTermFunc = func(*nats.Msg) error { return nats.ErrMsgNotBound }
	h.terminateChatMessage(context.Background(), &nats.Msg{Subject: "chat.room"}, "core fallback")
	assert.Equal(t, 1, jetStreamNakCalls, "core NATS messages have no JetStream redelivery adapter")

	client := &Client{Hub: h, ctx: context.Background()}
	nakCalls := 0
	nakOfflineMessageFunc = func(*nats.Msg, time.Duration) error {
		nakCalls++
		return errors.New("nak failed")
	}
	client.nakOfflineReplay(client.ctx, &nats.Msg{})
	assert.Equal(t, 1, nakCalls)

	emptyRoomCtx, cancelEmptyRoom := context.WithCancel(context.Background())
	t.Cleanup(cancelEmptyRoom)
	emptyRoomClient := &Client{ctx: emptyRoomCtx, cancel: cancelEmptyRoom}
	h.Rooms[""] = map[*Client]bool{emptyRoomClient: true}
	h.failRoomClients("")
	assert.NoError(t, emptyRoomCtx.Err(), "empty room identifiers must not disconnect clients")

	client.replays = map[string]*roomReplayState{"one": newReplayState(), "two": newReplayState()}
	states := []*roomReplayState{client.replays["one"], client.replays["two"]}
	client.cancelAllRoomReplays()
	assert.Empty(t, client.replays)
	for _, state := range states {
		assert.Error(t, state.ctx.Err())
	}

	server, peer := newConnPair(t)
	connCtx, cancel := context.WithCancel(context.Background())
	withoutHub := &Client{Conn: NewWebSocketSession(server), Send: make(chan []byte, 1), ctx: connCtx, cancel: cancel}
	withoutHub.failReplayConnection()
	assert.Error(t, connCtx.Err())
	require.NoError(t, peer.SetReadDeadline(time.Now().Add(time.Second)))
	_, _, err := peer.ReadMessage()
	assert.Error(t, err, "replay failure must close the underlying transport")
}

func TestReplayHelpersCoverFailClosedEdgeContracts(t *testing.T) {
	t.Run("subscription without checkpoint binds the canonical stream", func(t *testing.T) {
		opts := offlineReplaySubscriptionOptions("", 0, "")
		assert.Len(t, opts, 1)
	})

	t.Run("null personalized frame is rejected", func(t *testing.T) {
		h := setupTestHub()
		enableSecureReplayForTest(h)
		client := &Client{Hub: h, UserID: "user-a"}
		message := &Message{
			Room: "room-a",
			MessageReplayMetadata: &MessageReplayMetadata{
				Seq:    1,
				Stream: h.streamChat,
			},
		}

		personalized, err := client.personalizeRoomBroadcast(message, []byte("null"))
		require.ErrorContains(t, err, "broadcast frame is null")
		assert.Nil(t, personalized)
	})

	t.Run("connection close failures are logged and unregistered", func(t *testing.T) {
		var logs bytes.Buffer
		h := setupTestHub()
		h.Logger = slog.New(slog.NewJSONHandler(&logs, nil))
		h.Unregister = make(chan *Client, 1)
		client := &Client{
			ID:   "replay-close-error",
			Hub:  h,
			Conn: &recordingSession{closeErr: errors.New("close failed")},
			Send: make(chan []byte, 1),
			ctx:  context.Background(),
		}

		client.failReplayConnection()

		assert.Contains(t, logs.String(), "Failed to close replay session")
		require.Same(t, client, <-h.Unregister)
	})

	t.Run("missing replay metadata has no stream", func(t *testing.T) {
		var nilMessage *Message
		assert.Empty(t, nilMessage.replayStream())
		assert.Empty(t, (&Message{}).replayStream())
	})
}

func TestReplayContextCancellationAndGenerationReplacement(t *testing.T) {
	h := setupTestHub()
	enableSecureReplayForTest(h)
	h.js = &scriptedPullSubscription{pull: func(string, string, ...nats.SubOpt) (*nats.Subscription, error) {
		return &nats.Subscription{}, nil
	}}
	originalFetch := fetchPullMessagesFunc
	originalUnsubscribe := unsubscribePullFunc
	t.Cleanup(func() { fetchPullMessagesFunc = originalFetch; unsubscribePullFunc = originalUnsubscribe })
	unsubscribePullFunc = func(*nats.Subscription) error { return nil }

	cancelled, cancel := context.WithCancel(context.Background())
	cancel()
	fetchCalls := 0
	fetchPullMessagesFunc = func(*nats.Subscription, int, ...nats.PullOpt) ([]*nats.Msg, error) {
		fetchCalls++
		return nil, errors.New("fetch must not run after cancellation")
	}
	send := make(chan []byte, 1)
	send <- []byte("existing")
	client := &Client{UserID: "user", Hub: h, Send: send, ctx: context.Background()}
	_, completed := client.replayOfflineMessagesContext(cancelled, "room", 1, "")
	assert.False(t, completed)
	assert.Zero(t, fetchCalls, "a cancelled replay must not fetch another batch")
	retryDone := make(chan bool, 1)
	go func() { retryDone <- client.sendReplayWithRetry(cancelled, []byte("after-cancel")) }()
	select {
	case sent := <-retryDone:
		assert.False(t, sent)
	case <-time.After(100 * time.Millisecond):
		t.Fatal("cancelled replay retry did not return promptly")
	}
	assert.Equal(t, "existing", string(<-send))
	time.Sleep(2 * offlineReplaySendDelay)
	assert.Empty(t, send, "a cancelled replay must not retry after the queue becomes writable")

	ctx, cancelClient := context.WithCancel(context.Background())
	t.Cleanup(cancelClient)
	client = &Client{UserID: "user", Hub: h, Rooms: make(map[string]bool), Send: make(chan []byte), replays: make(map[string]*roomReplayState), ctx: ctx, cancel: cancelClient}
	fetchStarted := make(chan struct{})
	releaseFetch := make(chan struct{})
	fetchPullMessagesFunc = func(*nats.Subscription, int, ...nats.PullOpt) ([]*nats.Msg, error) {
		close(fetchStarted)
		<-releaseFetch
		return nil, nats.ErrTimeout
	}
	client.startRoomReplay(client.ctx, "room", 1, "")
	<-fetchStarted
	client.replayMu.Lock()
	client.replays["room"] = newReplayState()
	client.replayMu.Unlock()
	close(releaseFetch)
	require.Eventually(t, func() bool { return ctx.Err() != nil }, time.Second, time.Millisecond)
}

func TestSubscribeToNATSTransactionalJetStreamBranches(t *testing.T) {
	originalContext := jetStreamContextFunc
	originalCore := coreNATSSubscribeFunc
	t.Cleanup(func() { jetStreamContextFunc = originalContext; coreNATSSubscribeFunc = originalCore })

	t.Run("context initialization failure", func(t *testing.T) {
		h := setupTestHub()
		h.Nats = &nats.Conn{}
		h.enableJetStream = true
		h.internalSecret = "secret" // pragma: allowlist secret -- inert unit-test fixture
		jetStreamContextFunc = func(*nats.Conn) (nats.JetStreamContext, error) { return nil, errors.New("context failed") }
		err := h.SubscribeToNATS(context.Background())
		assert.ErrorContains(t, err, "initialize JetStream context")
	})

	t.Run("notification failure rolls back chat subscription", func(t *testing.T) {
		server := newMockNatsServer(t)
		nc, err := nats.Connect(server.Addr())
		require.NoError(t, err)
		t.Cleanup(nc.Close)
		chatSub, err := nc.SubscribeSync("rollback.chat")
		require.NoError(t, err)
		h := setupTestHub()
		h.Nats = nc
		h.enableJetStream = true
		h.internalSecret = "secret" // pragma: allowlist secret -- inert unit-test fixture
		h.js = &scriptedSubscribeJetStream{
			streamInfo: func(string, ...nats.JSOpt) (*nats.StreamInfo, error) {
				return &nats.StreamInfo{Created: time.Now()}, nil
			},
			subscribe: func(subject string, _ nats.MsgHandler, _ ...nats.SubOpt) (*nats.Subscription, error) {
				if subject == "chat.*" {
					return chatSub, nil
				}
				return nil, errors.New("notification failed")
			},
		}
		err = h.SubscribeToNATS(context.Background())
		assert.ErrorContains(t, err, "notification events")
		assert.False(t, chatSub.IsValid())
		assert.Empty(t, h.subs)
	})

	t.Run("success enables replay only after all subscriptions", func(t *testing.T) {
		h := setupTestHub()
		h.Nats = &nats.Conn{}
		h.enableJetStream = true
		h.internalSecret = "secret" // pragma: allowlist secret -- inert unit-test fixture
		created := time.Now().UTC()
		h.js = &scriptedSubscribeJetStream{
			streamInfo: func(string, ...nats.JSOpt) (*nats.StreamInfo, error) { return &nats.StreamInfo{Created: created}, nil },
			subscribe: func(string, nats.MsgHandler, ...nats.SubOpt) (*nats.Subscription, error) {
				return &nats.Subscription{}, nil
			},
		}
		coreNATSSubscribeFunc = func(*nats.Conn, string, nats.MsgHandler) (*nats.Subscription, error) {
			return &nats.Subscription{}, nil
		}
		require.NoError(t, h.SubscribeToNATS(context.Background()))
		assert.True(t, h.chatReplayAvailable.Load())
		assert.Equal(t, created.Format(time.RFC3339Nano), h.chatStreamIncarnation)
		assert.Len(t, h.subs, 5)
	})
}
