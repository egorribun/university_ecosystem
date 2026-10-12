package hub

import (
	"context"
	"errors"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"github.com/stretchr/testify/require"
)

type controlledRoomMembershipAuth struct {
	canJoin func(context.Context, string, string) bool
	refresh func(context.Context, string, string) (bool, error)
}

func (a *controlledRoomMembershipAuth) CanJoinRoom(ctx context.Context, userID, roomID string) bool {
	return a.canJoin(ctx, userID, roomID)
}

func (a *controlledRoomMembershipAuth) Invalidate(string, string) {}

func (a *controlledRoomMembershipAuth) RefreshRoomAuthorization(
	ctx context.Context,
	userID, roomID string,
) (bool, error) {
	return a.refresh(ctx, userID, roomID)
}

func waitRoomMembershipBarrierStart(t *testing.T, h *Hub, userID, roomID string) (<-chan struct{}, func()) {
	t.Helper()
	lock := h.roomMembershipLock(userID, roomID)
	lock.Lock()
	changed := lock.entry.changedLocked()
	lock.unlockRetained()
	var releaseOnce sync.Once
	return changed, func() { releaseOnce.Do(lock.release) }
}

func waitRoomMembershipSignal(t *testing.T, signal <-chan struct{}, message string) {
	t.Helper()
	select {
	case <-signal:
	case <-time.After(2 * time.Second):
		t.Fatal(message)
	}
}

func TestBlockedJoinCannotCommitAuthorizationFromBeforeRevocation(t *testing.T) {
	const userID = "11111111-1111-1111-1111-111111111111"
	const roomID = "22222222-2222-2222-2222-222222222222"
	joinStarted := make(chan struct{})
	firstJoinResult := make(chan bool, 1)
	refreshStarted := make(chan struct{})
	refreshResult := make(chan bool, 1)
	var joinCalls atomic.Int32
	var joinOnce sync.Once
	auth := &controlledRoomMembershipAuth{
		canJoin: func(context.Context, string, string) bool {
			if joinCalls.Add(1) == 1 {
				joinOnce.Do(func() { close(joinStarted) })
				return <-firstJoinResult
			}
			return false
		},
		refresh: func(context.Context, string, string) (bool, error) {
			close(refreshStarted)
			return <-refreshResult, nil
		},
	}
	h := newNatsTestHub(auth, "internal-secret", 10) // pragma: allowlist secret
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	client := &Client{
		ID:               "stale-join-client",
		SessionJTI:       validSessionJTI,
		SessionExpiresAt: time.Now().Add(time.Hour),
		UserID:           userID,
		Rooms:            make(map[string]bool),
		Send:             make(chan []byte, 1),
		Hub:              h,
		ctx:              ctx,
		cancel:           cancel,
	}

	joinDone := make(chan struct{})
	joinGoroutineStarted := false
	evictStarted := false
	evictFinished := make(chan struct{})
	evictDone := make(chan error, 1)
	t.Cleanup(func() {
		select {
		case firstJoinResult <- false:
		default:
		}
		select {
		case refreshResult <- false:
		default:
		}
		if joinGoroutineStarted {
			select {
			case <-joinDone:
			case <-time.After(2 * time.Second):
				t.Error("join goroutine did not exit during cleanup")
			}
		}
		if evictStarted {
			select {
			case <-evictFinished:
			case <-time.After(2 * time.Second):
				t.Error("revocation goroutine did not exit during cleanup")
			}
		}
	})
	go func() {
		client.handleJoin(ctx, Message{Type: "join", Room: roomID})
		close(joinDone)
	}()
	joinGoroutineStarted = true
	waitRoomMembershipSignal(t, joinStarted, "initial room authorization did not start")

	barrierStarted, releaseBarrier := waitRoomMembershipBarrierStart(t, h, userID, roomID)
	t.Cleanup(releaseBarrier)
	go func() {
		evictDone <- h.evictRoomMembership(context.Background(), userID, roomID)
		close(evictFinished)
	}()
	evictStarted = true
	waitRoomMembershipSignal(t, barrierStarted, "revocation did not close room write admission")
	releaseBarrier()
	waitRoomMembershipSignal(t, refreshStarted, "revocation refresh did not start")
	refreshResult <- false
	select {
	case err := <-evictDone:
		require.NoError(t, err)
	case <-time.After(2 * time.Second):
		t.Fatal("revocation did not finish")
	}

	// The old request now returns an allow verdict. It must be discarded and
	// rechecked against the post-revocation state, whose answer is deny.
	firstJoinResult <- true
	select {
	case <-joinDone:
	case <-time.After(2 * time.Second):
		t.Fatal("stale join did not finish its post-revocation check")
	}
	require.EqualValues(t, 2, joinCalls.Load())
	require.False(t, client.isInRoom(roomID), "pre-revocation allow must not restore room membership")
}

func TestBlockedWriteDrainsBeforeRevocationAndQueuedFrameIsDropped(t *testing.T) {
	const userID = "11111111-1111-1111-1111-111111111111"
	const roomID = "22222222-2222-2222-2222-222222222222"
	refreshStarted := make(chan struct{})
	refreshResult := make(chan bool, 1)
	auth := &controlledRoomMembershipAuth{
		canJoin: func(context.Context, string, string) bool { return true },
		refresh: func(context.Context, string, string) (bool, error) {
			close(refreshStarted)
			return <-refreshResult, nil
		},
	}
	h := newNatsTestHub(auth, "internal-secret", 10) // pragma: allowlist secret
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	order := &roomWriteOrder{}
	session := &blockedRoomWriteSession{
		writeStarted: make(chan struct{}, 2),
		allowWrite:   make(chan struct{}),
		order:        order,
	}
	client := &Client{
		ID:               "queued-frame-client",
		SessionJTI:       validSessionJTI,
		SessionExpiresAt: time.Now().Add(time.Hour),
		UserID:           userID,
		Rooms:            make(map[string]bool),
		Conn:             session,
		Send:             make(chan []byte, 2),
		Hub:              h,
		ctx:              ctx,
		cancel:           cancel,
	}
	client.JoinRoom(roomID)
	privateFrame := []byte(`{"type":"new_message","room":"22222222-2222-2222-2222-222222222222","payload":{"text":"private"}}`)
	client.Send <- privateFrame
	client.Send <- privateFrame
	close(client.Send)
	writeDone := make(chan struct{})
	writePumpStarted := false
	evictDone := make(chan error, 1)
	evictFinished := make(chan struct{})
	evictStarted := false
	t.Cleanup(func() {
		session.release()
		select {
		case refreshResult <- false:
		default:
		}
		cancel()
		if evictStarted {
			select {
			case <-evictFinished:
			case <-time.After(2 * time.Second):
				t.Error("revocation goroutine did not exit during cleanup")
			}
		}
		if writePumpStarted {
			select {
			case <-writeDone:
			case <-time.After(2 * time.Second):
				t.Error("write pump did not exit during cleanup")
			}
		}
	})
	go func() {
		client.WritePump()
		close(writeDone)
	}()
	writePumpStarted = true
	waitRoomMembershipSignal(t, session.writeStarted, "first private frame did not enter the blocked socket write")

	barrierStarted, releaseBarrier := waitRoomMembershipBarrierStart(t, h, userID, roomID)
	t.Cleanup(releaseBarrier)
	go func() {
		evictDone <- h.evictRoomMembership(context.Background(), userID, roomID)
		close(evictFinished)
	}()
	evictStarted = true
	waitRoomMembershipSignal(t, barrierStarted, "revocation did not close room write admission")
	releaseBarrier()
	session.release()
	waitRoomMembershipSignal(t, refreshStarted, "authorization refresh did not start after the in-flight write drained")
	refreshResult <- false
	select {
	case err := <-evictDone:
		require.NoError(t, err)
	case <-time.After(2 * time.Second):
		t.Fatal("revocation did not finish after the write drained")
	}
	select {
	case <-writeDone:
	case <-time.After(2 * time.Second):
		t.Fatal("write pump did not consume the queued frame and close marker")
	}
	require.False(t, client.isInRoom(roomID))
	require.Equal(t, []string{"private_frame_written"}, order.snapshot(),
		"only the frame admitted before revocation may reach the socket")
	select {
	case <-session.writeStarted:
		t.Fatal("queued room frame reached the socket after confirmed revocation")
	default:
	}
}

func TestJoinAfterRevocationWaitsForOldEvictionToFinish(t *testing.T) {
	const userID = "11111111-1111-1111-1111-111111111111"
	const roomID = "22222222-2222-2222-2222-222222222222"
	refreshStarted := make(chan struct{})
	refreshResult := make(chan bool, 1)
	joinStarted := make(chan struct{})
	var joinOnce sync.Once
	var joinDuringBarrier atomic.Bool
	var h *Hub
	auth := &controlledRoomMembershipAuth{
		canJoin: func(context.Context, string, string) bool {
			lock := h.roomMembershipLock(userID, roomID)
			lock.Lock()
			blocked := lock.entry.revocations > 0
			lock.Unlock()
			if blocked {
				joinDuringBarrier.Store(true)
			}
			joinOnce.Do(func() { close(joinStarted) })
			return true
		},
		refresh: func(context.Context, string, string) (bool, error) {
			close(refreshStarted)
			return <-refreshResult, nil
		},
	}
	h = newNatsTestHub(auth, "internal-secret", 10) // pragma: allowlist secret
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	session := &blockedRoomWriteSession{
		writeStarted: make(chan struct{}, 1),
		allowWrite:   make(chan struct{}),
		order:        &roomWriteOrder{},
	}
	client := &Client{
		ID:               "fresh-join-client",
		SessionJTI:       validSessionJTI,
		SessionExpiresAt: time.Now().Add(time.Hour),
		UserID:           userID,
		Rooms:            make(map[string]bool),
		Conn:             session,
		Send:             make(chan []byte, 1),
		Hub:              h,
		ctx:              ctx,
		cancel:           cancel,
	}
	client.JoinRoom(roomID)
	client.Send <- []byte(`{"type":"new_message","room":"22222222-2222-2222-2222-222222222222","payload":{"text":"private"}}`)
	writeDone := make(chan struct{})
	writePumpStarted := false
	evictDone := make(chan error, 1)
	evictFinished := make(chan struct{})
	evictStarted := false
	joinDone := make(chan struct{})
	joinGoroutineStarted := false
	t.Cleanup(func() {
		session.release()
		select {
		case refreshResult <- false:
		default:
		}
		cancel()
		if joinGoroutineStarted {
			select {
			case <-joinDone:
			case <-time.After(2 * time.Second):
				t.Error("join goroutine did not exit during cleanup")
			}
		}
		if evictStarted {
			select {
			case <-evictFinished:
			case <-time.After(2 * time.Second):
				t.Error("revocation goroutine did not exit during cleanup")
			}
		}
		if writePumpStarted {
			select {
			case <-writeDone:
			case <-time.After(2 * time.Second):
				t.Error("write pump did not exit during cleanup")
			}
		}
	})
	go func() {
		client.WritePump()
		close(writeDone)
	}()
	writePumpStarted = true
	waitRoomMembershipSignal(t, session.writeStarted, "private frame did not enter the blocked socket write")

	barrierStarted, releaseBarrier := waitRoomMembershipBarrierStart(t, h, userID, roomID)
	t.Cleanup(releaseBarrier)
	go func() {
		evictDone <- h.evictRoomMembership(context.Background(), userID, roomID)
		close(evictFinished)
	}()
	evictStarted = true
	waitRoomMembershipSignal(t, barrierStarted, "revocation did not close room write admission")
	releaseBarrier()
	go func() {
		client.handleJoin(ctx, Message{Type: "join", Room: roomID})
		close(joinDone)
	}()
	joinGoroutineStarted = true
	session.release()
	waitRoomMembershipSignal(t, refreshStarted, "authorization refresh did not start after the in-flight write drained")
	refreshResult <- false
	select {
	case err := <-evictDone:
		require.NoError(t, err)
	case <-time.After(2 * time.Second):
		t.Fatal("old revocation did not finish")
	}
	waitRoomMembershipSignal(t, joinStarted, "fresh join was not reauthorized after the revocation barrier")
	select {
	case <-joinDone:
	case <-time.After(2 * time.Second):
		t.Fatal("fresh join did not finish")
	}
	require.False(t, joinDuringBarrier.Load(), "join authorization must wait until revocation completes")
	require.True(t, client.isInRoom(roomID), "the old eviction must not remove a post-barrier grant")
	cancel()
	select {
	case <-writeDone:
	case <-time.After(2 * time.Second):
		t.Fatal("write pump did not stop after cancellation")
	}
}

type deadlineRejectingRoomWriteSession struct {
	*blockedRoomWriteSession
	firstFrameFinished chan struct{}
	finishOnce         sync.Once
}

func (s *deadlineRejectingRoomWriteSession) SetWriteDeadline(time.Time) error {
	return errors.New("test socket does not support write deadlines")
}

func (s *deadlineRejectingRoomWriteSession) WriteMessage(messageType int, data []byte) error {
	err := s.blockedRoomWriteSession.WriteMessage(messageType, data)
	if err == nil {
		s.finishOnce.Do(func() { close(s.firstFrameFinished) })
	}
	return err
}

func TestTimedOutWriteDrainRetainsFenceUntilWriteEndsAndRechecksJoin(t *testing.T) {
	const userID = "11111111-1111-1111-1111-111111111111"
	const roomID = "22222222-2222-2222-2222-222222222222"
	refreshStarted := make(chan struct{})
	var refreshStartedOnce sync.Once
	var refreshCalls atomic.Int32
	var joinCalls atomic.Int32
	auth := &controlledRoomMembershipAuth{
		canJoin: func(context.Context, string, string) bool {
			joinCalls.Add(1)
			return true
		},
		refresh: func(context.Context, string, string) (bool, error) {
			refreshCalls.Add(1)
			refreshStartedOnce.Do(func() { close(refreshStarted) })
			return false, nil
		},
	}
	h := newNatsTestHub(auth, "", 10)
	clientCtx, cancelClient := context.WithCancel(context.Background())
	order := &roomWriteOrder{}
	blocked := &blockedRoomWriteSession{
		writeStarted: make(chan struct{}, 2),
		allowWrite:   make(chan struct{}),
		order:        order,
	}
	session := &deadlineRejectingRoomWriteSession{
		blockedRoomWriteSession: blocked,
		firstFrameFinished:      make(chan struct{}),
	}
	client := &Client{
		ID:               "bounded-drain-client",
		SessionJTI:       validSessionJTI,
		SessionExpiresAt: time.Now().Add(time.Hour),
		UserID:           userID,
		Rooms:            make(map[string]bool),
		Conn:             session,
		Send:             make(chan []byte, 3),
		Hub:              h,
		ctx:              clientCtx,
		cancel:           cancelClient,
	}
	client.JoinRoom(roomID)
	privateFrame := []byte(`{"type":"new_message","room":"22222222-2222-2222-2222-222222222222","payload":{"text":"private"}}`)
	client.Send <- privateFrame
	client.Send <- privateFrame
	close(client.Send)
	writeDone := make(chan struct{})
	writePumpStarted := false
	evictionDone := make(chan error, 1)
	evictionFinished := make(chan struct{})
	evictionStarted := false
	t.Cleanup(func() {
		session.release()
		cancelClient()
		if evictionStarted {
			select {
			case <-evictionFinished:
			case <-time.After(2 * time.Second):
				t.Error("timed-out revocation goroutine did not exit during cleanup")
			}
		}
		if writePumpStarted {
			select {
			case <-writeDone:
			case <-time.After(2 * time.Second):
				t.Error("write pump did not exit during cleanup")
			}
		}
	})
	go func() {
		client.WritePump()
		close(writeDone)
	}()
	writePumpStarted = true
	waitRoomMembershipSignal(t, blocked.writeStarted, "first private frame did not enter the blocked socket write")

	barrierStarted, releaseBarrier := waitRoomMembershipBarrierStart(t, h, userID, roomID)
	t.Cleanup(releaseBarrier)
	drainCtx, cancelDrain := context.WithTimeout(context.Background(), 75*time.Millisecond)
	defer cancelDrain()
	go func() {
		evictionDone <- h.evictRoomMembership(drainCtx, userID, roomID)
		close(evictionFinished)
	}()
	evictionStarted = true
	waitRoomMembershipSignal(t, barrierStarted, "revocation did not close room write admission")
	releaseBarrier()
	select {
	case err := <-evictionDone:
		require.ErrorIs(t, err, context.DeadlineExceeded)
	case <-time.After(2 * time.Second):
		t.Fatal("blocked write drain did not honor caller cancellation")
	}
	require.EqualValues(t, 0, refreshCalls.Load(), "authorization must not refresh before the old write drains")
	select {
	case <-session.firstFrameFinished:
		t.Fatal("the timed-out drain must not claim it cancelled the already admitted frame")
	default:
	}
	require.False(t, client.isInRoom(roomID), "timeout must remove membership without waiting for the blocked socket write")
	require.True(t, h.isRoomRevocationPending(userID, roomID), "timeout must remain retryable as a pending revocation")

	lock := h.roomMembershipLock(userID, roomID)
	lock.Lock()
	failedClosed := lock.entry.drainFailedClosed.Load()
	lock.Unlock()
	require.True(t, failedClosed, "fence must remain closed while the old write is still in flight")
	permit, wait := h.roomMembershipLock(userID, roomID).tryWritePermit()
	require.Nil(t, permit, "future room writes must not receive a permit while drain is uncertain")
	require.NotNil(t, wait)
	select {
	case <-wait:
		t.Fatal("failed-closed admission was signaled open before the old write finished")
	default:
	}

	joinCtx, cancelJoin := context.WithTimeout(context.Background(), 40*time.Millisecond)
	joined := atomic.Bool{}
	joinResult := make(chan bool, 1)
	go func() {
		joinResult <- client.authorizeRoomJoin(joinCtx, roomID, func() bool {
			joined.Store(true)
			return true
		})
	}()
	select {
	case allowed := <-joinResult:
		require.False(t, allowed, "a fresh join must wait behind the failed-closed fence")
	case <-time.After(2 * time.Second):
		t.Fatal("join did not honor its context while waiting behind the fence")
	}
	cancelJoin()
	require.False(t, joined.Load(), "a join must not commit while drain state is uncertain")
	require.EqualValues(t, 0, joinCalls.Load(), "join authorization must not run through the failed-closed fence")
	require.EqualValues(t, 0, refreshCalls.Load(), "join must not refresh through the failed-closed fence")

	session.release()
	waitRoomMembershipSignal(t, session.firstFrameFinished, "already admitted frame did not finish after the test released the socket")
	select {
	case <-writeDone:
	case <-time.After(2 * time.Second):
		t.Fatal("queued frame did not exit after timed-out membership removal")
	}
	select {
	case <-wait:
	default:
		t.Fatal("last room write permit did not close the admission wait channel")
	}
	require.False(t, client.isInRoom(roomID))
	require.True(t, h.isRoomRevocationPending(userID, roomID), "pending state must outlive the ephemeral lock entry")
	h.roomMembershipLocks.mu.Lock()
	retained := h.roomMembershipLocks.entries[roomMembershipKey{userID: userID, roomID: roomID}]
	h.roomMembershipLocks.mu.Unlock()
	require.Nil(t, retained, "drained timeout state must not leave an unreferenced registry tombstone")
	require.Equal(t, []string{"private_frame_written"}, order.snapshot(), "only the frame admitted before the barrier may reach the socket")

	joinCtx, cancelJoin = context.WithTimeout(context.Background(), time.Second)
	defer cancelJoin()
	allowed := client.authorizeRoomJoin(joinCtx, roomID, func() bool {
		joined.Store(true)
		return true
	})
	require.False(t, allowed, "a fresh authoritative deny must not restore the room")
	require.False(t, joined.Load(), "a stale cached allow must not commit after registry cleanup")
	require.EqualValues(t, 1, refreshCalls.Load(), "the pending marker must force an authoritative check after lock-entry deletion")
	require.EqualValues(t, 0, joinCalls.Load(), "pending membership must not use the cached allow path")
	require.False(t, h.isRoomRevocationPending(userID, roomID), "a completed authoritative check may clear the pending marker")
}

func TestRoomRevocationDoesNotWaitForNonRoomSocketWrite(t *testing.T) {
	const userID = "11111111-1111-1111-1111-111111111111"
	const roomID = "22222222-2222-2222-2222-222222222222"
	var refreshCalls atomic.Int32
	auth := &controlledRoomMembershipAuth{
		canJoin: func(context.Context, string, string) bool { return true },
		refresh: func(context.Context, string, string) (bool, error) {
			refreshCalls.Add(1)
			return false, nil
		},
	}
	h := newNatsTestHub(auth, "", 10)
	clientCtx, cancelClient := context.WithCancel(context.Background())
	order := &roomWriteOrder{}
	blocked := &blockedRoomWriteSession{
		writeStarted: make(chan struct{}, 2),
		allowWrite:   make(chan struct{}),
		order:        order,
	}
	session := &deadlineRejectingRoomWriteSession{
		blockedRoomWriteSession: blocked,
		firstFrameFinished:      make(chan struct{}),
	}
	client := &Client{
		ID:               "non-room-write-client",
		SessionJTI:       validSessionJTI,
		SessionExpiresAt: time.Now().Add(time.Hour),
		UserID:           userID,
		Rooms:            make(map[string]bool),
		Conn:             session,
		Send:             make(chan []byte, 3),
		Hub:              h,
		ctx:              clientCtx,
		cancel:           cancelClient,
	}
	client.JoinRoom(roomID)
	client.Send <- []byte(`{"type":"notice","payload":{}}`)
	client.Send <- []byte(`{"type":"new_message","room":"22222222-2222-2222-2222-222222222222","payload":{"text":"private"}}`)
	close(client.Send)
	writeDone := make(chan struct{})
	writePumpStarted := false
	evictionDone := make(chan error, 1)
	evictionFinished := make(chan struct{})
	evictionStarted := false
	t.Cleanup(func() {
		session.release()
		cancelClient()
		if evictionStarted {
			select {
			case <-evictionFinished:
			case <-time.After(2 * time.Second):
				t.Error("room revocation did not exit during cleanup")
			}
		}
		if writePumpStarted {
			select {
			case <-writeDone:
			case <-time.After(2 * time.Second):
				t.Error("write pump did not exit during cleanup")
			}
		}
	})
	go func() {
		client.WritePump()
		close(writeDone)
	}()
	writePumpStarted = true
	waitRoomMembershipSignal(t, blocked.writeStarted, "non-room frame did not enter the blocked socket write")

	barrierStarted, releaseBarrier := waitRoomMembershipBarrierStart(t, h, userID, roomID)
	t.Cleanup(releaseBarrier)
	go func() {
		evictionDone <- h.evictRoomMembership(context.Background(), userID, roomID)
		close(evictionFinished)
	}()
	evictionStarted = true
	waitRoomMembershipSignal(t, barrierStarted, "room revocation did not close write admission")
	releaseBarrier()
	select {
	case err := <-evictionDone:
		require.NoError(t, err, "revocation must not wait on writeMu held by an unrelated socket frame")
	case <-time.After(2 * time.Second):
		t.Fatal("room revocation waited for the non-room socket write")
	}
	require.EqualValues(t, 1, refreshCalls.Load())
	require.False(t, client.isInRoom(roomID), "confirmed denial must remove room membership before the barrier opens")

	session.release()
	waitRoomMembershipSignal(t, session.firstFrameFinished, "the preexisting non-room write did not finish after release")
	select {
	case <-writeDone:
	case <-time.After(2 * time.Second):
		t.Fatal("queued room frame did not exit after membership removal")
	}
	require.Equal(t, []string{"private_frame_written"}, order.snapshot(), "the queued room frame must not reach the socket after revocation")
	select {
	case <-blocked.writeStarted:
		t.Fatal("queued room frame reached the socket after confirmed revocation")
	default:
	}
}

func TestReplayFailureReleasesMembershipLockBeforeClosingTransport(t *testing.T) {
	const userID = "11111111-1111-1111-1111-111111111111"
	const roomID = "22222222-2222-2222-2222-222222222222"

	h := newNatsTestHub(nil, "", 10)
	ctx, cancelContext := context.WithCancel(context.Background())
	defer cancelContext()

	cancelStarted := make(chan struct{})
	var cancelOnce sync.Once
	client := &Client{
		ID:     "replay-failure-client",
		UserID: userID,
		Rooms:  make(map[string]bool),
		Send:   make(chan []byte, 1),
		Hub:    h,
		ctx:    ctx,
		cancel: func() {
			cancelOnce.Do(func() { close(cancelStarted) })
			cancelContext()
		},
		replays: make(map[string]*roomReplayState),
	}
	replayCtx, cancelReplay := context.WithCancel(ctx)
	client.replays[roomID] = &roomReplayState{
		ctx:      replayCtx,
		cancel:   cancelReplay,
		buffered: make(map[uint64][]byte),
	}

	h.mu.Lock()
	h.Rooms[roomID] = map[*Client]bool{client: true}
	h.mu.Unlock()

	membershipLock := h.roomMembershipLock(userID, roomID)
	membershipLock.Lock()
	client.writeMu.Lock()
	writeLocked := true
	deliveryDone := make(chan struct{})
	go func() {
		h.deliverBroadcastRecipient(
			ctx,
			&Message{Type: "new_message", Room: roomID},
			[]byte("{}"),
			recipient{client: client},
		)
		close(deliveryDone)
	}()
	membershipLock.Unlock()

	t.Cleanup(func() {
		if writeLocked {
			client.writeMu.Unlock()
		}
		select {
		case <-deliveryDone:
		case <-time.After(2 * time.Second):
			t.Error("broadcast delivery did not finish during cleanup")
		}
	})

	select {
	case <-cancelStarted:
	case <-time.After(2 * time.Second):
		t.Fatal("replay failure did not begin connection cleanup")
	}

	probe := h.roomMembershipLock(userID, roomID)
	membershipAvailable := probe.entry.mu.TryLock()
	if membershipAvailable {
		probe.entry.mu.Unlock()
	}
	probe.release()

	client.writeMu.Unlock()
	writeLocked = false
	select {
	case <-deliveryDone:
	case <-time.After(2 * time.Second):
		t.Fatal("broadcast delivery remained blocked after releasing the write lock")
	}
	require.True(t, membershipAvailable,
		"replay cleanup waited on writeMu while retaining the room membership lock")
}
