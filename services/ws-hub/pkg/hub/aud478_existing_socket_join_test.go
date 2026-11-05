package hub

import (
	"context"
	"errors"
	"net"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"github.com/gorilla/websocket"
	"github.com/nats-io/nats.go"
	"github.com/stretchr/testify/require"
	"github.com/university-ecosystem/ws-hub/pkg/config"
)

func aud478DisconnectableNATS(t *testing.T) *nats.Conn {
	t.Helper()
	server := newMockNatsServer(t)
	conn, err := nats.Connect(server.Addr())
	require.NoError(t, err)
	t.Cleanup(func() {
		conn.Close()
		server.mu.Lock()
		defer server.mu.Unlock()
		for _, peer := range server.conns {
			if closeErr := peer.Close(); closeErr != nil && !errors.Is(closeErr, net.ErrClosed) {
				t.Errorf("close mock NATS peer: %v", closeErr)
			}
		}
		server.conns = nil
	})
	return conn
}

// aud478Socket runs the production reader against an already-established WebSocket.
// The queued heartbeat is a completion marker for all preceding client commands.
func aud478Socket(t *testing.T, h *Hub, id string) (*Client, *websocket.Conn) {
	t.Helper()
	return aud478SocketWithSetup(t, h, id, nil)
}

func aud478SocketWithSetup(t *testing.T, h *Hub, id string, setup func(*Client)) (*Client, *websocket.Conn) {
	t.Helper()
	server, socket := newConnPair(t)
	client := newClientOn(h, server, id, rdUser)
	if setup != nil {
		setup(client)
	}
	h.handleRegister(context.Background(), client)
	done := make(chan struct{})
	go func() {
		defer close(done)
		client.ReadPump(client.ctx)
	}()
	t.Cleanup(func() {
		_ = socket.Close()
		select {
		case <-done:
		case <-time.After(3 * time.Second):
			t.Error("WebSocket reader did not stop")
		}
		h.handleUnregister(context.Background(), client)
	})
	return client, socket
}

func aud478SendJoin(t *testing.T, socket *websocket.Conn, room string) {
	t.Helper()
	sendAUD337Text(t, socket, `{"type":"join","room":"`+room+`"}`)
	sendAUD337Text(t, socket, `{"type":"heartbeat_ping","nonce":"`+aud337ValidNonce()+`"}`)
}

func aud478WaitForJoin(t *testing.T, client *Client) {
	t.Helper()
	select {
	case frame := <-client.Send:
		require.JSONEq(t, `{"type":"heartbeat_pong","nonce":"`+aud337ValidNonce()+`"}`, string(frame))
	case <-time.After(3 * time.Second):
		t.Fatal("WebSocket join did not finish")
	}
}

func aud478WaitForRetryClose(t *testing.T, socket *websocket.Conn) {
	t.Helper()
	require.NoError(t, socket.SetReadDeadline(time.Now().Add(2*time.Second)))
	_, _, err := socket.ReadMessage()
	var closeErr *websocket.CloseError
	require.ErrorAs(t, err, &closeErr, "temporary room admission failure must close the socket")
	require.NotNil(t, closeErr)
	require.Equal(t, websocket.CloseTryAgainLater, closeErr.Code)
}

func TestAUD478TemporaryJoinFailureClosesForRetryAndRejoins(t *testing.T) {
	server, calls := aud478BackendAnswer(t, http.StatusOK)
	auth := mustNewTestAuthClient(t, server.URL, "", nil)
	h := setupTestHub()
	h.authClient = auth
	h.authCacheTracked.Store(true)
	var connected atomic.Bool
	connected.Store(true)
	h.revocationConnected = func(*nats.Conn) bool { return connected.Load() }
	t.Cleanup(h.Stop)
	first, socket := aud478Socket(t, h, "aud478-retry-close")

	connected.Store(false)
	sendAUD337Text(t, socket, `{"type":"join","room":"`+rdRoom+`"}`)
	aud478WaitForRetryClose(t, socket)
	require.False(t, first.isInRoom(rdRoom))
	require.Zero(t, calls.Load())

	connected.Store(true)
	require.NoError(t, h.completeAuthCacheReset(context.Background()))
	replacement, retrySocket := aud478Socket(t, h, "aud478-retry-reconnected")
	aud478SendJoin(t, retrySocket, rdRoom)
	aud478WaitForJoin(t, replacement)
	require.True(t, replacement.isInRoom(rdRoom), "the replacement socket must rejoin after recovery")
	require.EqualValues(t, 1, calls.Load())
}

func TestAUD478DisconnectBeforeMembershipPublicationRejectsJoin(t *testing.T) {
	server, _ := aud478BackendAnswer(t, http.StatusOK)
	cache := mustNewTestAuthClient(t, server.URL, "", nil)
	require.True(t, cache.CanJoinRoom(context.Background(), rdUser, rdRoom))
	auth := &aud478HeldCacheAnswer{
		InternalAPIAuthClient: cache,
		started:               make(chan struct{}),
		release:               make(chan struct{}),
	}
	nc := aud478DisconnectableNATS(t)
	h := setupTestHub()
	h.Nats = nc
	h.authClient = auth
	h.authCacheTracked.Store(true)
	t.Cleanup(h.Stop)
	client, socket := aud478Socket(t, h, "aud478-blocked-commit")
	var releaseAuth sync.Once
	t.Cleanup(func() { releaseAuth.Do(func() { close(auth.release) }) })
	sendAUD337Text(t, socket, `{"type":"join","room":"`+rdRoom+`"}`)
	waitRoomMembershipSignal(t, auth.started, "cached authorization did not finish")

	// The generation read lock identifies the final authorization section.
	// Holding Hub.mu forces the join to pause before publishing membership.
	h.mu.Lock()
	var unlockHub sync.Once
	defer unlockHub.Do(h.mu.Unlock)
	releaseAuth.Do(func() { close(auth.release) })
	require.Eventually(t, func() bool {
		if cache.genMu.TryLock() {
			cache.genMu.Unlock()
			return false
		}
		return true
	}, 2*time.Second, time.Millisecond, "join did not reach the final authorization section")
	nc.Close()
	unlockHub.Do(h.mu.Unlock)
	aud478WaitForRetryClose(t, socket)
	require.False(t, client.isInRoom(rdRoom), "a disconnected hub must not publish membership after the fence")
}

func TestAUD478NewWebSocketRejectsImmediatelyOnNATSDisconnect(t *testing.T) {
	mr, redisClient := newMiniredisClient(t)
	require.NoError(t, mr.Set(wsTicketKeyPrefix+validTicket, rdUser+":"+validSessionJTI+":9999999999"))
	nc := aud478DisconnectableNATS(t)
	h := setupTestHub()
	h.Nats = nc
	h.redisClient = redisClient
	h.revocationRedisClient = redisClient
	h.authCacheTracked.Store(true)
	t.Cleanup(h.Stop)

	ctx, cancel := context.WithCancel(context.Background())
	done := make(chan struct{})
	go func() {
		defer close(done)
		h.Run(ctx)
	}()
	t.Cleanup(func() {
		cancel()
		select {
		case <-done:
		case <-time.After(3 * time.Second):
			t.Error("hub run loop did not stop")
		}
	})
	require.Eventually(t, func() bool { return hubLifecycleContext(h) != nil }, 2*time.Second, time.Millisecond)
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		h.HandleWebSocket(w, r, &config.Config{SendBufferSize: 8})
	}))
	t.Cleanup(server.Close)

	// This is the interval before either watchdog updates its admission flag.
	nc.Close()
	require.False(t, nc.IsConnected())
	socket, response, err := websocket.DefaultDialer.Dial("ws"+strings.TrimPrefix(server.URL, "http")+"?ticket="+validTicket, nil)
	if socket != nil {
		_ = socket.Close()
	}
	if response != nil && response.Body != nil {
		defer response.Body.Close()
	}
	require.Error(t, err, "an upgrade during the NATS outage must be refused")
	require.NotNil(t, response)
	require.Equal(t, http.StatusServiceUnavailable, response.StatusCode)
	require.True(t, mr.Exists(wsTicketKeyPrefix+validTicket), "a refused upgrade must preserve its one-time ticket")

	wtransport := httptest.NewRecorder()
	h.HandleWebTransport(wtransport, httptest.NewRequest(http.MethodGet, "/wt?ticket="+validTicket, nil), &config.Config{})
	require.Equal(t, http.StatusServiceUnavailable, wtransport.Code)
	require.True(t, mr.Exists(wsTicketKeyPrefix+validTicket), "the WebTransport refusal must also preserve the ticket")
}

func TestAUD478ExistingSocketRejectsCachedAllowImmediatelyOnNATSDisconnect(t *testing.T) {
	server, calls := aud478BackendAnswer(t, http.StatusOK)
	auth := mustNewTestAuthClient(t, server.URL, "", nil)
	require.True(t, auth.CanJoinRoom(context.Background(), rdUser, rdRoom))

	nc := aud478DisconnectableNATS(t)
	h := setupTestHub()
	h.Nats = nc
	h.authClient = auth
	h.authCacheTracked.Store(true)
	t.Cleanup(h.Stop)
	client, socket := aud478Socket(t, h, "aud478-cached")

	// Close the real NATS connection before either admission watchdog polls it.
	// The cached allow must not authorize an action on the existing socket.
	nc.Close()
	require.False(t, nc.IsConnected())
	sendAUD337Text(t, socket, `{"type":"join","room":"`+rdRoom+`"}`)
	aud478WaitForRetryClose(t, socket)
	require.False(t, client.isInRoom(rdRoom), "a cached allow must not admit a join during a NATS outage")
	require.EqualValues(t, 1, calls.Load(), "the test must begin with a cached allow")
}

type aud478HeldCacheAnswer struct {
	*InternalAPIAuthClient
	started chan struct{}
	release chan struct{}
	once    sync.Once
}

func (a *aud478HeldCacheAnswer) CanJoinRoom(ctx context.Context, userID, roomID string) bool {
	allowed := a.InternalAPIAuthClient.CanJoinRoom(ctx, userID, roomID)
	a.once.Do(func() { close(a.started) })
	select {
	case <-a.release:
		return allowed
	case <-ctx.Done():
		return false
	}
}

func TestAUD478ExistingSocketRejectsCachedAnswerRetiredBeforeCommit(t *testing.T) {
	server, calls := aud478BackendAnswer(t, http.StatusOK)
	cache := mustNewTestAuthClient(t, server.URL, "", nil)
	require.True(t, cache.CanJoinRoom(context.Background(), rdUser, rdRoom))
	auth := &aud478HeldCacheAnswer{
		InternalAPIAuthClient: cache,
		started:               make(chan struct{}),
		release:               make(chan struct{}),
	}
	var releaseOnce sync.Once
	h := setupTestHub()
	h.authClient = auth
	h.authCacheTracked.Store(true)
	h.revocationConnected = func(*nats.Conn) bool { return true }
	t.Cleanup(h.Stop)
	client, socket := aud478Socket(t, h, "aud478-held-cache")
	t.Cleanup(func() { releaseOnce.Do(func() { close(auth.release) }) })

	sendAUD337Text(t, socket, `{"type":"join","room":"`+rdRoom+`"}`)
	waitRoomMembershipSignal(t, auth.started, "cached authorization did not finish")
	// Keep the NATS count constant to isolate the cache-generation fence from
	// the separate reconnect-count check.
	require.NoError(t, h.completeAuthCacheReset(context.Background()))
	releaseOnce.Do(func() { close(auth.release) })
	aud478WaitForRetryClose(t, socket)
	require.False(t, client.isInRoom(rdRoom), "the generation fence must reject an allow returned before reset")
	require.EqualValues(t, 1, calls.Load())

	// A reconnected socket obtains a fresh allow in the current generation.
	replacement, replacementSocket := aud478Socket(t, h, "aud478-held-cache-reconnected")
	aud478SendJoin(t, replacementSocket, rdRoom)
	aud478WaitForJoin(t, replacement)
	require.True(t, replacement.isInRoom(rdRoom))
	require.EqualValues(t, 2, calls.Load())
}

func TestAUD478ExistingSocketHonorsEachAdmissionBarrier(t *testing.T) {
	server, calls := aud478BackendAnswer(t, http.StatusOK)
	auth := mustNewTestAuthClient(t, server.URL, "", nil)
	require.True(t, auth.CanJoinRoom(context.Background(), rdUser, rdRoom))
	h := setupTestHub()
	h.authClient = auth
	h.authCacheTracked.Store(true)
	h.revocationConnected = func(*nats.Conn) bool { return true }
	var reconnects atomic.Uint64
	h.natsReconnectCount = func(*nats.Conn) uint64 { return reconnects.Load() }
	t.Cleanup(h.Stop)
	replayClient, replaySocket := aud478Socket(t, h, "aud478-replay-barrier")
	resetClient, resetSocket := aud478Socket(t, h, "aud478-reset-barrier")
	reconnectClient, reconnectSocket := aud478Socket(t, h, "aud478-reconnect-barrier")

	h.revocationCatchingUp.Store(true)
	sendAUD337Text(t, replaySocket, `{"type":"join","room":"`+rdRoom+`"}`)
	aud478WaitForRetryClose(t, replaySocket)
	require.False(t, replayClient.isInRoom(rdRoom), "revocation replay must also gate existing joins")
	h.revocationCatchingUp.Store(false)
	h.authCacheAdmissionClosed.Store(true)
	sendAUD337Text(t, resetSocket, `{"type":"join","room":"`+rdRoom+`"}`)
	aud478WaitForRetryClose(t, resetSocket)
	require.False(t, resetClient.isInRoom(rdRoom), "an incomplete reset must gate existing joins")
	h.authCacheAdmissionClosed.Store(false)
	reconnects.Add(1)
	sendAUD337Text(t, reconnectSocket, `{"type":"join","room":"`+rdRoom+`"}`)
	aud478WaitForRetryClose(t, reconnectSocket)
	require.False(t, reconnectClient.isInRoom(rdRoom), "a newly observed reconnect must close admission before the watcher")
	require.EqualValues(t, 1, calls.Load())
}

func TestAUD478AuthoritativeDenialLeavesSocketOpen(t *testing.T) {
	server, calls := aud478BackendAnswer(t, http.StatusForbidden)
	h := setupTestHub()
	h.authClient = mustNewTestAuthClient(t, server.URL, "", nil)
	h.authCacheTracked.Store(true)
	h.revocationConnected = func(*nats.Conn) bool { return true }
	t.Cleanup(h.Stop)
	client, socket, _ := startAUD337ClientWithBeforePumps(t, h, 8, true, func(client *Client, _ <-chan struct{}) {
		client.UserID = rdUser
	})

	aud478SendJoin(t, socket, rdRoom)
	_, response := readAUD337JSON(t, socket)
	require.Equal(t, "heartbeat_pong", response["type"], "an ordinary denial must not close the socket")
	require.False(t, client.isInRoom(rdRoom))
	require.EqualValues(t, 1, calls.Load())
}

func TestAUD478EmptyReplayDoesNotCreateRoomMembership(t *testing.T) {
	h := setupTestHub()
	t.Cleanup(h.Stop)
	client, _ := aud478Socket(t, h, "aud478-empty-replay")
	_, replay := client.prepareRoomReplay(client.ctx, "")
	require.NotNil(t, replay)
	require.False(t, client.isInRoom(""))
	h.mu.RLock()
	_, registered := h.Rooms[""]
	h.mu.RUnlock()
	require.False(t, registered)
	client.cancelRoomReplay("")
}

type aud478ObservedFlight struct {
	*InternalAPIAuthClient
	requests atomic.Int32
	waiter   *aud478FlightContext
}

type aud478FlightContext struct {
	context.Context
	armed    atomic.Bool
	observed chan struct{}
	once     sync.Once
}

func (c *aud478FlightContext) Done() <-chan struct{} {
	if c.armed.Load() {
		c.once.Do(func() { close(c.observed) })
	}
	return c.Context.Done()
}

func (a *aud478ObservedFlight) CanJoinRoom(ctx context.Context, userID, roomID string) bool {
	if a.requests.Add(1) == 2 {
		a.waiter.armed.Store(true)
	}
	return a.InternalAPIAuthClient.CanJoinRoom(ctx, userID, roomID)
}

func TestAUD478ExistingSocketsRejectSingleFlightAllowAcrossReset(t *testing.T) {
	started := make(chan struct{})
	release := make(chan struct{})
	var releaseOnce sync.Once
	var calls atomic.Int32
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if calls.Add(1) == 1 {
			close(started)
			select {
			case <-release:
			case <-r.Context().Done():
				return
			}
			w.WriteHeader(http.StatusOK)
			return
		}
		w.WriteHeader(http.StatusForbidden)
	}))
	t.Cleanup(server.Close)
	auth := &aud478ObservedFlight{
		InternalAPIAuthClient: mustNewTestAuthClient(t, server.URL, "", nil),
	}
	h := setupTestHub()
	h.authClient = auth
	h.authCacheTracked.Store(true)
	var connected atomic.Bool
	connected.Store(true)
	h.revocationConnected = func(*nats.Conn) bool { return connected.Load() }
	var reconnects atomic.Uint64
	h.natsReconnectCount = func(*nats.Conn) uint64 { return reconnects.Load() }
	t.Cleanup(h.Stop)
	first, socket1 := aud478Socket(t, h, "aud478-first")
	waiter, socket2 := aud478SocketWithSetup(t, h, "aud478-waiter", func(client *Client) {
		auth.waiter = &aud478FlightContext{Context: client.ctx, observed: make(chan struct{})}
		client.ctx = auth.waiter
	})
	afterReset, socket3 := aud478Socket(t, h, "aud478-after-reset")
	t.Cleanup(func() { releaseOnce.Do(func() { close(release) }) })

	sendAUD337Text(t, socket1, `{"type":"join","room":"`+rdRoom+`"}`)
	waitRoomMembershipSignal(t, started, "backend authorization did not start")
	sendAUD337Text(t, socket2, `{"type":"join","room":"`+rdRoom+`"}`)
	waitRoomMembershipSignal(t, auth.waiter.observed, "second socket did not attach to the flight")
	require.EqualValues(t, 1, calls.Load(), "the waiter must share the first backend request")

	connected.Store(false)
	reconnects.Add(1)
	h.closeAndObserveNATSSession(reconnects.Load())
	connected.Store(true)
	require.NoError(t, h.completeAuthCacheReset(context.Background()))
	// This test exercises cache single-flight behavior after both admission barriers clear.
	oldConsumerInfo := revocationConsumerInfoFunc
	t.Cleanup(func() { revocationConsumerInfoFunc = oldConsumerInfo })
	revocationConsumerInfoFunc = func(*nats.Subscription) (*nats.ConsumerInfo, error) {
		return &nats.ConsumerInfo{}, nil
	}
	reason := ""
	h.checkRevocationCatchUp(context.Background(), nil, &reason)
	require.False(t, h.AdmissionClosed())

	// The post-reset join must start a new flight without waiting for the old
	// allow, and the current backend denial must leave this socket open.
	aud478SendJoin(t, socket3, rdRoom)
	aud478WaitForJoin(t, afterReset)
	require.False(t, afterReset.isInRoom(rdRoom))
	require.EqualValues(t, 2, calls.Load(), "the post-reset join must use a new backend request")
	releaseOnce.Do(func() { close(release) })
	aud478WaitForRetryClose(t, socket1)
	aud478WaitForRetryClose(t, socket2)
	require.False(t, first.isInRoom(rdRoom))
	require.False(t, waiter.isInRoom(rdRoom))
}
