package hub

import (
	"context"
	"io"
	"log/slog"
	"net"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/gorilla/websocket"
	"github.com/prometheus/client_golang/prometheus/testutil"
	"github.com/quic-go/webtransport-go"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"github.com/university-ecosystem/ws-hub/pkg/config"
)

type blockingLifecycleLogHandler struct {
	started chan struct{}
	release <-chan struct{}
	once    sync.Once
}

func (h *blockingLifecycleLogHandler) Enabled(context.Context, slog.Level) bool { return true }

func (h *blockingLifecycleLogHandler) Handle(context.Context, slog.Record) error {
	h.once.Do(func() { close(h.started) })
	<-h.release
	return nil
}

func (h *blockingLifecycleLogHandler) WithAttrs([]slog.Attr) slog.Handler { return h }

func (h *blockingLifecycleLogHandler) WithGroup(string) slog.Handler { return h }

type gatedDoneContext struct {
	context.Context
	entered chan struct{}
	release <-chan struct{}
	once    sync.Once
}

func (c *gatedDoneContext) Done() <-chan struct{} {
	c.once.Do(func() { close(c.entered) })
	<-c.release
	return c.Context.Done()
}

type blockingShutdownSession struct {
	readStarted chan struct{}
	closed      chan struct{}
	startOnce   sync.Once
	closeOnce   sync.Once
}

func newBlockingShutdownSession() *blockingShutdownSession {
	return &blockingShutdownSession{
		readStarted: make(chan struct{}),
		closed:      make(chan struct{}),
	}
}

func (s *blockingShutdownSession) ReadMessage() (int, []byte, error) {
	s.startOnce.Do(func() { close(s.readStarted) })
	<-s.closed
	return 0, nil, io.EOF
}

func (s *blockingShutdownSession) WriteMessage(int, []byte) error { return nil }

func (s *blockingShutdownSession) Close() error {
	s.closeOnce.Do(func() { close(s.closed) })
	return nil
}

func (s *blockingShutdownSession) RemoteAddr() net.Addr { return &net.TCPAddr{} }

func (s *blockingShutdownSession) TransportType() string { return "test" }

func (s *blockingShutdownSession) SetReadLimit(int64) {}

func (s *blockingShutdownSession) SetReadDeadline(time.Time) error { return nil }

func (s *blockingShutdownSession) SetWriteDeadline(time.Time) error { return nil }

func (s *blockingShutdownSession) SetPongHandler(func(string) error) {}

func TestHubStop_ClosesActiveClientAndStopsItsPumps(t *testing.T) {
	h := setupTestHub()
	t.Cleanup(h.Stop)

	runDone := make(chan struct{})
	go func() {
		h.Run(context.Background())
		close(runDone)
	}()
	require.Eventually(t, func() bool { return hubLifecycleContext(h) != nil }, time.Second, time.Millisecond)

	clientCtx, clientCancel := context.WithCancel(context.Background())
	session := newBlockingShutdownSession()
	client := &Client{
		ID:     "shutdown-client",
		UserID: "shutdown-user",
		Conn:   session,
		Rooms:  make(map[string]bool),
		Send:   make(chan []byte, 1),
		Hub:    h,
		ctx:    clientCtx,
		cancel: clientCancel,
	}
	require.True(t, h.registerClient(client), "hub should admit the test client before shutdown")
	require.Eventually(t, func() bool {
		h.mu.RLock()
		defer h.mu.RUnlock()
		return h.Clients[client.ID] == client
	}, time.Second, time.Millisecond)

	readDone := make(chan struct{})
	writeDone := make(chan struct{})
	StartTrackedGoroutine(func() {
		defer h.clientPumpWG.Done()
		defer close(readDone)
		client.ReadPump(clientCtx)
	})
	StartTrackedGoroutine(func() {
		defer h.clientPumpWG.Done()
		defer close(writeDone)
		client.WritePump()
	})
	select {
	case <-session.readStarted:
	case <-time.After(time.Second):
		t.Fatal("read pump did not start reading the session")
	}

	stopDone := make(chan struct{})
	go func() {
		h.Stop()
		close(stopDone)
	}()
	select {
	case <-stopDone:
	case <-time.After(time.Second):
		clientCancel()
		_ = session.Close()
		safeClose(client.Send)
		<-stopDone
		t.Fatal("Hub.Stop did not finish after closing its active clients")
	}
	select {
	case <-runDone:
	case <-time.After(time.Second):
		t.Fatal("hub run loop did not stop")
	}
	for name, done := range map[string]<-chan struct{}{
		"read pump":  readDone,
		"write pump": writeDone,
	} {
		select {
		case <-done:
		case <-time.After(time.Second):
			// Keep the regression failure from leaking the test pumps.
			clientCancel()
			_ = session.Close()
			safeClose(client.Send)
			t.Fatalf("%s remained blocked after Hub.Stop", name)
		}
	}

	assert.ErrorIs(t, clientCtx.Err(), context.Canceled)
	select {
	case <-session.closed:
	default:
		t.Fatal("Hub.Stop left the active session open")
	}
	h.mu.RLock()
	_, stillRegistered := h.Clients[client.ID]
	h.mu.RUnlock()
	assert.False(t, stillRegistered, "Hub.Stop must remove the stopped client")
}

func TestClientDisconnectAfterRunExitSynchronouslyCleansMembership(t *testing.T) {
	baseline := testutil.ToFloat64(ActiveConnections)
	h := setupTestHub()
	t.Cleanup(h.Stop)

	runCtx, cancelRun := context.WithCancel(context.Background())
	runDone := make(chan struct{})
	go func() {
		h.Run(runCtx)
		close(runDone)
	}()
	require.Eventually(t, func() bool { return hubLifecycleContext(h) != nil }, time.Second, time.Millisecond)

	client := &Client{
		ID:     "disconnect-after-run-exit",
		UserID: "disconnect-after-run-exit-user",
		Conn:   &recordingSession{},
		Hub:    h,
		Rooms:  make(map[string]bool),
		Send:   make(chan []byte, 1),
		ctx:    context.Background(),
	}
	h.handleRegister(context.Background(), client)
	client.JoinRoom("disconnect-after-run-exit-room")

	cancelRun()
	select {
	case <-runDone:
	case <-time.After(time.Second):
		t.Fatal("hub run loop did not exit after its lifecycle context was cancelled")
	}
	require.Nil(t, hubLifecycleContext(h), "Run must clear its lifecycle context before later client cleanup")

	client.Disconnect(1000, "peer closed")

	h.mu.RLock()
	_, registered := h.Clients[client.ID]
	roomCount := len(h.Rooms)
	h.mu.RUnlock()
	assert.False(t, registered, "disconnect after Run exit must not wait for a receiver that no longer exists")
	assert.Zero(t, roomCount, "disconnect after Run exit must clear the room index")
	client.mu.Lock()
	assert.Empty(t, client.Rooms, "disconnect after Run exit must clear client membership")
	client.mu.Unlock()
	assert.Equal(t, baseline, testutil.ToFloat64(ActiveConnections), "disconnect after Run exit must decrement the active gauge exactly once")
	_, open := <-client.Send
	assert.False(t, open, "disconnect after Run exit must close the send queue")
}

func TestHubHandleRegister_RejectsClientAfterStopBegins(t *testing.T) {
	baseline := testutil.ToFloat64(ActiveConnections)
	h := setupTestHub()
	h.Stop()
	t.Cleanup(h.Stop)
	t.Cleanup(func() { ActiveConnections.Set(baseline) })

	session := newBlockingShutdownSession()
	client := &Client{
		ID:    "late-register-client",
		Hub:   h,
		Conn:  session,
		Rooms: make(map[string]bool),
		Send:  make(chan []byte, 1),
	}
	h.handleRegister(context.Background(), client)

	h.mu.RLock()
	_, registered := h.Clients[client.ID]
	h.mu.RUnlock()
	assert.False(t, registered, "a late register event must not become active after Stop wins")
	assert.Equal(t, baseline, testutil.ToFloat64(ActiveConnections), "rejected late registration must not change the active-connection gauge")
	select {
	case <-client.Send:
		// The rejected client's write pump, if already reserved, must be able to exit.
	default:
		t.Fatal("late registration must close the send queue")
	}
	select {
	case <-session.closed:
	default:
		t.Fatal("late registration must close its upgraded transport")
	}
}

func TestHubHandleRegister_RejectsClientAfterRunContextCancellation(t *testing.T) {
	baseline := testutil.ToFloat64(ActiveConnections)
	h := setupTestHub()
	_, runCancel, started := h.beginRun(context.Background())
	require.True(t, started)
	runCancel()
	t.Cleanup(func() {
		h.endRun(runCancel)
		h.Stop()
		ActiveConnections.Set(baseline)
	})

	session := newBlockingShutdownSession()
	client := &Client{
		ID:    "cancelled-run-register-client",
		Hub:   h,
		Conn:  session,
		Rooms: make(map[string]bool),
		Send:  make(chan []byte, 1),
	}
	h.handleRegister(context.Background(), client)

	h.mu.RLock()
	_, registered := h.Clients[client.ID]
	h.mu.RUnlock()
	assert.False(t, registered, "a pending register must be rejected once the Run lifecycle context is cancelled")
	assert.Equal(t, baseline, testutil.ToFloat64(ActiveConnections), "cancelled-run registration must not change the active-connection gauge")
	select {
	case <-client.Send:
	default:
		t.Fatal("cancelled-run registration must close the send queue")
	}
	select {
	case <-session.closed:
	default:
		t.Fatal("cancelled-run registration must close its upgraded transport")
	}
}

func TestHubStop_WaitsForClientEvictionStartedBeforeShutdown(t *testing.T) {
	baseline := testutil.ToFloat64(ActiveConnections)
	h := setupTestHub()
	releaseDone := make(chan struct{})
	var releaseOnce sync.Once
	releaseGate := func() { releaseOnce.Do(func() { close(releaseDone) }) }
	t.Cleanup(func() { ActiveConnections.Set(baseline) })
	t.Cleanup(h.Stop)
	t.Cleanup(releaseGate)

	baseCtx, cancelBase := context.WithCancel(context.Background())
	cancelObserved := make(chan struct{})
	var cancelOnce sync.Once
	h.lifecycleMu.Lock()
	h.ctx = &gatedDoneContext{
		Context: baseCtx,
		entered: make(chan struct{}),
		release: releaseDone,
	}
	h.ctxCancel = func() {
		cancelBase()
		cancelOnce.Do(func() { close(cancelObserved) })
	}
	gateEntered := h.ctx.(*gatedDoneContext).entered
	h.lifecycleMu.Unlock()

	client := &Client{
		ID:    "eviction-shutdown-client",
		Hub:   h,
		Rooms: make(map[string]bool),
		Send:  make(chan []byte, 1),
		ctx:   context.Background(),
	}
	h.handleRegister(context.Background(), client)
	h.scheduleClientEviction(client)
	select {
	case <-gateEntered:
	case <-time.After(time.Second):
		t.Fatal("eviction worker did not reach the controlled lifecycle-context gate")
	}

	stopDone := make(chan struct{})
	go func() {
		h.Stop()
		close(stopDone)
	}()
	select {
	case <-cancelObserved:
	case <-time.After(time.Second):
		t.Fatal("Hub.Stop did not cancel the lifecycle context")
	}
	select {
	case <-stopDone:
		t.Fatal("Hub.Stop returned while a tracked client-eviction worker was still blocked")
	case <-time.After(25 * time.Millisecond):
	}

	releaseGate()
	select {
	case <-stopDone:
	case <-time.After(time.Second):
		t.Fatal("Hub.Stop did not finish after the client-eviction worker was released")
	}
}

func TestHandleWebSocket_RejectsUpgradeWhenStopRacesTicketValidation(t *testing.T) {
	h := setupTestHub()
	t.Cleanup(h.Stop)

	validationStarted := make(chan struct{})
	continueValidation := make(chan struct{})
	oldValidate := validateUpgradeTicketIdentityFunc
	validateUpgradeTicketIdentityFunc = func(*Hub, context.Context, string) (upgradeTicketIdentity, error) {
		close(validationStarted)
		<-continueValidation
		return upgradeTicketIdentity{UserID: "user", SessionJTI: "session", SessionExpiresAt: time.Unix(9999999999, 0)}, nil
	}
	t.Cleanup(func() { validateUpgradeTicketIdentityFunc = oldValidate })

	handlerDone := make(chan struct{})
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		defer close(handlerDone)
		h.HandleWebSocket(w, r, &config.Config{SendBufferSize: 1})
	}))
	t.Cleanup(server.Close)

	result := make(chan struct {
		conn       *websocket.Conn
		statusCode int
		hasResp    bool
		err        error
	}, 1)
	wsURL := "ws" + strings.TrimPrefix(server.URL, "http") + "/ws?ticket=test-ticket"
	go func() {
		conn, resp, err := websocket.DefaultDialer.Dial(wsURL, nil)
		resultValue := struct {
			conn       *websocket.Conn
			statusCode int
			hasResp    bool
			err        error
		}{conn: conn, err: err}
		if resp != nil {
			resultValue.hasResp = true
			resultValue.statusCode = resp.StatusCode
			if resp.Body != nil {
				defer resp.Body.Close() //nolint:errcheck // test response cleanup
			}
		}
		result <- resultValue
	}()
	select {
	case <-validationStarted:
	case <-time.After(time.Second):
		t.Fatal("upgrade handler did not begin ticket validation")
	}

	h.Stop()
	close(continueValidation)

	var dialResult struct {
		conn       *websocket.Conn
		statusCode int
		hasResp    bool
		err        error
	}
	select {
	case dialResult = <-result:
	case <-time.After(time.Second):
		t.Fatal("upgrade request did not finish after Stop")
	}
	if dialResult.conn != nil {
		defer func() { _ = dialResult.conn.Close() }()
	}
	select {
	case <-handlerDone:
	case <-time.After(time.Second):
		t.Fatal("upgrade handler remained blocked while registering after Stop")
	}
	require.Error(t, dialResult.err, "stopped hubs must reject before websocket upgrade")
	require.True(t, dialResult.hasResp)
	assert.Equal(t, http.StatusServiceUnavailable, dialResult.statusCode)
}

func TestHandleWebSocket_ClosesUpgradeWhenStopWinsBeforeRegistration(t *testing.T) {
	connectionBaseline := testutil.ToFloat64(ActiveConnections)
	goroutineBaseline := testutil.ToFloat64(ActiveGoroutines)
	h := setupTestHub()
	runCtx, runCancel, started := h.beginRun(context.Background())
	require.True(t, started)
	runDone := make(chan struct{})
	go func() {
		defer close(runDone)
		<-runCtx.Done()
		h.endRun(runCancel)
	}()

	oldValidate := validateUpgradeTicketIdentityFunc
	validateUpgradeTicketIdentityFunc = func(*Hub, context.Context, string) (upgradeTicketIdentity, error) {
		return upgradeTicketIdentity{UserID: "user", SessionJTI: "session", SessionExpiresAt: time.Unix(9999999999, 0)}, nil
	}
	t.Cleanup(func() { validateUpgradeTicketIdentityFunc = oldValidate })

	handlerDone := make(chan struct{})
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		defer close(handlerDone)
		h.HandleWebSocket(w, r, &config.Config{SendBufferSize: 1})
	}))
	t.Cleanup(server.Close)
	t.Cleanup(func() {
		h.Stop()
		select {
		case <-runDone:
		case <-time.After(time.Second):
			t.Error("Run lifecycle helper did not exit during test cleanup")
		}
	})

	wsURL := "ws" + strings.TrimPrefix(server.URL, "http") + "/ws?ticket=test-ticket"
	clientConn, response, err := websocket.DefaultDialer.Dial(wsURL, nil)
	if response != nil && response.Body != nil {
		defer response.Body.Close() //nolint:errcheck // test response cleanup
	}
	require.NoError(t, err, "the request must complete the upgrade before shutdown wins")
	defer func() { _ = clientConn.Close() }()

	stopDone := make(chan struct{})
	go func() {
		h.Stop()
		close(stopDone)
	}()
	select {
	case <-handlerDone:
	case <-time.After(time.Second):
		t.Fatal("upgraded handler remained blocked after Stop cancelled registration")
	}
	select {
	case <-stopDone:
	case <-time.After(time.Second):
		t.Fatal("Stop did not finish after the unregistered upgrade was closed")
	}

	_, _, err = clientConn.ReadMessage()
	require.Error(t, err, "the upgraded socket must be closed when registration loses the shutdown race")
	assert.True(t, websocket.IsCloseError(err, websocket.CloseTryAgainLater), "rejected post-upgrade registration should use the retryable close code")

	h.mu.RLock()
	clientCount := len(h.Clients)
	h.mu.RUnlock()
	assert.Zero(t, clientCount, "a client rejected after upgrade must never enter the hub")
	assert.Equal(t, connectionBaseline, testutil.ToFloat64(ActiveConnections), "rejected upgrade must not leak the active-connection gauge")
	assert.Equal(t, goroutineBaseline, testutil.ToFloat64(ActiveGoroutines), "rejected upgrade must not start client pumps")
}

func TestEnqueueRoomBroadcast_DropsFramesAfterClientDisconnect(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	send := make(chan []byte, 1)
	client := &Client{ctx: ctx, Send: send}

	result := client.enqueueRoomBroadcast(&Message{Room: "private-room"}, []byte(`{"type":"message","room":"private-room"}`))

	assert.Equal(t, roomEnqueueReplayFatal, result, "a disconnected client must not accept a late room frame")
	assert.Empty(t, send, "the stale room frame must not be queued for a disconnected client")
}

func TestHandleWebTransport_RejectsRequestAfterStopBeforeUpgrade(t *testing.T) {
	h := setupTestHub()
	h.Stop()

	oldValidate := validateUpgradeTicketIdentityFunc
	oldUpgrade := upgradeWTFunc
	t.Cleanup(func() {
		validateUpgradeTicketIdentityFunc = oldValidate
		upgradeWTFunc = oldUpgrade
	})
	validateUpgradeTicketIdentityFunc = func(*Hub, context.Context, string) (upgradeTicketIdentity, error) {
		return upgradeTicketIdentity{UserID: "user", SessionJTI: "session", SessionExpiresAt: time.Unix(9999999999, 0)}, nil
	}
	upgradeCalled := false
	upgradeWTFunc = func(*webtransport.Server, http.ResponseWriter, *http.Request) (*webtransport.Session, error) {
		upgradeCalled = true
		return nil, nil
	}

	recorder := httptest.NewRecorder()
	h.HandleWebTransport(recorder, httptest.NewRequest(http.MethodGet, "/wt?ticket=test-ticket", nil), &config.Config{})

	assert.Equal(t, http.StatusServiceUnavailable, recorder.Code)
	assert.False(t, upgradeCalled, "a stopped hub must reject before opening a WebTransport session")
}

func TestHandleWebTransport_ClosesUpgradeWhenStopWinsBeforeRegistration(t *testing.T) {
	connectionBaseline := testutil.ToFloat64(ActiveConnections)
	goroutineBaseline := testutil.ToFloat64(ActiveGoroutines)
	h := setupTestHub()

	oldValidate := validateUpgradeTicketIdentityFunc
	oldUpgrade := upgradeWTFunc
	oldSession := newWebTransportSessionFunc
	t.Cleanup(func() {
		validateUpgradeTicketIdentityFunc = oldValidate
		upgradeWTFunc = oldUpgrade
		newWebTransportSessionFunc = oldSession
	})
	validateUpgradeTicketIdentityFunc = func(*Hub, context.Context, string) (upgradeTicketIdentity, error) {
		return upgradeTicketIdentity{UserID: "user", SessionJTI: "session", SessionExpiresAt: time.Unix(9999999999, 0)}, nil
	}
	upgradeStarted := make(chan struct{})
	continueUpgrade := make(chan struct{})
	upgradeWTFunc = func(*webtransport.Server, http.ResponseWriter, *http.Request) (*webtransport.Session, error) {
		close(upgradeStarted)
		<-continueUpgrade
		return nil, nil
	}
	session := newBlockingShutdownSession()
	newWebTransportSessionFunc = func(*webtransport.Session) Session { return session }

	handlerDone := make(chan struct{})
	recorder := httptest.NewRecorder()
	go func() {
		defer close(handlerDone)
		h.HandleWebTransport(recorder, httptest.NewRequest(http.MethodGet, "/wt?ticket=test-ticket", nil), &config.Config{SendBufferSize: 1})
	}()
	select {
	case <-upgradeStarted:
	case <-time.After(time.Second):
		t.Fatal("WebTransport handler did not reach the controlled upgrade")
	}

	h.Stop()
	close(continueUpgrade)
	select {
	case <-handlerDone:
	case <-time.After(time.Second):
		t.Fatal("WebTransport handler remained blocked after shutdown won registration")
	}
	select {
	case <-session.closed:
	case <-time.After(time.Second):
		t.Fatal("session created by a rejected post-upgrade registration was not closed")
	}

	h.mu.RLock()
	clientCount := len(h.Clients)
	h.mu.RUnlock()
	assert.Zero(t, clientCount, "a session rejected after upgrade must never enter the hub")
	assert.Equal(t, connectionBaseline, testutil.ToFloat64(ActiveConnections), "rejected WebTransport session must not leak the active-connection gauge")
	assert.Equal(t, goroutineBaseline, testutil.ToFloat64(ActiveGoroutines), "rejected WebTransport session must not start client pumps")
}

func TestRegisterClientRejectsMissingOrCancelledRunContext(t *testing.T) {
	t.Run("run not started", func(t *testing.T) {
		h := setupTestHub()
		require.False(t, h.registerClient(&Client{ID: "before-run", Send: make(chan []byte, 1)}))
		waitDone := make(chan struct{})
		go func() {
			h.clientPumpWG.Wait()
			close(waitDone)
		}()
		select {
		case <-waitDone:
		case <-time.After(time.Second):
			t.Fatal("rejected pre-Run registration leaked reserved client-pump wait-group entries")
		}
		h.Stop()
	})

	t.Run("run context cancelled", func(t *testing.T) {
		h := setupTestHub()
		_, runCancel, started := h.beginRun(context.Background())
		require.True(t, started)
		t.Cleanup(func() {
			h.endRun(runCancel)
			h.Stop()
		})
		runCancel()

		require.False(t, h.registerClient(&Client{ID: "cancelled-run", Send: make(chan []byte, 1)}))
		waitDone := make(chan struct{})
		go func() {
			h.clientPumpWG.Wait()
			close(waitDone)
		}()
		select {
		case <-waitDone:
		case <-time.After(time.Second):
			t.Fatal("cancelled Run registration leaked reserved client-pump wait-group entries")
		}
	})
}

func TestHubRunRejectsDuplicateAndPostStopStarts(t *testing.T) {
	h := setupTestHub()
	_, runCancel, started := h.beginRun(context.Background())
	require.True(t, started)
	_, duplicateCancel, duplicateStarted := h.beginRun(context.Background())
	assert.False(t, duplicateStarted, "a second Run lifecycle must not be admitted")
	assert.Nil(t, duplicateCancel)

	runDone := make(chan struct{})
	go func() {
		h.Run(context.Background())
		close(runDone)
	}()
	select {
	case <-runDone:
	case <-time.After(time.Second):
		t.Fatal("a duplicate Run call did not return promptly")
	}
	h.endRun(runCancel)
	h.Stop()

	_, stoppedCancel, restarted := h.beginRun(context.Background())
	assert.False(t, restarted, "a stopped hub must not restart its Run lifecycle")
	assert.Nil(t, stoppedCancel)
	postStopRunDone := make(chan struct{})
	go func() {
		h.Run(context.Background())
		close(postStopRunDone)
	}()
	select {
	case <-postStopRunDone:
	case <-time.After(time.Second):
		t.Fatal("Run on a stopped hub did not return promptly")
	}
}

func TestScheduleClientEvictionAfterStopUsesSynchronousCleanup(t *testing.T) {
	baseline := testutil.ToFloat64(ActiveConnections)
	h := setupTestHub()
	session := newBlockingShutdownSession()
	ctx, cancel := context.WithCancel(context.Background())
	client := &Client{
		ID:     "post-stop-eviction",
		UserID: "post-stop-user",
		Hub:    h,
		Conn:   session,
		Rooms:  make(map[string]bool),
		Send:   make(chan []byte, 1),
		ctx:    ctx,
		cancel: cancel,
	}
	h.handleRegister(context.Background(), client)
	h.Stop()
	baselineGoroutines := testutil.ToFloat64(ActiveGoroutines)

	done := make(chan struct{})
	go func() {
		h.scheduleClientEviction(client)
		close(done)
	}()
	select {
	case <-done:
	case <-time.After(time.Second):
		t.Fatal("post-stop eviction did not clean up synchronously")
	}

	h.mu.RLock()
	_, registered := h.Clients[client.ID]
	h.mu.RUnlock()
	assert.False(t, registered)
	assert.Equal(t, baseline, testutil.ToFloat64(ActiveConnections))
	assert.Equal(t, baselineGoroutines, testutil.ToFloat64(ActiveGoroutines), "post-stop eviction must not launch an untracked cleanup worker")
}

func TestRoomMembershipLock_StaleLeaseDoesNotTouchReplacementEntry(t *testing.T) {
	registry := &roomMembershipLockRegistry{}
	key := roomMembershipKey{userID: "user", roomID: "room"}
	lease := registry.acquire(key)
	lease.Lock()
	replacement := &roomMembershipLockEntry{references: 2}
	registry.mu.Lock()
	registry.entries[key] = replacement
	registry.mu.Unlock()

	lease.Unlock()

	registry.mu.Lock()
	defer registry.mu.Unlock()
	assert.Same(t, replacement, registry.entries[key], "releasing a stale membership-lock lease must not erase a replacement entry")
	assert.Equal(t, 2, replacement.references, "a stale lease must not decrement another entry's reference count")
}

func TestHubStopWaitsForLimiterCleanupWorker(t *testing.T) {
	h := setupTestHub()
	baseline := testutil.ToFloat64(ActiveGoroutines)
	started := make(chan struct{})
	release := make(chan struct{})
	var releaseOnce sync.Once
	releaseWorker := func() { releaseOnce.Do(func() { close(release) }) }
	defer releaseWorker()
	h.Logger = slog.New(&blockingLifecycleLogHandler{started: started, release: release})
	h.limiterCleanupInterval = time.Millisecond
	h.msgLimiters.Store("orphaned-limiter", struct{}{})
	h.StartLimiterCleanup(context.Background())
	select {
	case <-started:
	case <-time.After(time.Second):
		t.Fatal("limiter cleanup worker did not reach the controlled blocking log call")
	}

	stopStarted := make(chan struct{})
	stopDone := make(chan struct{})
	go func() {
		close(stopStarted)
		h.Stop()
		close(stopDone)
	}()
	<-stopStarted
	select {
	case <-stopDone:
		t.Fatal("Hub.Stop returned while its limiter cleanup worker was still running")
	case <-time.After(25 * time.Millisecond):
	}

	releaseWorker()
	select {
	case <-stopDone:
	case <-time.After(time.Second):
		t.Fatal("Hub.Stop did not finish after limiter cleanup was released")
	}
	expected := baseline - 1 // setupTestHub owns one tracked upgrade-limiter GC worker.
	var current float64
	require.Eventually(t, func() bool {
		current = testutil.ToFloat64(ActiveGoroutines)
		return current == expected
	}, time.Second, time.Millisecond, "Hub.Stop must join its limiter cleanup and upgrade-limiter goroutines (expected=%v current=%v)", expected, current)
}

func TestHubStartLimiterCleanupAfterStopDoesNotStartWorker(t *testing.T) {
	h := setupTestHub()
	h.Stop()
	baseline := testutil.ToFloat64(ActiveGoroutines)

	h.StartLimiterCleanup(context.Background())
	assert.Equal(t, baseline, testutil.ToFloat64(ActiveGoroutines), "stopped hubs must reject new background workers")

	h.lifecycleMu.Lock()
	cancel := h.limiterCancel
	h.lifecycleMu.Unlock()
	if cancel != nil {
		cancel()
	}
	require.Eventually(t, func() bool {
		return testutil.ToFloat64(ActiveGoroutines) == baseline
	}, time.Second, time.Millisecond, "test cleanup must leave no limiter goroutine behind")
}
