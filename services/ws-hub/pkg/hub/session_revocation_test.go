package hub

import (
	"bufio"
	"context"
	"errors"
	"io"
	"net"
	"strconv"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/alicebob/miniredis/v2"
	"github.com/google/uuid"
	"github.com/gorilla/websocket"
	"github.com/prometheus/client_golang/prometheus/testutil"
	goredis "github.com/redis/go-redis/v9"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// revocationTestSession is deliberately synchronized so `go test -race` can
// exercise a concurrent revocation and an in-flight client action.
type revocationTestSession struct {
	mu          sync.Mutex
	frames      [][]byte
	closed      bool
	closeCalls  int
	writes      []recordedSessionWrite
	transportID string
	deadlineErr error
	writeErr    error
	closeErr    error
}

func (s *revocationTestSession) ReadMessage() (int, []byte, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	if len(s.frames) == 0 {
		return 0, nil, io.EOF
	}
	frame := append([]byte(nil), s.frames[0]...)
	s.frames = s.frames[1:]
	return websocket.TextMessage, frame, nil
}

func (s *revocationTestSession) SetReadLimit(int64) {}

func (s *revocationTestSession) SetReadDeadline(time.Time) error { return nil }

func (s *revocationTestSession) SetWriteDeadline(time.Time) error { return s.deadlineErr }

func (s *revocationTestSession) SetPongHandler(func(string) error) {}

func (s *revocationTestSession) WriteMessage(messageType int, data []byte) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.writes = append(s.writes, recordedSessionWrite{
		messageType: messageType,
		data:        append([]byte(nil), data...),
	})
	return s.writeErr
}

func (s *revocationTestSession) Close() error {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.closed = true
	s.closeCalls++
	return s.closeErr
}

func (s *revocationTestSession) RemoteAddr() net.Addr { return &net.TCPAddr{} }

func (s *revocationTestSession) TransportType() string { return s.transportID }

func (s *revocationTestSession) wasClosed() bool {
	s.mu.Lock()
	defer s.mu.Unlock()
	return s.closed
}

func (s *revocationTestSession) closeCount() int {
	s.mu.Lock()
	defer s.mu.Unlock()
	return s.closeCalls
}

func newRevocationTestClient(h *Hub, id, userID, jti, transport string, frames ...[]byte) (*Client, *revocationTestSession) {
	ctx, cancel := context.WithCancel(context.Background())
	session := &revocationTestSession{frames: frames, transportID: transport}
	return &Client{
		ID:         id,
		UserID:     userID,
		SessionJTI: jti,
		Conn:       session,
		Rooms:      make(map[string]bool),
		Send:       make(chan []byte, 4),
		Hub:        h,
		ctx:        ctx,
		cancel:     cancel,
	}, session
}

func TestDisconnectSessionTargetsOnlyMatchingJTIAcrossTransports(t *testing.T) {
	h := setupTestHub()
	h.Unregister = make(chan *Client, 2)
	targetJTI := uuid.NewString()
	otherJTI := uuid.NewString()
	target, targetSession := newRevocationTestClient(h, "websocket-client", "same-user", targetJTI, "websocket")
	other, otherSession := newRevocationTestClient(h, "webtransport-client", "same-user", otherJTI, "webtransport")

	h.mu.Lock()
	h.Clients[target.ID] = target
	h.Clients[other.ID] = other
	h.mu.Unlock()

	h.DisconnectSession(targetJTI, websocket.ClosePolicyViolation, "Session revoked")

	require.Eventually(t, targetSession.wasClosed, time.Second, 10*time.Millisecond)
	assert.Error(t, target.ctx.Err())
	assert.True(t, target.sessionRevoked.Load())
	assert.False(t, otherSession.wasClosed(), "a same-user session with another JTI must remain live")
	assert.NoError(t, other.ctx.Err())
	assert.False(t, other.sessionRevoked.Load())
}

func TestProcessNextMessageFailsClosedWhenTombstoneCheckFails(t *testing.T) {
	h := setupTestHub()
	deadlineObserved := false
	h.sessionRevocationCheck = func(ctx context.Context, jti string) error {
		deadline, ok := ctx.Deadline()
		deadlineObserved = ok && time.Until(deadline) <= sessionActionRevocationTimeout
		assert.NotEmpty(t, jti)
		return errors.New("revocation store unavailable")
	}
	client, session := newRevocationTestClient(
		h,
		"blocked-client",
		"user-1",
		uuid.NewString(),
		"websocket",
		[]byte(`{"type":"join","room":"must-not-join"}`),
	)

	assert.False(t, client.processNextMessage(context.Background()))
	assert.True(t, deadlineObserved)
	assert.True(t, client.sessionRevoked.Load())
	assert.Empty(t, h.Rooms, "the rejected action must never reach the room handler")
	assert.True(t, session.wasClosed())
}

func TestProcessNextMessageFailsClosedWithoutSessionJTI(t *testing.T) {
	h := setupTestHub()
	h.sessionRevocationCheck = func(context.Context, string) error {
		t.Fatal("revocation lookup must not run without the ticket JTI")
		return nil
	}
	client, session := newRevocationTestClient(
		h,
		"missing-jti-client",
		"user-1",
		"",
		"webtransport",
		[]byte(`{"type":"leave","room":"room-1"}`),
	)

	assert.False(t, client.processNextMessage(context.Background()))
	assert.True(t, client.sessionRevoked.Load())
	assert.True(t, session.wasClosed())
}

func TestAuthorizeAndHandleIncomingMessageFailsClosedForAllRevocationStates(t *testing.T) {
	t.Run("already revoked", func(t *testing.T) {
		h := setupTestHub()
		client, _ := newRevocationTestClient(h, "revoked", "user-1", uuid.NewString(), "websocket")
		client.sessionRevoked.Store(true)
		err := client.authorizeAndHandleIncomingMessage(context.Background(), Message{Type: "leave"}, nil)
		assert.Error(t, err)
	})

	t.Run("missing hub", func(t *testing.T) {
		client, _ := newRevocationTestClient(nil, "orphan", "user-1", uuid.NewString(), "websocket")
		err := client.authorizeAndHandleIncomingMessage(context.Background(), Message{Type: "leave"}, nil)
		assert.Error(t, err)
	})

	t.Run("missing checker", func(t *testing.T) {
		h := setupTestHub()
		h.sessionRevocationCheck = nil
		client, _ := newRevocationTestClient(h, "unchecked", "user-1", uuid.NewString(), "websocket")
		err := client.authorizeAndHandleIncomingMessage(context.Background(), Message{Type: "leave"}, nil)
		assert.Error(t, err)
	})

	t.Run("revoked during lookup", func(t *testing.T) {
		h := setupTestHub()
		client, _ := newRevocationTestClient(h, "mid-check", "user-1", uuid.NewString(), "websocket")
		h.sessionRevocationCheck = func(context.Context, string) error {
			client.sessionRevoked.Store(true)
			return nil
		}
		err := client.authorizeAndHandleIncomingMessage(context.Background(), Message{Type: "leave"}, nil)
		assert.Error(t, err)
	})
}

func TestCloseTransportWithControlFrameSerializesErrorsAndPhysicalClose(t *testing.T) {
	h := setupTestHub()
	client, session := newRevocationTestClient(h, "close-errors", "user-1", uuid.NewString(), "websocket")
	session.deadlineErr = errors.New("deadline failed")
	session.writeErr = errors.New("write failed")
	session.closeErr = errors.New("close failed")

	client.closeTransportWithControlFrame(websocket.ClosePolicyViolation, "Session revoked")
	client.closeTransportWithControlFrame(websocket.ClosePolicyViolation, "Session revoked")

	assert.Equal(t, 1, session.closeCount())
	assert.Len(t, session.writes, 1)

	withoutTransport := &Client{Hub: h}
	assert.NotPanics(t, func() {
		withoutTransport.closeTransportWithControlFrame(websocket.ClosePolicyViolation, "Session revoked")
		withoutTransport.closeTransport("unused")
	})
}

func TestDisconnectSessionRejectsEmptyMissingAndLoggerlessTargets(t *testing.T) {
	assert.NotPanics(t, func() {
		var h *Hub
		h.DisconnectSession(uuid.NewString(), websocket.ClosePolicyViolation, "Session revoked")
	})

	h := setupTestHub()
	h.DisconnectSession("", websocket.ClosePolicyViolation, "Session revoked")
	h.DisconnectSession(uuid.NewString(), websocket.ClosePolicyViolation, "Session revoked")

	loggerless := &Hub{
		Clients:    make(map[string]*Client),
		Rooms:      make(map[string]map[*Client]bool),
		Register:   make(chan *Client),
		Unregister: make(chan *Client, 1),
	}
	jti := uuid.NewString()
	client, session := newRevocationTestClient(loggerless, "loggerless", "user-1", jti, "websocket")
	loggerless.Clients[client.ID] = client
	assert.NotPanics(t, func() {
		loggerless.DisconnectSession(jti, websocket.ClosePolicyViolation, "Session revoked")
	})
	assert.True(t, session.wasClosed())
}

func TestSessionRevocationListenerClosesPublishedJTIAndStops(t *testing.T) {
	baseline := testutil.ToFloat64(ActiveGoroutines)
	mr := miniredis.RunT(t)
	redisClient := goredis.NewClient(&goredis.Options{Addr: mr.Addr()})
	t.Cleanup(func() { require.NoError(t, redisClient.Close()) })
	h := trackTestHub(NewHub(nil, newTestLogger(), &mockAuthClient{allowed: true}, nil, nil, redisClient))
	t.Cleanup(h.Stop)
	assert.Equal(t, baseline+1, testutil.ToFloat64(ActiveGoroutines), "hub limiter is tracked")
	h.Unregister = make(chan *Client, 2)
	targetJTI := uuid.NewString()
	target, targetSession := newRevocationTestClient(h, "target", "user-1", targetJTI, "websocket")
	other, otherSession := newRevocationTestClient(h, "other", "user-1", uuid.NewString(), "webtransport")

	h.mu.Lock()
	h.Clients[target.ID] = target
	h.Clients[other.ID] = other
	h.mu.Unlock()

	require.NoError(t, h.StartSessionRevocationListener(context.Background()))
	assert.Equal(t, baseline+2, testutil.ToFloat64(ActiveGoroutines), "listener is tracked")
	require.NoError(t, redisClient.Publish(context.Background(), sessionRevocationsChannel, targetJTI).Err())
	require.Eventually(t, targetSession.wasClosed, time.Second, 10*time.Millisecond)
	assert.True(t, target.sessionRevoked.Load())
	assert.False(t, otherSession.wasClosed())

	h.Stop()
	assert.Nil(t, h.sessionRevocationCancel)
	assert.Equal(t, baseline, testutil.ToFloat64(ActiveGoroutines), "Stop joins listener and limiter")
}

func TestStartSessionRevocationListenerFailsClosedAndReplacesPriorLifecycle(t *testing.T) {
	t.Run("nil hub", func(t *testing.T) {
		var h *Hub
		assert.Error(t, h.StartSessionRevocationListener(context.Background()))
	})

	t.Run("missing durable redis", func(t *testing.T) {
		h := setupTestHub()
		assert.Error(t, h.StartSessionRevocationListener(context.Background()))
	})

	t.Run("stopped hub rejects a late listener bootstrap", func(t *testing.T) {
		mr := miniredis.RunT(t)
		redisClient := goredis.NewClient(&goredis.Options{Addr: mr.Addr()})
		t.Cleanup(func() { require.NoError(t, redisClient.Close()) })
		h := NewHub(nil, newTestLogger(), nil, nil, nil, redisClient)
		h.Stop()
		assert.ErrorContains(t, h.StartSessionRevocationListener(context.Background()), "after hub shutdown")
	})

	t.Run("unavailable durable redis", func(t *testing.T) {
		redisClient := goredis.NewClient(&goredis.Options{
			Addr:        "127.0.0.1:1",
			DialTimeout: 10 * time.Millisecond,
			MaxRetries:  0,
		})
		t.Cleanup(func() { require.NoError(t, redisClient.Close()) })
		h := NewHub(nil, newTestLogger(), nil, nil, nil, redisClient)
		t.Cleanup(h.Stop)
		assert.Error(t, h.StartSessionRevocationListener(context.Background()))
	})

	t.Run("replaces prior listener cancellation", func(t *testing.T) {
		mr := miniredis.RunT(t)
		redisClient := goredis.NewClient(&goredis.Options{Addr: mr.Addr()})
		t.Cleanup(func() { require.NoError(t, redisClient.Close()) })
		h := NewHub(nil, newTestLogger(), nil, nil, nil, redisClient)
		t.Cleanup(h.Stop)
		cancelled := false
		h.sessionRevocationCancel = func() { cancelled = true }
		require.NoError(t, h.StartSessionRevocationListener(context.Background()))
		assert.True(t, cancelled)
	})
}

// stalledSubscribeServer accepts the Pub/Sub command but deliberately withholds
// its acknowledgement. This models a Redis-side stall after the client has a
// concrete PubSub connection, which is the window where Hub.Stop must own and
// close the startup resource rather than merely cancelling a context.
type stalledSubscribeServer struct {
	listener       net.Listener
	subscribeSeen  chan struct{}
	release        chan struct{}
	serverFinished chan struct{}
	once           sync.Once
}

func newStalledSubscribeServer(t *testing.T) *stalledSubscribeServer {
	t.Helper()
	listener, err := net.Listen("tcp", "127.0.0.1:0")
	require.NoError(t, err)
	server := &stalledSubscribeServer{
		listener:       listener,
		subscribeSeen:  make(chan struct{}),
		release:        make(chan struct{}),
		serverFinished: make(chan struct{}),
	}
	go func() {
		defer close(server.serverFinished)
		connection, acceptErr := listener.Accept()
		if acceptErr != nil {
			return
		}
		defer connection.Close()

		reader := bufio.NewReader(connection)
		for {
			command, readErr := readRESPCommand(reader)
			if readErr != nil {
				return
			}
			if len(command) > 0 && strings.EqualFold(command[0], "subscribe") {
				close(server.subscribeSeen)
				<-server.release
				return
			}
			// go-redis probes HELLO even when Protocol is explicitly RESP2. Make
			// the mock look like a pre-RESP3 endpoint so that it falls back to
			// RESP2, then acknowledge any non-subscription setup commands.
			reply := "+OK\r\n"
			if len(command) > 0 && strings.EqualFold(command[0], "hello") {
				reply = "-ERR unknown command 'HELLO'\r\n"
			}
			if _, writeErr := io.WriteString(connection, reply); writeErr != nil {
				return
			}
		}
	}()
	t.Cleanup(func() {
		server.once.Do(func() { close(server.release) })
		require.NoError(t, listener.Close())
		select {
		case <-server.serverFinished:
		case <-time.After(time.Second):
			t.Error("stalled Redis test server did not exit")
		}
	})
	return server
}

func (s *stalledSubscribeServer) Addr() string {
	return s.listener.Addr().String()
}

func readRESPCommand(reader *bufio.Reader) ([]string, error) {
	header, err := reader.ReadString('\n')
	if err != nil {
		return nil, err
	}
	if !strings.HasPrefix(header, "*") {
		return nil, errors.New("expected RESP array")
	}
	count, err := strconv.Atoi(strings.TrimSpace(strings.TrimPrefix(header, "*")))
	if err != nil || count < 1 {
		return nil, errors.New("invalid RESP array length")
	}
	command := make([]string, 0, count)
	for range count {
		lengthHeader, lengthErr := reader.ReadString('\n')
		if lengthErr != nil {
			return nil, lengthErr
		}
		if !strings.HasPrefix(lengthHeader, "$") {
			return nil, errors.New("expected RESP bulk string")
		}
		length, parseErr := strconv.Atoi(strings.TrimSpace(strings.TrimPrefix(lengthHeader, "$")))
		if parseErr != nil || length < 0 {
			return nil, errors.New("invalid RESP bulk string length")
		}
		payload := make([]byte, length+2)
		if _, readErr := io.ReadFull(reader, payload); readErr != nil {
			return nil, readErr
		}
		if !strings.HasSuffix(string(payload), "\r\n") {
			return nil, errors.New("malformed RESP bulk string")
		}
		command = append(command, string(payload[:length]))
	}
	return command, nil
}

func TestStopOwnsSessionRevocationStartupBeforeSubscribeAcknowledgement(t *testing.T) {
	server := newStalledSubscribeServer(t)
	redisClient := goredis.NewClient(&goredis.Options{
		Addr:            server.Addr(),
		Protocol:        2,
		DisableIdentity: true,
		DialTimeout:     time.Second,
		ReadTimeout:     -1,
		MaxRetries:      0,
	})
	t.Cleanup(func() { require.NoError(t, redisClient.Close()) })
	h := NewHub(nil, newTestLogger(), nil, nil, nil, redisClient)
	t.Cleanup(h.Stop)

	startResult := make(chan error, 1)
	go func() { startResult <- h.StartSessionRevocationListener(context.Background()) }()

	select {
	case <-server.subscribeSeen:
	case <-time.After(time.Second):
		t.Fatal("listener did not reach the unacknowledged Subscribe state")
	}

	stopReturned := make(chan struct{})
	go func() {
		h.Stop()
		close(stopReturned)
	}()
	select {
	case <-stopReturned:
	case <-time.After(time.Second):
		t.Error("Hub.Stop did not join the unacknowledged subscription startup")
	}
	select {
	case err := <-startResult:
		assert.Error(t, err)
	case <-time.After(time.Second):
		t.Error("subscription bootstrap was not cancelled by Hub.Stop")
	}
}

func TestSessionRevocationStartupTimeoutFailsClosed(t *testing.T) {
	listener, err := net.Listen("tcp", "127.0.0.1:0")
	require.NoError(t, err)
	release := make(chan struct{})
	serverFinished := make(chan struct{})
	go func() {
		defer close(serverFinished)
		connection, acceptErr := listener.Accept()
		if acceptErr != nil {
			return
		}
		defer connection.Close()
		<-release // Withhold every setup response until the caller times out.
	}()
	t.Cleanup(func() {
		close(release)
		require.NoError(t, listener.Close())
		select {
		case <-serverFinished:
		case <-time.After(time.Second):
			t.Error("black-hole Redis test server did not exit")
		}
	})

	redisClient := goredis.NewClient(&goredis.Options{
		Addr:            listener.Addr().String(),
		Protocol:        2,
		DisableIdentity: true,
		DialTimeout:     time.Second,
		ReadTimeout:     -1,
		MaxRetries:      0,
	})
	t.Cleanup(func() { require.NoError(t, redisClient.Close()) })
	h := NewHub(nil, newTestLogger(), nil, nil, nil, redisClient)
	h.sessionRevocationSubscribeTimeout = 25 * time.Millisecond
	t.Cleanup(h.Stop)

	err = h.StartSessionRevocationListener(context.Background())
	require.Error(t, err)
	assert.ErrorIs(t, err, context.DeadlineExceeded)
	h.lifecycleMu.Lock()
	assert.Nil(t, h.sessionRevocationCancel, "a timed-out bootstrap must not leave a degraded listener")
	h.lifecycleMu.Unlock()
}

func TestStopOwnsSessionRevocationBootstrapBeforePubSubExists(t *testing.T) {
	listener, err := net.Listen("tcp", "127.0.0.1:0")
	require.NoError(t, err)
	accepted := make(chan struct{})
	release := make(chan struct{})
	serverFinished := make(chan struct{})
	go func() {
		defer close(serverFinished)
		connection, acceptErr := listener.Accept()
		if acceptErr != nil {
			return
		}
		defer connection.Close()
		close(accepted)
		<-release // Do not answer HELLO, so no PubSub handle can be returned.
	}()
	t.Cleanup(func() {
		close(release)
		require.NoError(t, listener.Close())
		select {
		case <-serverFinished:
		case <-time.After(time.Second):
			t.Error("black-hole Redis test server did not exit")
		}
	})

	redisClient := goredis.NewClient(&goredis.Options{
		Addr:            listener.Addr().String(),
		Protocol:        2,
		DisableIdentity: true,
		DialTimeout:     time.Second,
		ReadTimeout:     -1,
		MaxRetries:      0,
	})
	t.Cleanup(func() { require.NoError(t, redisClient.Close()) })
	h := NewHub(nil, newTestLogger(), nil, nil, nil, redisClient)
	h.sessionRevocationSubscribeTimeout = time.Second
	t.Cleanup(h.Stop)

	startResult := make(chan error, 1)
	go func() { startResult <- h.StartSessionRevocationListener(context.Background()) }()
	select {
	case <-accepted:
	case <-time.After(time.Second):
		t.Fatal("listener did not enter the pre-PubSub bootstrap phase")
	}

	stopReturned := make(chan struct{})
	go func() {
		h.Stop()
		close(stopReturned)
	}()
	select {
	case <-stopReturned:
	case <-time.After(time.Second):
		t.Error("Hub.Stop did not join the pre-PubSub bootstrap")
	}
	select {
	case err := <-startResult:
		assert.Error(t, err)
	case <-time.After(time.Second):
		t.Error("pre-PubSub bootstrap was not cancelled by Hub.Stop")
	}
}

func TestReplacingSessionRevocationListenerRetainsNewLifecycleOwner(t *testing.T) {
	mr := miniredis.RunT(t)
	redisClient := goredis.NewClient(&goredis.Options{Addr: mr.Addr()})
	t.Cleanup(func() { require.NoError(t, redisClient.Close()) })
	h := NewHub(nil, newTestLogger(), nil, nil, nil, redisClient)
	t.Cleanup(h.Stop)
	require.NoError(t, h.StartSessionRevocationListener(context.Background()))

	oldClose := closeSessionRevocationPubSubFunc
	t.Cleanup(func() { closeSessionRevocationPubSubFunc = oldClose })
	firstCloseEntered := make(chan struct{})
	allowFirstClose := make(chan struct{})
	var allowFirstCloseOnce sync.Once
	releaseFirstClose := func() {
		allowFirstCloseOnce.Do(func() { close(allowFirstClose) })
	}
	t.Cleanup(releaseFirstClose)
	var firstClose sync.Once
	closeSessionRevocationPubSubFunc = func(pubsub *goredis.PubSub) error {
		block := false
		firstClose.Do(func() {
			block = true
			close(firstCloseEntered)
		})
		if block {
			<-allowFirstClose
		}
		return pubsub.Close()
	}

	replacement := make(chan error, 1)
	go func() { replacement <- h.StartSessionRevocationListener(context.Background()) }()
	select {
	case <-firstCloseEntered:
	case <-time.After(time.Second):
		t.Fatal("replacement did not cancel the prior listener")
	}
	h.lifecycleMu.Lock()
	assert.Equal(t, uint64(2), h.sessionRevocationGeneration)
	assert.NotNil(t, h.sessionRevocationCancel, "replacement must be registered before prior cleanup")
	h.lifecycleMu.Unlock()
	releaseFirstClose()
	require.NoError(t, <-replacement)
	require.Eventually(t, func() bool {
		return mr.PubSubNumSub(sessionRevocationsChannel)[sessionRevocationsChannel] == 1
	}, time.Second, 10*time.Millisecond)
	h.lifecycleMu.Lock()
	assert.NotNil(t, h.sessionRevocationCancel, "prior generation cleanup must not clear the replacement owner")
	h.lifecycleMu.Unlock()
}

func TestSessionRevocationListenerCloseErrorsAreContained(t *testing.T) {
	oldClose := closeSessionRevocationPubSubFunc
	t.Cleanup(func() { closeSessionRevocationPubSubFunc = oldClose })
	closeSessionRevocationPubSubFunc = func(pubsub *goredis.PubSub) error {
		_ = pubsub.Close() //nolint:errcheck // the injected error is the asserted path.
		return errors.New("synthetic pubsub close failure")
	}

	t.Run("failed subscription", func(t *testing.T) {
		redisClient := goredis.NewClient(&goredis.Options{
			Addr:        "127.0.0.1:1",
			DialTimeout: 10 * time.Millisecond,
			MaxRetries:  0,
		})
		t.Cleanup(func() { require.NoError(t, redisClient.Close()) })
		h := NewHub(nil, newTestLogger(), nil, nil, nil, redisClient)
		t.Cleanup(h.Stop)
		assert.Error(t, h.StartSessionRevocationListener(context.Background()))
	})

	t.Run("listener shutdown", func(t *testing.T) {
		mr := miniredis.RunT(t)
		redisClient := goredis.NewClient(&goredis.Options{Addr: mr.Addr()})
		t.Cleanup(func() { require.NoError(t, redisClient.Close()) })
		h := NewHub(nil, newTestLogger(), nil, nil, nil, redisClient)
		require.NoError(t, h.StartSessionRevocationListener(context.Background()))
		h.Stop()
	})
}

func TestConsumeSessionRevocationMessagesRejectsMalformedAndStopsOnClose(t *testing.T) {
	h := setupTestHub()
	messages := make(chan *goredis.Message, 2)
	messages <- nil
	messages <- &goredis.Message{Payload: "not-a-jti"}
	close(messages)
	assert.NotPanics(t, func() {
		h.consumeSessionRevocationMessages(context.Background(), messages)
	})

	cancelled, cancel := context.WithCancel(context.Background())
	cancel()
	assert.NotPanics(t, func() {
		h.consumeSessionRevocationMessages(cancelled, make(chan *goredis.Message))
	})
}

func TestConcurrentRevocationAndActionSerializeTransportClose(t *testing.T) {
	h := setupTestHub()
	h.Unregister = make(chan *Client, 1)
	checkStarted := make(chan struct{})
	allowCheck := make(chan struct{})
	h.sessionRevocationCheck = func(context.Context, string) error {
		close(checkStarted)
		<-allowCheck
		return nil
	}
	jti := uuid.NewString()
	client, session := newRevocationTestClient(
		h,
		"racing-client",
		"user-1",
		jti,
		"websocket",
		[]byte(`{"type":"leave","room":"room-1"}`),
	)
	h.mu.Lock()
	h.Clients[client.ID] = client
	h.mu.Unlock()

	actionDone := make(chan bool, 1)
	go func() { actionDone <- client.processNextMessage(context.Background()) }()
	<-checkStarted
	revocationDone := make(chan struct{})
	go func() {
		h.DisconnectSession(jti, websocket.ClosePolicyViolation, "Session revoked")
		close(revocationDone)
	}()
	close(allowCheck)
	<-actionDone
	<-revocationDone

	require.Eventually(t, session.wasClosed, time.Second, 10*time.Millisecond)
	assert.Equal(t, 1, session.closeCount(), "concurrent paths must close the transport once")
	assert.True(t, client.sessionRevoked.Load())
}
