package hub

import (
	"context"
	"encoding/json"
	"errors"
	"testing"
	"time"

	"github.com/nats-io/nats.go"
	"github.com/quic-go/webtransport-go"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

type scriptedPullSubscription struct {
	nats.JetStreamContext
	pull func(string, string, ...nats.SubOpt) (*nats.Subscription, error)
}

func (s *scriptedPullSubscription) PullSubscribe(subject, durable string, opts ...nats.SubOpt) (*nats.Subscription, error) {
	return s.pull(subject, durable, opts...)
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
	client := &Client{Hub: h, ctx: context.Background(), Send: make(chan []byte, 4)}
	oldAck := ackOfflineMessageFunc
	t.Cleanup(func() { ackOfflineMessageFunc = oldAck })
	ackOfflineMessageFunc = func(*nats.Msg) error { return errors.New("ack unavailable") }
	msgs := []*nats.Msg{
		{Header: nats.Header{"Nats-Msg-Id": []string{"before"}}, Data: []byte(`{"type":"message","payload":{"n":0}}`)},
		{Header: nats.Header{"Nats-Msg-Id": []string{"resume-7"}}, Data: []byte(`{"type":"message","payload":{"n":1}}`)},
		{Reply: "$JS.ACK.CHAT_EVENTS.consumer.1.42.7.123456789.0", Sub: &nats.Subscription{}, Data: []byte(`{"type":"message","payload":{"n":2}}`)},
		{Data: []byte("not-json")},
	}

	client.deliverOfflineMessages(msgs, 0, "resume-7")
	first := <-client.Send
	second := <-client.Send
	var replayed map[string]any
	require.NoError(t, json.Unmarshal(first, &replayed))
	assert.Equal(t, true, replayed["replayed"])
	assert.Equal(t, float64(42), replayed["seq"])
	assert.Equal(t, `not-json`, string(second))

	cancelledCtx, cancel := context.WithCancel(context.Background())
	cancel()
	client.ctx = cancelledCtx
	client.deliverOfflineMessages([]*nats.Msg{{Data: []byte(`{"type":"message"}`)}}, 0, "")
	assert.Empty(t, client.Send)
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
	assert.False(t, client.processNextMessage())
}

func TestClientHandleJoin_MalformedPayloadAndReplayTrigger(t *testing.T) {
	h := setupTestHub()
	h.js = &scriptedPullSubscription{pull: func(string, string, ...nats.SubOpt) (*nats.Subscription, error) {
		return nil, errors.New("no replay backend")
	}}
	srv, _ := newConnPair(t)
	c := newClientOn(h, srv, "join-topup", "join-user")
	c.handleJoin(Message{Type: "join", Room: "room", Payload: []byte(`{not-json`)})
	c.handleJoin(Message{Type: "join", Room: "room", Payload: []byte(`{"last_seq":1}`)})

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
