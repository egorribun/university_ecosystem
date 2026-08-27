// Client replay, publish, and message-processing contracts.
package hub

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"github.com/nats-io/nats.go"
	"github.com/prometheus/client_golang/prometheus/testutil"
	"github.com/quic-go/webtransport-go"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

type scriptedPullSubscription struct {
	nats.JetStreamContext
	pull func(string, string, ...nats.SubOpt) (*nats.Subscription, error)
}

type scriptedSubscribeJetStream struct {
	nats.JetStreamContext
	subscribe  func(string, nats.MsgHandler, ...nats.SubOpt) (*nats.Subscription, error)
	pull       func(string, string, ...nats.SubOpt) (*nats.Subscription, error)
	streamInfo func(string, ...nats.JSOpt) (*nats.StreamInfo, error)
}

func (s *scriptedSubscribeJetStream) StreamInfo(name string, opts ...nats.JSOpt) (*nats.StreamInfo, error) {
	if s.streamInfo == nil {
		return nil, errors.New("stream info unavailable")
	}
	return s.streamInfo(name, opts...)
}

func (s *scriptedSubscribeJetStream) Subscribe(
	subject string,
	handler nats.MsgHandler,
	opts ...nats.SubOpt,
) (*nats.Subscription, error) {
	return s.subscribe(subject, handler, opts...)
}

func (s *scriptedSubscribeJetStream) PullSubscribe(
	subject, durable string,
	opts ...nats.SubOpt,
) (*nats.Subscription, error) {
	return s.pull(subject, durable, opts...)
}

func (s *scriptedPullSubscription) PullSubscribe(subject, durable string, opts ...nats.SubOpt) (*nats.Subscription, error) {
	return s.pull(subject, durable, opts...)
}

func enableSecureReplayForTest(h *Hub) {
	h.internalSecret = "test-replay-secret" // pragma: allowlist secret
	h.streamChat = "CHAT_EVENTS"
	h.chatStreamIncarnation = "test-stream-incarnation"
	h.chatReplayAvailable.Store(true)
}

func resumeJoinPayload(t *testing.T, h *Hub, userID, room string, sequence uint64) json.RawMessage {
	t.Helper()
	token, err := h.issueResumeToken(userID, room, h.streamChat, sequence)
	require.NoError(t, err)
	payload, err := json.Marshal(joinPayload{ResumeToken: token})
	require.NoError(t, err)
	return payload
}

type scriptedPublishJetStream struct {
	nats.JetStreamContext
	publishErr error
}

type readErrorSession struct {
	recordingSession
	err error
}

func (s *readErrorSession) ReadMessage() (int, []byte, error) {
	return 0, nil, s.err
}

func (s *scriptedPublishJetStream) PublishMsgAsync(*nats.Msg, ...nats.PubOpt) (nats.PubAckFuture, error) {
	return nil, s.publishErr
}

func TestClientChannelAndReplayGuards(t *testing.T) {
	assert.Error(t, ackOfflineMessageFunc(&nats.Msg{}))
	assert.False(t, safeSend(nil, []byte("ignored")))
	safeClose(nil)

	closedEntryCh := make(chan []byte, 1)
	chMu.Lock()
	chMutexes[closedEntryCh] = &chEntry{closed: true}
	chMu.Unlock()
	assert.False(t, safeSend(closedEntryCh, []byte("ignored")))
	safeClose(closedEntryCh)

	panicEntryCh := make(chan []byte, 1)
	chMu.Lock()
	chMutexes[panicEntryCh] = &chEntry{}
	chMu.Unlock()
	close(panicEntryCh)
	assert.False(t, safeSend(panicEntryCh, []byte("panic-recovery")))
	chMu.RLock()
	_, stillRegistered := chMutexes[panicEntryCh]
	chMu.RUnlock()
	assert.False(t, stillRegistered)

	hook := safeSendAfterLockHook
	t.Cleanup(func() { safeSendAfterLockHook = hook })
	safeSendAfterLockHook = func(_ chan []byte, entry *chEntry) { entry.closed = true }
	hooked := make(chan []byte, 1)
	assert.False(t, safeSend(hooked, []byte("closed-after-lock")))
	safeClose(hooked)

	assert.True(t, isNormalCloseError(&webtransport.SessionError{ErrorCode: 0}))
	assert.True(t, isNormalCloseError(&webtransport.SessionError{ErrorCode: 268}))
	assert.False(t, isNormalCloseError(&webtransport.SessionError{ErrorCode: 7}))

	msg := &Message{Type: "message", Payload: []byte(`{}`)}
	mergeTopLevelJoinReplay(msg, []byte(`{"type":"join","last_seq":1}`))
	assert.Equal(t, `{}`, string(msg.Payload), "non-join messages are unchanged")
	mergeTopLevelJoinReplay(nil, []byte(`{"type":"join","last_seq":1}`))
	join := &Message{Type: "join", Payload: []byte(`{not-json`)}
	mergeTopLevelJoinReplay(join, []byte(`{"type":"join","last_seq":1}`))
	assert.Equal(t, `{not-json`, string(join.Payload))
	join = &Message{Type: "join"}
	mergeTopLevelJoinReplay(join, []byte(`{"type":"join"}`))
	assert.Empty(t, join.Payload)

	join = &Message{Type: "join", Payload: []byte(`{"last_seq":7}`)}
	mergeTopLevelJoinReplay(join, []byte(`{"type":"join","last_msg_id":"resume-7"}`))
	var merged joinPayload
	require.NoError(t, json.Unmarshal(join.Payload, &merged))
	assert.Equal(t, "resume-7", merged.LastMsgID)
}

func TestClientReplayOfflineMessages_UsesResumeOptionsAndHandlesFetchFailure(t *testing.T) {
	h := setupTestHub()
	h.streamChat = ""
	client := &Client{Hub: h, ctx: context.Background(), Send: make(chan []byte, 1)}
	h.js = &scriptedPullSubscription{pull: func(subject, durable string, opts ...nats.SubOpt) (*nats.Subscription, error) {
		assert.Equal(t, "chat.room", subject)
		assert.Empty(t, durable)
		return nil, errors.New("pull subscription unavailable")
	}}
	client.replayOfflineMessages("room", 3, "")
	client.replayOfflineMessages("room", 0, "42")
	client.replayOfflineMessages("room", 0, "not-a-sequence")

	server := newMockNatsServer(t)
	nc, err := nats.Connect(server.Addr())
	require.NoError(t, err)
	t.Cleanup(nc.Close)
	sub, err := nc.SubscribeSync("chat.room")
	require.NoError(t, err)
	defaultFetch := fetchPullMessagesFunc
	_, fetchErr := defaultFetch(sub, 1, nats.MaxWait(time.Millisecond))
	assert.Error(t, fetchErr)
	t.Cleanup(func() { fetchPullMessagesFunc = defaultFetch })
	fetchPullMessagesFunc = func(*nats.Subscription, int, ...nats.PullOpt) ([]*nats.Msg, error) {
		return []*nats.Msg{}, nil
	}
	h.js = &scriptedPullSubscription{pull: func(string, string, ...nats.SubOpt) (*nats.Subscription, error) {
		return sub, nil
	}}
	oldUnsubscribe := unsubscribePullFunc
	t.Cleanup(func() { unsubscribePullFunc = oldUnsubscribe })
	unsubscribePullFunc = func(*nats.Subscription) error { return errors.New("unsubscribe failed") }
	client.replayOfflineMessages("room", 1, "")
	fetchPullMessagesFunc = func(*nats.Subscription, int, ...nats.PullOpt) ([]*nats.Msg, error) {
		return nil, errors.New("fetch unavailable")
	}
	client.replayOfflineMessages("room", 1, "")
}

func TestClientDeliverOfflineMessages_ResumesAndSerializesReplay(t *testing.T) {
	h := setupTestHub()
	enableSecureReplayForTest(h)
	client := &Client{UserID: "replay-user", Hub: h, ctx: context.Background(), Send: make(chan []byte, 4)}
	oldAck := ackOfflineMessageFunc
	oldTerm := termOfflineMessageFunc
	t.Cleanup(func() {
		ackOfflineMessageFunc = oldAck
		termOfflineMessageFunc = oldTerm
	})
	ackOfflineMessageFunc = func(*nats.Msg) error { return errors.New("ack unavailable") }
	termOfflineMessageFunc = func(*nats.Msg) error { return nil }
	msgs := []*nats.Msg{
		{Subject: "chat.room", Header: nats.Header{"Nats-Msg-Id": []string{"before"}}, Data: []byte(`{"type":"message","room":"room","payload":{"room":"room","n":0}}`)},
		{Subject: "chat.room", Header: nats.Header{"Nats-Msg-Id": []string{"resume-7"}}, Data: []byte(`{"type":"message","room":"room","payload":{"room":"room","n":1}}`)},
		{Subject: "chat.room", Reply: "$JS.ACK.CHAT_EVENTS.consumer.1.42.7.123456789.0", Sub: &nats.Subscription{}, Data: []byte(`{"type":"message","room":"room","payload":{"room":"room","n":2}}`)},
		{Data: []byte("not-json")},
	}

	foundLastMsgID := false
	maxSequence := uint64(0)
	client.deliverOfflineMessageBatch(context.Background(), "room", msgs, "resume-7", &foundLastMsgID, &maxSequence)
	first := <-client.Send
	var replayed map[string]any
	require.NoError(t, json.Unmarshal(first, &replayed))
	assert.Equal(t, true, replayed["replayed"])
	assert.Equal(t, float64(42), replayed["seq"])
	assert.Empty(t, client.Send)

	cancelledCtx, cancel := context.WithCancel(context.Background())
	cancel()
	client.ctx = cancelledCtx
	client.deliverOfflineMessages([]*nats.Msg{{Data: []byte(`{"type":"message"}`)}}, 0, "")
	assert.Empty(t, client.Send)
}

func TestClientDeliverOfflineMessages_AcksOnlyAfterQueueing(t *testing.T) {
	h := setupTestHub()
	enableSecureReplayForTest(h)
	client := &Client{UserID: "replay-user", Hub: h, ctx: context.Background(), Send: make(chan []byte, 1)}
	oldAck := ackOfflineMessageFunc
	oldNak := nakOfflineMessageFunc
	t.Cleanup(func() {
		ackOfflineMessageFunc = oldAck
		nakOfflineMessageFunc = oldNak
	})
	ackCount := 0
	ackSawQueuedMessage := false
	ackOfflineMessageFunc = func(*nats.Msg) error {
		ackCount++
		ackSawQueuedMessage = len(client.Send) == 1
		return nil
	}
	nakCount := 0
	nakOfflineMessageFunc = func(*nats.Msg, time.Duration) error {
		nakCount++
		return nil
	}

	client.deliverOfflineMessages([]*nats.Msg{replayMessage(41)}, 40, "")

	assert.Equal(t, 1, ackCount)
	assert.Zero(t, nakCount)
	assert.True(t, ackSawQueuedMessage, "ACK must happen only after the replay is queued for the client")
}

func TestClientDeliverOfflineMessages_BackpressureDoesNotAck(t *testing.T) {
	h := setupTestHub()
	enableSecureReplayForTest(h)
	client := &Client{UserID: "replay-user", Hub: h, ctx: context.Background(), Send: make(chan []byte, 1)}
	client.Send <- []byte("already-full")
	oldAck := ackOfflineMessageFunc
	oldNak := nakOfflineMessageFunc
	t.Cleanup(func() {
		ackOfflineMessageFunc = oldAck
		nakOfflineMessageFunc = oldNak
	})
	ackCount := 0
	ackOfflineMessageFunc = func(*nats.Msg) error {
		ackCount++
		return nil
	}
	nakCount := 0
	nakOfflineMessageFunc = func(_ *nats.Msg, delay time.Duration) error {
		nakCount++
		assert.Equal(t, offlineReplayRetryDelay, delay)
		return nil
	}

	client.deliverOfflineMessages([]*nats.Msg{replayMessage(42)}, 41, "")

	assert.Zero(t, ackCount, "a replay rejected by the client queue must remain available for redelivery")
	assert.Equal(t, 1, nakCount)
	assert.Equal(t, "already-full", string(<-client.Send))
}

func TestClientDeliverOfflineMessages_PermanentPoisonIsNotAckedOrForwarded(t *testing.T) {
	h := setupTestHub()
	enableSecureReplayForTest(h)
	client := &Client{UserID: "replay-user", Hub: h, ctx: context.Background(), Send: make(chan []byte, 1)}
	oldAck := ackOfflineMessageFunc
	oldNak := nakOfflineMessageFunc
	oldTerm := termOfflineMessageFunc
	t.Cleanup(func() {
		ackOfflineMessageFunc = oldAck
		nakOfflineMessageFunc = oldNak
		termOfflineMessageFunc = oldTerm
	})
	ackCount := 0
	ackOfflineMessageFunc = func(*nats.Msg) error {
		ackCount++
		return nil
	}
	nakCount := 0
	termCount := 0
	nakOfflineMessageFunc = func(*nats.Msg, time.Duration) error {
		nakCount++
		return nil
	}
	termOfflineMessageFunc = func(*nats.Msg) error {
		termCount++
		return nil
	}

	client.deliverOfflineMessages([]*nats.Msg{{Data: []byte("not-json")}}, 0, "")

	assert.Zero(t, ackCount, "permanently invalid replay data must not be acknowledged as delivered")
	assert.Zero(t, nakCount)
	assert.Equal(t, 1, termCount, "permanently invalid replay data must be terminal, not retried forever")
	assert.Empty(t, client.Send, "permanently invalid replay data must not reach the browser")
}

func TestClientDeliverOfflineMessages_PoisonCheckpointAllowsProgress(t *testing.T) {
	h := setupTestHub()
	enableSecureReplayForTest(h)
	client := &Client{UserID: "replay-user", Hub: h, ctx: context.Background(), Send: make(chan []byte, 2)}
	oldAck := ackOfflineMessageFunc
	oldNak := nakOfflineMessageFunc
	oldTerm := termOfflineMessageFunc
	t.Cleanup(func() {
		ackOfflineMessageFunc = oldAck
		nakOfflineMessageFunc = oldNak
		termOfflineMessageFunc = oldTerm
	})
	ackCount := 0
	termCount := 0
	ackOfflineMessageFunc = func(*nats.Msg) error {
		ackCount++
		return nil
	}
	nakOfflineMessageFunc = func(*nats.Msg, time.Duration) error {
		t.Fatal("a queueable poison checkpoint must not be retried")
		return nil
	}
	termOfflineMessageFunc = func(*nats.Msg) error {
		termCount++
		return nil
	}
	poison := replayMessage(42)
	poison.Data = []byte("not-json")
	foundLastMsgID := true
	maxSequence := uint64(41)

	continued := client.deliverOfflineMessageBatch(
		context.Background(),
		"room",
		[]*nats.Msg{poison, replayMessage(43)},
		"",
		&foundLastMsgID,
		&maxSequence,
	)

	assert.True(t, continued)
	assert.Equal(t, 1, termCount)
	assert.Equal(t, 1, ackCount, "only the valid replay is acknowledged")
	var checkpoint map[string]any
	require.NoError(t, json.Unmarshal(<-client.Send, &checkpoint))
	assert.Equal(t, "replay_checkpoint", checkpoint["type"])
	assert.Equal(t, float64(42), checkpoint["seq"])
	var replayed map[string]any
	require.NoError(t, json.Unmarshal(<-client.Send, &replayed))
	assert.Equal(t, float64(43), replayed["seq"])
}

func TestClientDeliverOfflineMessages_TermFailureCannotAdvancePoisonCheckpoint(t *testing.T) {
	h := setupTestHub()
	enableSecureReplayForTest(h)
	client := &Client{UserID: "replay-user", Hub: h, ctx: context.Background(), Send: make(chan []byte, 1)}
	poison := replayMessage(42)
	poison.Data = []byte("not-json")
	oldTerm := termOfflineMessageFunc
	oldNak := nakOfflineMessageFunc
	t.Cleanup(func() {
		termOfflineMessageFunc = oldTerm
		nakOfflineMessageFunc = oldNak
	})
	termOfflineMessageFunc = func(*nats.Msg) error { return errors.New("term unavailable") }
	nakCalls := 0
	nakOfflineMessageFunc = func(*nats.Msg, time.Duration) error { nakCalls++; return nil }
	found := true
	maxSequence := uint64(41)

	continued := client.deliverOfflineMessageBatch(
		context.Background(), "room", []*nats.Msg{poison}, "", &found, &maxSequence,
	)

	assert.False(t, continued)
	assert.Equal(t, 1, nakCalls)
	assert.Empty(t, client.Send, "the browser cursor must not advance before poison termination commits")
	assert.Equal(t, uint64(41), maxSequence)
}

func TestClientReplayOfflineMessages_PaginatesBeyondOneBatch(t *testing.T) {
	h := setupTestHub()
	enableSecureReplayForTest(h)
	client := &Client{UserID: "replay-user", Hub: h, ctx: context.Background(), Send: make(chan []byte, 125)}
	h.js = &scriptedPullSubscription{pull: func(string, string, ...nats.SubOpt) (*nats.Subscription, error) {
		return &nats.Subscription{}, nil
	}}
	oldFetch := fetchPullMessagesFunc
	oldAck := ackOfflineMessageFunc
	oldUnsubscribe := unsubscribePullFunc
	t.Cleanup(func() {
		fetchPullMessagesFunc = oldFetch
		ackOfflineMessageFunc = oldAck
		unsubscribePullFunc = oldUnsubscribe
	})
	fetchCalls := 0
	fetchPullMessagesFunc = func(_ *nats.Subscription, batch int, _ ...nats.PullOpt) ([]*nats.Msg, error) {
		assert.Equal(t, 100, batch)
		fetchCalls++
		switch fetchCalls {
		case 1:
			return replayMessageRange(1, 100), nil
		case 2:
			return replayMessageRange(101, 125), nil
		default:
			return nil, nats.ErrTimeout
		}
	}
	ackCount := 0
	ackOfflineMessageFunc = func(*nats.Msg) error {
		ackCount++
		return nil
	}
	unsubscribePullFunc = func(*nats.Subscription) error { return nil }

	client.replayOfflineMessages("room", 1, "")

	assert.Equal(t, 3, fetchCalls, "replay must fetch until the consumer is drained")
	assert.Equal(t, 125, ackCount)
	require.Equal(t, 125, len(client.Send), "all replay pages must be queued before validating their order")
	for expectedSeq := 1; expectedSeq <= 125; expectedSeq++ {
		var replayed map[string]any
		require.NoError(t, json.Unmarshal(<-client.Send, &replayed))
		assert.Equal(t, float64(expectedSeq), replayed["seq"])
		assert.Equal(t, true, replayed["replayed"])
	}
}

func TestClientReplayOfflineMessages_StopsPageOnBackpressure(t *testing.T) {
	h := setupTestHub()
	enableSecureReplayForTest(h)
	client := &Client{UserID: "replay-user", Hub: h, ctx: context.Background(), Send: make(chan []byte, 1)}
	client.Send <- []byte("already-full")
	h.js = &scriptedPullSubscription{pull: func(string, string, ...nats.SubOpt) (*nats.Subscription, error) {
		return &nats.Subscription{}, nil
	}}
	oldFetch := fetchPullMessagesFunc
	oldAck := ackOfflineMessageFunc
	oldNak := nakOfflineMessageFunc
	oldUnsubscribe := unsubscribePullFunc
	t.Cleanup(func() {
		fetchPullMessagesFunc = oldFetch
		ackOfflineMessageFunc = oldAck
		nakOfflineMessageFunc = oldNak
		unsubscribePullFunc = oldUnsubscribe
	})
	fetchCalls := 0
	fetchPullMessagesFunc = func(*nats.Subscription, int, ...nats.PullOpt) ([]*nats.Msg, error) {
		fetchCalls++
		return replayMessageRange(50, 51), nil
	}
	ackCount := 0
	nakCount := 0
	unsubscribeCount := 0
	ackOfflineMessageFunc = func(*nats.Msg) error {
		ackCount++
		return nil
	}
	nakOfflineMessageFunc = func(*nats.Msg, time.Duration) error {
		nakCount++
		return nil
	}
	unsubscribePullFunc = func(*nats.Subscription) error {
		unsubscribeCount++
		return nil
	}

	client.replayOfflineMessages("room", 49, "")

	assert.Equal(t, 1, fetchCalls, "backpressure must stop pagination immediately")
	assert.Zero(t, ackCount, "neither the current nor unprocessed replay may be acknowledged")
	assert.Equal(t, 1, nakCount, "only the current blocked replay is explicitly delayed")
	assert.Equal(t, 1, unsubscribeCount, "unsubscribe releases the remaining unprocessed page")
}

func TestClientHandleJoin_SerializesReplayBeforeBufferedLiveDelivery(t *testing.T) {
	h := setupTestHub()
	enableSecureReplayForTest(h)
	h.enableJetStream = true
	h.js = &scriptedPullSubscription{pull: func(string, string, ...nats.SubOpt) (*nats.Subscription, error) {
		return &nats.Subscription{}, nil
	}}
	ctx, cancel := context.WithCancel(context.Background())
	t.Cleanup(cancel)
	client := &Client{
		ID: "ordered-replay", UserID: "ordered-user", Hub: h,
		Rooms: make(map[string]bool), Send: make(chan []byte, 4), ctx: ctx, cancel: cancel,
	}
	oldFetch := fetchPullMessagesFunc
	oldAck := ackOfflineMessageFunc
	oldUnsubscribe := unsubscribePullFunc
	t.Cleanup(func() {
		fetchPullMessagesFunc = oldFetch
		ackOfflineMessageFunc = oldAck
		unsubscribePullFunc = oldUnsubscribe
	})
	fetchStarted := make(chan struct{})
	releaseReplay := make(chan struct{})
	fetchCalls := 0
	fetchPullMessagesFunc = func(*nats.Subscription, int, ...nats.PullOpt) ([]*nats.Msg, error) {
		fetchCalls++
		if fetchCalls == 1 {
			close(fetchStarted)
			<-releaseReplay
			return []*nats.Msg{replayMessage(10)}, nil
		}
		return nil, nats.ErrTimeout
	}
	ackOfflineMessageFunc = func(*nats.Msg) error { return nil }
	unsubscribePullFunc = func(*nats.Subscription) error { return nil }

	client.handleJoin(client.ctx, Message{
		Type: "join", Room: "room", Payload: resumeJoinPayload(t, h, client.UserID, "room", 9),
	})
	<-fetchStarted
	h.broadcastMessage(context.Background(), &Message{
		Type: "new_message", Room: "room", MessageReplayMetadata: &MessageReplayMetadata{Seq: 20, Stream: "CHAT_EVENTS"},
		Payload: json.RawMessage(`{"type":"new_message"}`),
	})
	close(releaseReplay)

	var first map[string]any
	var second map[string]any
	require.Eventually(t, func() bool { return len(client.Send) == 2 }, time.Second, 10*time.Millisecond)
	require.NoError(t, json.Unmarshal(<-client.Send, &first))
	require.NoError(t, json.Unmarshal(<-client.Send, &second))
	assert.Equal(t, float64(10), first["seq"])
	assert.Equal(t, float64(20), second["seq"])
}

func TestClientDeliverOfflineMessages_RetriesHealthyQueueBackpressure(t *testing.T) {
	h := setupTestHub()
	enableSecureReplayForTest(h)
	client := &Client{UserID: "replay-user", Hub: h, ctx: context.Background(), Send: make(chan []byte, 1)}
	client.Send <- []byte("temporary-pressure")
	oldAck := ackOfflineMessageFunc
	oldNak := nakOfflineMessageFunc
	t.Cleanup(func() {
		ackOfflineMessageFunc = oldAck
		nakOfflineMessageFunc = oldNak
	})
	ackCount := 0
	nakCount := 0
	ackOfflineMessageFunc = func(*nats.Msg) error {
		ackCount++
		return nil
	}
	nakOfflineMessageFunc = func(*nats.Msg, time.Duration) error {
		nakCount++
		return nil
	}
	done := make(chan struct{})
	go func() {
		client.deliverOfflineMessages([]*nats.Msg{replayMessage(70)}, 69, "")
		close(done)
	}()

	time.Sleep(10 * time.Millisecond)
	assert.Equal(t, "temporary-pressure", string(<-client.Send))
	select {
	case <-done:
	case <-time.After(time.Second):
		t.Fatal("bounded replay retry did not complete")
	}
	require.Len(t, client.Send, 1)
	var replayed map[string]any
	require.NoError(t, json.Unmarshal(<-client.Send, &replayed))
	assert.Equal(t, float64(70), replayed["seq"])
	assert.Equal(t, 1, ackCount)
	assert.Zero(t, nakCount)
}

func TestClientHandleJoin_ClosesForCheckpointResumeAfterRetryExhaustion(t *testing.T) {
	h := setupTestHub()
	enableSecureReplayForTest(h)
	h.enableJetStream = true
	h.js = &scriptedPullSubscription{pull: func(string, string, ...nats.SubOpt) (*nats.Subscription, error) {
		return &nats.Subscription{}, nil
	}}
	ctx, cancel := context.WithCancel(context.Background())
	client := &Client{
		ID: "retry-exhausted", UserID: "retry-exhausted-user", Hub: h,
		Rooms: make(map[string]bool), Send: make(chan []byte, 1), ctx: ctx, cancel: cancel,
	}
	client.Send <- []byte("permanent-pressure")
	oldFetch := fetchPullMessagesFunc
	oldAck := ackOfflineMessageFunc
	oldNak := nakOfflineMessageFunc
	oldUnsubscribe := unsubscribePullFunc
	t.Cleanup(func() {
		fetchPullMessagesFunc = oldFetch
		ackOfflineMessageFunc = oldAck
		nakOfflineMessageFunc = oldNak
		unsubscribePullFunc = oldUnsubscribe
	})
	fetchPullMessagesFunc = func(*nats.Subscription, int, ...nats.PullOpt) ([]*nats.Msg, error) {
		return []*nats.Msg{replayMessage(80)}, nil
	}
	ackCount := 0
	nakCount := 0
	ackOfflineMessageFunc = func(*nats.Msg) error {
		ackCount++
		return nil
	}
	nakOfflineMessageFunc = func(*nats.Msg, time.Duration) error {
		nakCount++
		return nil
	}
	unsubscribePullFunc = func(*nats.Subscription) error { return nil }

	client.handleJoin(client.ctx, Message{Type: "join", Room: "room", Payload: resumeJoinPayload(t, h, client.UserID, "room", 79)})

	require.Eventually(t, func() bool { return client.ctx.Err() != nil }, time.Second, 10*time.Millisecond)
	_, firstOpen := <-client.Send
	_, secondOpen := <-client.Send
	assert.True(t, firstOpen)
	assert.False(t, secondOpen, "retry exhaustion must close the socket queue for checkpoint resume")
	assert.Zero(t, ackCount)
	assert.Equal(t, 1, nakCount)
}

func TestClientHandleJoin_RejoinCancelsStaleReplaySingleFlight(t *testing.T) {
	h := setupTestHub()
	enableSecureReplayForTest(h)
	h.enableJetStream = true
	h.js = &scriptedPullSubscription{pull: func(string, string, ...nats.SubOpt) (*nats.Subscription, error) {
		return &nats.Subscription{}, nil
	}}
	ctx, cancel := context.WithCancel(context.Background())
	t.Cleanup(cancel)
	client := &Client{
		ID: "single-flight", UserID: "single-flight-user", Hub: h,
		Rooms: make(map[string]bool), Send: make(chan []byte, 4), ctx: ctx, cancel: cancel,
	}
	oldFetch := fetchPullMessagesFunc
	oldAck := ackOfflineMessageFunc
	oldUnsubscribe := unsubscribePullFunc
	t.Cleanup(func() {
		fetchPullMessagesFunc = oldFetch
		ackOfflineMessageFunc = oldAck
		unsubscribePullFunc = oldUnsubscribe
	})
	firstStarted := make(chan struct{})
	releaseFirst := make(chan struct{})
	var fetchCalls atomic.Int32
	fetchPullMessagesFunc = func(*nats.Subscription, int, ...nats.PullOpt) ([]*nats.Msg, error) {
		switch fetchCalls.Add(1) {
		case 1:
			close(firstStarted)
			<-releaseFirst
			return []*nats.Msg{replayMessage(20)}, nil
		case 2:
			return []*nats.Msg{replayMessage(30)}, nil
		default:
			return nil, nats.ErrTimeout
		}
	}
	ackOfflineMessageFunc = func(*nats.Msg) error { return nil }
	unsubscribePullFunc = func(*nats.Subscription) error { return nil }

	client.handleJoin(client.ctx, Message{Type: "join", Room: "room", Payload: resumeJoinPayload(t, h, client.UserID, "room", 19)})
	<-firstStarted
	client.handleJoin(client.ctx, Message{Type: "join", Room: "room", Payload: resumeJoinPayload(t, h, client.UserID, "room", 29)})
	require.Eventually(t, func() bool { return len(client.Send) == 1 }, time.Second, 10*time.Millisecond)
	close(releaseFirst)
	time.Sleep(50 * time.Millisecond)

	require.Len(t, client.Send, 1, "the canceled replay generation must not deliver stale data")
	var replayed map[string]any
	require.NoError(t, json.Unmarshal(<-client.Send, &replayed))
	assert.Equal(t, float64(30), replayed["seq"])
	require.Eventually(t, func() bool {
		client.replayMu.Lock()
		defer client.replayMu.Unlock()
		return len(client.replays) == 0
	}, time.Second, 10*time.Millisecond)
}

func TestClientLeaveRoom_CancelsReplayAndDiscardsPendingDelivery(t *testing.T) {
	h := setupTestHub()
	enableSecureReplayForTest(h)
	h.enableJetStream = true
	h.js = &scriptedPullSubscription{pull: func(string, string, ...nats.SubOpt) (*nats.Subscription, error) {
		return &nats.Subscription{}, nil
	}}
	ctx, cancel := context.WithCancel(context.Background())
	t.Cleanup(cancel)
	client := &Client{
		ID: "leave-replay", UserID: "leave-replay-user", Hub: h,
		Rooms: make(map[string]bool), Send: make(chan []byte, 2), ctx: ctx, cancel: cancel,
	}
	oldFetch := fetchPullMessagesFunc
	oldAck := ackOfflineMessageFunc
	oldUnsubscribe := unsubscribePullFunc
	t.Cleanup(func() {
		fetchPullMessagesFunc = oldFetch
		ackOfflineMessageFunc = oldAck
		unsubscribePullFunc = oldUnsubscribe
	})
	fetchStarted := make(chan struct{})
	releaseReplay := make(chan struct{})
	fetchPullMessagesFunc = func(*nats.Subscription, int, ...nats.PullOpt) ([]*nats.Msg, error) {
		close(fetchStarted)
		<-releaseReplay
		return []*nats.Msg{replayMessage(40)}, nil
	}
	ackOfflineMessageFunc = func(*nats.Msg) error { return nil }
	unsubscribePullFunc = func(*nats.Subscription) error { return nil }

	client.handleJoin(client.ctx, Message{Type: "join", Room: "room", Payload: resumeJoinPayload(t, h, client.UserID, "room", 39)})
	<-fetchStarted
	client.LeaveRoom("room")
	close(releaseReplay)
	time.Sleep(50 * time.Millisecond)

	assert.Empty(t, client.Send)
	client.replayMu.Lock()
	assert.Empty(t, client.replays)
	client.replayMu.Unlock()
}

func TestClientHandleJoin_JetStreamFailureCannotExposeCoreFallback(t *testing.T) {
	h := setupTestHub()
	h.enableJetStream = true
	h.internalSecret = "replay-signing-secret" // pragma: allowlist secret -- inert unit-test fixture
	h.Nats = &nats.Conn{}
	pullCalls := 0
	h.js = &scriptedSubscribeJetStream{
		subscribe: func(string, nats.MsgHandler, ...nats.SubOpt) (*nats.Subscription, error) {
			return nil, errors.New("JetStream subscription unavailable")
		},
		pull: func(string, string, ...nats.SubOpt) (*nats.Subscription, error) {
			pullCalls++
			return nil, errors.New("replay must stay disabled")
		},
	}
	oldCoreSubscribe := coreNATSSubscribeFunc
	coreCalls := 0
	t.Cleanup(func() { coreNATSSubscribeFunc = oldCoreSubscribe })
	coreNATSSubscribeFunc = func(*nats.Conn, string, nats.MsgHandler) (*nats.Subscription, error) {
		coreCalls++
		return &nats.Subscription{}, nil
	}
	require.Error(t, h.SubscribeToNATS(context.Background()))
	assert.False(t, h.chatReplayAvailable.Load())
	assert.Zero(t, pullCalls)
	assert.Zero(t, coreCalls, "replay-capable startup must fail instead of serving an inconsistent core mode")
}

func TestClientHandleJoin_RateLimitsReplayConsumerChurn(t *testing.T) {
	h := setupTestHub()
	enableSecureReplayForTest(h)
	h.enableJetStream = true
	var pullCalls atomic.Int32
	h.js = &scriptedPullSubscription{pull: func(string, string, ...nats.SubOpt) (*nats.Subscription, error) {
		pullCalls.Add(1)
		return &nats.Subscription{}, nil
	}}
	ctx, cancel := context.WithCancel(context.Background())
	client := &Client{
		ID: "rate-limited-replay", UserID: "rate-limited-user", Hub: h,
		Rooms: make(map[string]bool), Send: make(chan []byte, 32), ctx: ctx, cancel: cancel,
	}
	oldFetch := fetchPullMessagesFunc
	oldUnsubscribe := unsubscribePullFunc
	var replayDone sync.WaitGroup
	// The limiter permits exactly two replay workers in this scenario.  Wait
	// for both deferred unsubscribe callbacks before restoring the package-level
	// hooks; otherwise a worker can read a restored hook concurrently with the
	// test cleanup, which is a real -race failure rather than harmless logging.
	replayDone.Add(2)
	t.Cleanup(func() {
		cancel()
		replayDone.Wait()
		fetchPullMessagesFunc = oldFetch
		unsubscribePullFunc = oldUnsubscribe
	})
	fetchPullMessagesFunc = func(*nats.Subscription, int, ...nats.PullOpt) ([]*nats.Msg, error) {
		return nil, nats.ErrTimeout
	}
	unsubscribePullFunc = func(*nats.Subscription) error {
		replayDone.Done()
		return nil
	}
	beforeLimited := testutil.ToFloat64(ReplayJoinRateLimitedTotal)

	for sequence := uint64(1); sequence <= 3; sequence++ {
		room := fmt.Sprintf("room-%d", sequence)
		client.handleJoin(client.ctx, Message{
			Type: "join", Room: room,
			Payload: resumeJoinPayload(t, h, client.UserID, room, sequence),
		})
	}

	require.Eventually(t, func() bool { return pullCalls.Load() == 2 }, time.Second, 10*time.Millisecond)
	assert.Equal(t, int32(2), pullCalls.Load(), "join flood must stay within the limiter burst")
	assert.Equal(t, beforeLimited+1, testutil.ToFloat64(ReplayJoinRateLimitedTotal))
	client.mu.Lock()
	assert.True(t, client.Rooms["room-3"], "a rate-limited third join must still establish live membership")
	client.mu.Unlock()
}

func TestResumeToken_IsOpaqueBoundAndExpiring(t *testing.T) {
	h := setupTestHub()
	enableSecureReplayForTest(h)
	originalNow := resumeTokenNowFunc
	issuedAt := time.Date(2026, time.August, 26, 12, 0, 0, 0, time.UTC)
	resumeTokenNowFunc = func() time.Time { return issuedAt }
	t.Cleanup(func() { resumeTokenNowFunc = originalNow })

	token, err := h.issueResumeToken("user-a", "room-a", "CHAT_EVENTS", 42)
	require.NoError(t, err)
	sequence, err := h.verifyResumeToken(token, "user-a", "room-a")
	require.NoError(t, err)
	assert.Equal(t, uint64(42), sequence)

	_, err = h.verifyResumeToken("x"+token[1:], "user-a", "room-a")
	assert.Error(t, err, "tampering must invalidate the HMAC")
	_, err = h.verifyResumeToken(token, "user-b", "room-a")
	assert.Error(t, err, "tokens must be bound to the authenticated user")
	_, err = h.verifyResumeToken(token, "user-a", "room-b")
	assert.Error(t, err, "tokens must be bound to the joined room")
	h.chatStreamIncarnation = "replacement-stream-incarnation"
	_, err = h.verifyResumeToken(token, "user-a", "room-a")
	assert.Error(t, err, "stream recreation must invalidate old cursors")
	h.chatStreamIncarnation = "test-stream-incarnation"
	resumeTokenNowFunc = func() time.Time { return issuedAt.Add(resumeTokenTTL + time.Second) }
	_, err = h.verifyResumeToken(token, "user-a", "room-a")
	assert.Error(t, err, "expired cursors must fail closed")
}

func TestClientHandleJoin_RejectsUnsignedCursorButKeepsLiveMembership(t *testing.T) {
	h := setupTestHub()
	enableSecureReplayForTest(h)
	pullCalls := 0
	h.js = &scriptedPullSubscription{pull: func(string, string, ...nats.SubOpt) (*nats.Subscription, error) {
		pullCalls++
		return &nats.Subscription{}, nil
	}}
	ctx, cancel := context.WithCancel(context.Background())
	t.Cleanup(cancel)
	client := &Client{
		ID: "unsigned-cursor", UserID: "cursor-user", Hub: h,
		Rooms: make(map[string]bool), Send: make(chan []byte, 1), ctx: ctx, cancel: cancel,
	}

	client.handleJoin(client.ctx, Message{Type: "join", Room: "room", Payload: json.RawMessage(`{"last_seq":999999}`)})

	assert.Zero(t, pullCalls, "a browser-controlled integer must never choose the durable replay cursor")
	client.mu.Lock()
	assert.True(t, client.Rooms["room"])
	client.mu.Unlock()
	var errorFrame map[string]any
	require.NoError(t, json.Unmarshal(<-client.Send, &errorFrame))
	assert.Equal(t, "resume_token_required", errorFrame["code"])
	assert.Equal(t, "room", errorFrame["room"])
}

func TestClientDeliverOfflineMessages_TerminatesCrossRoomReplay(t *testing.T) {
	h := setupTestHub()
	enableSecureReplayForTest(h)
	client := &Client{UserID: "replay-user", Hub: h, ctx: context.Background(), Send: make(chan []byte, 1)}
	message := replayMessage(44)
	message.Data = []byte(`{"type":"new_message","room":"other-room","payload":{"chat_id":"other-room"}}`)
	oldTerm := termOfflineMessageFunc
	termCalls := 0
	termOfflineMessageFunc = func(*nats.Msg) error { termCalls++; return nil }
	t.Cleanup(func() { termOfflineMessageFunc = oldTerm })
	found := true
	maxSequence := uint64(43)

	continued := client.deliverOfflineMessageBatch(context.Background(), "room", []*nats.Msg{message}, "", &found, &maxSequence)

	assert.True(t, continued)
	assert.Equal(t, 1, termCalls)
	assert.Empty(t, client.Send)
	assert.Equal(t, uint64(43), maxSequence, "a mismatched envelope must not advance the checkpoint")
}

func TestHubBroadcast_SequencedBackpressureDisconnectsBeforeLaterSequence(t *testing.T) {
	h := setupTestHub()
	enableSecureReplayForTest(h)
	ctx, cancel := context.WithCancel(context.Background())
	client := &Client{
		ID: "backpressured", UserID: "backpressured-user", Hub: h,
		Rooms: map[string]bool{"room": true}, Send: make(chan []byte, 1), ctx: ctx, cancel: cancel,
	}
	h.Rooms["room"] = map[*Client]bool{client: true}
	client.Send <- []byte("already-full")

	h.broadcastMessage(context.Background(), &Message{Type: "new_message", Room: "room", MessageReplayMetadata: &MessageReplayMetadata{Seq: 10, Stream: "CHAT_EVENTS"}})
	require.Error(t, client.ctx.Err(), "dropping a sequenced frame must invalidate the connection")
	assert.Equal(t, "already-full", string(<-client.Send))
	h.broadcastMessage(context.Background(), &Message{Type: "new_message", Room: "room", MessageReplayMetadata: &MessageReplayMetadata{Seq: 11, Stream: "CHAT_EVENTS"}})
	assert.Empty(t, client.Send, "a disconnected client must never accept a later sequence")
}

func TestHubRun_SerializesSequencedChatAcrossBroadcastWorkers(t *testing.T) {
	h := setupTestHub()
	h.broadcastWorkers = 2
	oldBroadcast := broadcastMessageFunc
	t.Cleanup(func() { broadcastMessageFunc = oldBroadcast })
	firstStarted := make(chan struct{})
	releaseFirst := make(chan struct{})
	var orderMu sync.Mutex
	order := make([]uint64, 0, 2)
	broadcastMessageFunc = func(_ *Hub, _ context.Context, message *Message) {
		if message.Seq == 1 {
			close(firstStarted)
			<-releaseFirst
		}
		orderMu.Lock()
		order = append(order, message.Seq)
		orderMu.Unlock()
	}
	ctx, cancel := context.WithCancel(context.Background())
	done := make(chan struct{})
	go func() {
		h.Run(ctx)
		close(done)
	}()
	h.Broadcast <- &Message{Type: "new_message", Room: "room", MessageReplayMetadata: &MessageReplayMetadata{Seq: 1}}
	<-firstStarted
	h.Broadcast <- &Message{Type: "new_message", Room: "room", MessageReplayMetadata: &MessageReplayMetadata{Seq: 2}}
	time.Sleep(25 * time.Millisecond)
	close(releaseFirst)
	require.Eventually(t, func() bool {
		orderMu.Lock()
		defer orderMu.Unlock()
		return len(order) == 2
	}, time.Second, 10*time.Millisecond)
	cancel()
	<-done

	orderMu.Lock()
	assert.Equal(t, []uint64{1, 2}, order)
	orderMu.Unlock()
}

func TestHubRun_SequencedLaneOverflowDisconnectsRoomClients(t *testing.T) {
	h := setupTestHub()
	h.Broadcast = make(chan *Message, 1)
	h.broadcastWorkers = 1
	clientCtx, cancelClient := context.WithCancel(context.Background())
	client := &Client{
		ID: "lane-overflow", UserID: "lane-user", Hub: h,
		Rooms: map[string]bool{"room": true}, Send: make(chan []byte, 1),
		ctx: clientCtx, cancel: cancelClient,
	}
	h.Rooms["room"] = map[*Client]bool{client: true}
	oldBroadcast := broadcastMessageFunc
	t.Cleanup(func() { broadcastMessageFunc = oldBroadcast })
	firstStarted := make(chan struct{})
	releaseFirst := make(chan struct{})
	broadcastMessageFunc = func(_ *Hub, _ context.Context, message *Message) {
		if message.Seq == 1 {
			close(firstStarted)
			<-releaseFirst
		}
	}
	runCtx, cancelRun := context.WithCancel(context.Background())
	done := make(chan struct{})
	go func() {
		h.Run(runCtx)
		close(done)
	}()

	h.Broadcast <- &Message{Type: "new_message", Room: "room", MessageReplayMetadata: &MessageReplayMetadata{Seq: 1}}
	<-firstStarted
	h.Broadcast <- &Message{Type: "new_message", Room: "room", MessageReplayMetadata: &MessageReplayMetadata{Seq: 2}}
	require.Eventually(t, func() bool { return len(h.Broadcast) == 0 }, time.Second, time.Millisecond)
	h.Broadcast <- &Message{Type: "new_message", Room: "room", MessageReplayMetadata: &MessageReplayMetadata{Seq: 3}}
	require.Eventually(t, func() bool { return client.ctx.Err() != nil }, time.Second, time.Millisecond)

	close(releaseFirst)
	cancelRun()
	<-done
}

func replayMessage(sequence uint64) *nats.Msg {
	return &nats.Msg{
		Subject: "chat.room",
		Reply: fmt.Sprintf(
			"$JS.ACK.CHAT_EVENTS.offline-replay.1.%d.%d.1690000000000000000.0",
			sequence,
			sequence,
		),
		Sub:  &nats.Subscription{},
		Data: []byte(fmt.Sprintf(`{"type":"new_message","room":"room","payload":{"chat_id":"room","n":%d}}`, sequence)),
	}
}

func replayMessageRange(first, last uint64) []*nats.Msg {
	messages := make([]*nats.Msg, 0, last-first+1)
	for sequence := first; sequence <= last; sequence++ {
		messages = append(messages, replayMessage(sequence))
	}
	return messages
}

func TestClientCleanupReadPump_QueuesUnregisterAndLogsCloseError(t *testing.T) {
	h := setupTestHub()
	h.Unregister = make(chan *Client, 1)
	ctx, cancel := context.WithCancel(context.Background())
	client := &Client{
		ID:     "cleanup-error",
		Hub:    h,
		Conn:   &recordingSession{closeErr: errors.New("close failed")},
		Send:   make(chan []byte, 1),
		ctx:    ctx,
		cancel: cancel,
	}
	client.cleanupReadPump()
	select {
	case got := <-h.Unregister:
		assert.Same(t, client, got)
	default:
		t.Fatal("cleanup should queue the client for unregister")
	}
}

func TestClientProcessNextMessage_LogsNonNormalReadError(t *testing.T) {
	h := setupTestHub()
	client := &Client{
		Hub:  h,
		Conn: &readErrorSession{err: errors.New("transport failed")},
		ctx:  context.Background(),
	}
	assert.False(t, client.processNextMessage(client.ctx))
}

func TestClientHandleJoin_MalformedPayloadAndReplayTrigger(t *testing.T) {
	h := setupTestHub()
	h.js = &scriptedPullSubscription{pull: func(string, string, ...nats.SubOpt) (*nats.Subscription, error) {
		return nil, errors.New("no replay backend")
	}}
	srv, _ := newConnPair(t)
	c := newClientOn(h, srv, "join-runtime", "join-user")
	c.handleJoin(c.ctx, Message{Type: "join", Room: "room", Payload: []byte(`{not-json`)})
	c.handleJoin(c.ctx, Message{Type: "join", Room: "room", Payload: []byte(`{"last_seq":1}`)})
	var errorFrame map[string]any
	require.NoError(t, json.Unmarshal(<-c.Send, &errorFrame))
	assert.Equal(t, "resume_token_required", errorFrame["code"])

	c.cleanupReadPump()
	_, open := <-c.Send
	assert.False(t, open)
}

func TestClientDisconnect_DefaultHubContextClosesSend(t *testing.T) {
	h := setupTestHub()
	c := &Client{ID: "default-context", Hub: h, Send: make(chan []byte, 1), ctx: context.Background()}
	c.Disconnect(1000, "done")
	_, open := <-c.Send
	assert.False(t, open)
}

func TestClientHandleMessage_JetStreamPublishErrorIsContained(t *testing.T) {
	h := setupTestHub()
	h.enableJetStream = true
	h.Nats = &nats.Conn{}
	h.js = &scriptedPublishJetStream{publishErr: errors.New("publish failed")}
	c := &Client{
		ID: "publish-error", UserID: "publish-user", Hub: h,
		Send: make(chan []byte, 1), Rooms: map[string]bool{"room": true}, ctx: context.Background(),
	}
	c.handleMessage(Message{Type: "message", Room: "room"}, []byte(`{"type":"message"}`))
}

func TestClientHandleMessage_InvalidRawPayloadIsContained(t *testing.T) {
	h := setupTestHub()
	h.Nats = &nats.Conn{}
	c := &Client{
		ID: "invalid-payload", UserID: "canonical-user", Hub: h,
		Send: make(chan []byte, 1), Rooms: map[string]bool{"room": true}, ctx: context.Background(),
	}

	assert.NotPanics(t, func() {
		c.handleMessage(
			Message{Type: "message", Room: "room", Payload: json.RawMessage(`{`)},
			[]byte(`{"type":"message"}`),
		)
	})
}
