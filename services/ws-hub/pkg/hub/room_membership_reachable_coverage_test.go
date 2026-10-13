package hub

import (
	"context"
	"errors"
	"sync/atomic"
	"testing"
	"time"

	"github.com/nats-io/nats.go"
	"github.com/prometheus/client_golang/prometheus/testutil"
	"github.com/stretchr/testify/require"
)

func TestAuthorizeRoomJoinRejectsCanceledCallerBeforeBackend(t *testing.T) {
	const userID = "11111111-1111-1111-1111-111111111111"
	const roomID = "22222222-2222-2222-2222-222222222222"

	var backendCalls atomic.Int32
	auth := &controlledRoomMembershipAuth{
		canJoin: func(context.Context, string, string) bool {
			backendCalls.Add(1)
			return true
		},
		refresh: func(context.Context, string, string) (bool, error) {
			backendCalls.Add(1)
			return true, nil
		},
	}
	h := newNatsTestHub(auth, "", 10)
	client := &Client{
		ID: "canceled-join", UserID: userID, Hub: h,
		Rooms: make(map[string]bool), Send: make(chan []byte, 1),
	}
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	var commitCalled atomic.Bool

	allowed := client.authorizeRoomJoin(ctx, roomID, func() bool {
		commitCalled.Store(true)
		return true
	})

	require.False(t, allowed, "a canceled caller must not authorize or commit a room join")
	require.Zero(t, backendCalls.Load(), "backend authorization must not run for an inactive caller")
	require.False(t, commitCalled.Load(), "membership must not commit for an inactive caller")
	require.False(t, client.isInRoom(roomID))
}

func TestQueuedRoomWriteStopsWaitingWhenClientContextCancels(t *testing.T) {
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
	client, session := newRevocationTestClient(h, "queued-canceled", userID, "11111111-1111-4111-8111-111111111111", "websocket")
	client.JoinRoom(roomID)
	observedCtx := &observedDoneContext{Context: client.ctx, observed: make(chan struct{})}
	client.ctx = observedCtx

	permitLock := h.roomMembershipLock(userID, roomID)
	permit, wait := permitLock.tryWritePermit()
	require.NotNil(t, permit, "the test must hold the admission permit before revocation")
	require.Nil(t, wait)
	permitHeld := permit != nil
	evictionDone := make(chan error, 1)
	writerDone := make(chan error, 1)
	evictionStarted := false
	evictionFinished := false
	writerStarted := false
	writerFinished := false
	t.Cleanup(func() {
		client.cancel()
		if permitHeld {
			permit.release()
			permitHeld = false
		}
		if writerStarted && !writerFinished {
			select {
			case <-writerDone:
			case <-time.After(2 * time.Second):
				t.Error("queued writer did not exit during cleanup")
			}
		}
		if evictionStarted && !evictionFinished {
			select {
			case <-evictionDone:
			case <-time.After(2 * time.Second):
				t.Error("room eviction did not exit during cleanup")
			}
		}
	})

	barrierLock := h.roomMembershipLock(userID, roomID)
	barrierLock.Lock()
	barrierStarted := barrierLock.entry.changedLocked()
	barrierLock.Unlock()
	go func() {
		evictionDone <- h.evictRoomMembership(context.Background(), userID, roomID)
	}()
	evictionStarted = true
	waitRoomMembershipSignal(t, barrierStarted, "eviction did not close room write admission")

	go func() {
		writerDone <- client.writeQueuedMessage(
			[]byte("{\"type\":\"notification\",\"room\":\""+roomID+"\"}"),
			true,
		)
	}()
	writerStarted = true
	waitRoomMembershipSignal(t, observedCtx.observed, "queued writer did not reach the permit wait")
	client.cancel()
	select {
	case err := <-writerDone:
		writerFinished = true
		require.ErrorIs(t, err, errSessionInactive,
			"a queued room frame must stop when its client is canceled behind revocation")
	case <-time.After(2 * time.Second):
		t.Fatal("queued room writer ignored client cancellation")
	}
	session.mu.Lock()
	writes := len(session.writes)
	session.mu.Unlock()
	require.Zero(t, writes, "a canceled queued frame must not reach the socket")

	permit.release()
	permitHeld = false
	select {
	case err := <-evictionDone:
		evictionFinished = true
		require.NoError(t, err)
	case <-time.After(2 * time.Second):
		t.Fatal("eviction did not finish after the admitted write drained")
	}
	require.EqualValues(t, 1, refreshCalls.Load(), "authorization refresh must run only after the old permit drains")
	require.False(t, client.isInRoom(roomID), "the authoritative deny must remove local membership")
}

func TestEvictionRetriesAfterPriorMutationCompletionSignal(t *testing.T) {
	const userID = "11111111-1111-1111-1111-111111111111"
	const roomID = "22222222-2222-2222-2222-222222222222"

	refreshStarted := make(chan struct{})
	var refreshCalls atomic.Int32
	auth := &controlledRoomMembershipAuth{
		canJoin: func(context.Context, string, string) bool { return true },
		refresh: func(context.Context, string, string) (bool, error) {
			if refreshCalls.Add(1) != 1 {
				return false, errors.New("unexpected authorization refresh")
			}
			close(refreshStarted)
			return false, nil
		},
	}
	h := newNatsTestHub(auth, "", 10)
	barrierLock := h.roomMembershipLock(userID, roomID)
	barrierLock.Lock()
	barrierLock.entry.mutationPending = true
	barrierLock.entry.revocations = 1
	barrierLock.entry.revocationEpoch = &roomMembershipEpoch{marker: 1}
	pendingChanged := barrierLock.entry.changedLocked()
	barrierLock.unlockRetained()
	barrierHeld := true

	ctx, cancel := context.WithCancel(context.Background())
	observedCtx := &observedDoneContext{Context: ctx, observed: make(chan struct{})}
	evictionDone := make(chan error, 1)
	evictionExited := make(chan struct{})
	evictionStarted := false
	evictionFinished := false
	t.Cleanup(func() {
		cancel()
		if evictionStarted && !evictionFinished {
			select {
			case <-evictionExited:
			case <-time.After(2 * time.Second):
				t.Error("overlapping eviction did not exit during cleanup")
			}
		}
		if barrierHeld {
			barrierLock.release()
			barrierHeld = false
		}
	})

	go func() {
		defer close(evictionExited)
		evictionDone <- h.evictRoomMembership(observedCtx, userID, roomID)
	}()
	evictionStarted = true
	waitRoomMembershipSignal(t, observedCtx.observed, "overlapping eviction did not wait on the pending mutation")
	select {
	case <-refreshStarted:
		t.Fatal("authorization refresh ran before the prior mutation completed")
	default:
	}

	barrierLock.Lock()
	barrierLock.entry.mutationPending = false
	barrierLock.entry.revocations--
	barrierLock.entry.signalChangedLocked()
	barrierLock.unlockRetained()
	select {
	case <-pendingChanged:
	case <-time.After(2 * time.Second):
		t.Fatal("prior mutation did not signal its waiting eviction")
	}
	select {
	case <-refreshStarted:
	case <-time.After(2 * time.Second):
		t.Fatal("overlapping eviction did not retry after the mutation signal")
	}
	select {
	case err := <-evictionDone:
		evictionFinished = true
		require.NoError(t, err)
	case <-time.After(2 * time.Second):
		t.Fatal("overlapping eviction did not finish after its refresh")
	}
	require.EqualValues(t, 1, refreshCalls.Load())
	require.False(t, h.isRoomRevocationPending(userID, roomID))
}

func TestFailedClosedDrainClearsFenceAfterLastPermitFinishes(t *testing.T) {
	const userID = "11111111-1111-1111-1111-111111111111"
	const roomID = "22222222-2222-2222-2222-222222222222"

	h := newNatsTestHub(nil, "", 10)
	permitLock := h.roomMembershipLock(userID, roomID)
	permit, wait := permitLock.tryWritePermit()
	require.NotNil(t, permit)
	require.Nil(t, wait)
	permitHeld := permit != nil
	t.Cleanup(func() {
		if permitHeld {
			permit.release()
			permitHeld = false
		}
	})

	observeLock := h.roomMembershipLock(userID, roomID)
	observeLock.Lock()
	drained := observeLock.entry.writesDrained
	observeLock.Unlock()
	require.NotNil(t, drained, "the admitted write must expose a drain channel")

	revocationLock := h.roomMembershipLock(userID, roomID)
	revocationLock.Lock()
	epoch := &roomMembershipEpoch{marker: 1}
	if revocationLock.entry.revocations == 0 {
		revocationLock.entry.signalChangedLocked()
	}
	revocationLock.entry.revocationEpoch = epoch
	revocationLock.entry.revocations++
	admissionChanged := revocationLock.entry.changedLocked()
	revocationLock.unlockRetained()
	revocationLockHeld := true
	t.Cleanup(func() {
		if revocationLockHeld {
			revocationLock.release()
			revocationLockHeld = false
		}
	})

	permit.release()
	permitHeld = false
	waitRoomMembershipSignal(t, drained, "last admitted write did not close the drain channel")
	// This models cancellation selecting its branch just as the final permit
	// closes the drain channel captured by the revocation.
	h.failClosedRoomMembershipDrain(revocationLock, epoch, userID, roomID)

	revocationLock.Lock()
	failedClosed := revocationLock.entry.drainFailedClosed.Load()
	mutationPending := revocationLock.entry.mutationPending
	revocations := revocationLock.entry.revocations
	revocationLock.Unlock()
	revocationLockHeld = false
	require.False(t, failedClosed, "a completed last write must not leave admission fail-closed")
	require.False(t, mutationPending, "the removal mutation must be completed before admission reopens")
	require.Zero(t, revocations)
	waitRoomMembershipSignal(t, admissionChanged, "completed drain cleanup did not signal queued admissions")
	require.True(t, h.isRoomRevocationPending(userID, roomID),
		"clearing a drained-write fence must preserve the authoritative refresh requirement")
}

func TestRoomRevocationSkipsRefreshForCanceledContext(t *testing.T) {
	const userID = "11111111-1111-1111-1111-111111111111"
	const roomID = "22222222-2222-2222-2222-222222222222"

	var refreshCalls atomic.Int32
	auth := &controlledRoomMembershipAuth{
		canJoin: func(context.Context, string, string) bool { return true },
		refresh: func(context.Context, string, string) (bool, error) {
			refreshCalls.Add(1)
			return true, nil
		},
	}
	h := newNatsTestHub(auth, "", 10)
	client := &Client{
		ID: "canceled-revocation", UserID: userID, Hub: h,
		Rooms: make(map[string]bool), Send: make(chan []byte, 1),
	}
	client.JoinRoom(roomID)
	ctx, cancel := context.WithCancel(context.Background())
	cancel()

	err := h.evictRoomMembership(ctx, userID, roomID)

	require.ErrorIs(t, err, context.Canceled)
	require.Zero(t, refreshCalls.Load(), "a canceled revocation must not call the authorization backend")
	require.False(t, client.isInRoom(roomID), "failed-closed authorization must remove local membership")
	require.True(t, h.isRoomRevocationPending(userID, roomID),
		"a canceled authoritative check must leave the room pending for a future refresh")
}

func TestAuthorizeRoomJoinRetriesAfterMembershipBarrierChanges(t *testing.T) {
	const userID = "11111111-1111-1111-1111-111111111111"
	const roomID = "22222222-2222-2222-2222-222222222222"

	var authorizationCalls atomic.Int32
	var commitCalls atomic.Int32
	auth := &controlledRoomMembershipAuth{
		canJoin: func(context.Context, string, string) bool {
			authorizationCalls.Add(1)
			return true
		},
		refresh: func(context.Context, string, string) (bool, error) {
			return false, errors.New("unexpected refresh for a cleared revocation")
		},
	}
	h := newNatsTestHub(auth, "", 10)
	client := &Client{
		ID: "barrier-retry", UserID: userID, Hub: h,
		Rooms: make(map[string]bool), Send: make(chan []byte, 1),
	}
	barrier, epoch, _, err := h.beginRoomMembershipRevocation(context.Background(), userID, roomID)
	require.NoError(t, err)
	barrierActive := true
	joinStarted := false
	joinFinished := false
	joinDone := make(chan bool, 1)
	joinExited := make(chan struct{})
	t.Cleanup(func() {
		if barrierActive {
			h.finishRoomMembershipRevocation(barrier, epoch, userID, roomID, true, nil)
			barrier.release()
		}
		if joinStarted && !joinFinished {
			select {
			case <-joinExited:
			case <-time.After(2 * time.Second):
				t.Error("barrier retry join did not exit during cleanup")
			}
		}
	})

	caller := &observedDoneContext{Context: context.Background(), observed: make(chan struct{})}
	go func() {
		defer close(joinExited)
		joinDone <- client.authorizeRoomJoin(caller, roomID, func() bool {
			commitCalls.Add(1)
			return true
		})
	}()
	joinStarted = true
	waitRoomMembershipSignal(t, caller.observed, "join did not wait at the active revocation barrier")
	require.Zero(t, authorizationCalls.Load(), "authorization must not run while the barrier is active")

	h.finishRoomMembershipRevocation(barrier, epoch, userID, roomID, true, nil)
	barrier.release()
	barrierActive = false
	select {
	case allowed := <-joinDone:
		require.True(t, allowed, "a current allow must complete after the barrier changes")
	case <-time.After(2 * time.Second):
		t.Fatal("join did not retry after the revocation barrier changed")
	}
	waitRoomMembershipSignal(t, joinExited, "join worker did not exit after its result")
	joinFinished = true
	require.EqualValues(t, 1, authorizationCalls.Load())
	require.EqualValues(t, 1, commitCalls.Load())
}

func TestAuthorizeRoomJoinStopsWhenCallerContextCancelsBehindRevocation(t *testing.T) {
	const userID = "11111111-1111-1111-1111-111111111111"
	const roomID = "22222222-2222-2222-2222-222222222222"

	var authorizationCalls atomic.Int32
	var commitCalls atomic.Int32
	auth := &controlledRoomMembershipAuth{
		canJoin: func(context.Context, string, string) bool {
			authorizationCalls.Add(1)
			return true
		},
		refresh: func(context.Context, string, string) (bool, error) {
			return false, errors.New("unexpected refresh for a canceled join")
		},
	}
	h := newNatsTestHub(auth, "", 10)
	clientCtx, cancelClient := context.WithCancel(context.Background())
	callerCtx, cancelCaller := context.WithCancel(context.Background())
	client := &Client{
		ID: "caller-canceled-barrier", UserID: userID, Hub: h,
		Rooms: make(map[string]bool), Send: make(chan []byte, 1),
		ctx: clientCtx, cancel: cancelClient,
	}
	barrier, epoch, _, err := h.beginRoomMembershipRevocation(context.Background(), userID, roomID)
	require.NoError(t, err)
	barrierActive := true
	joinStarted := false
	joinFinished := false
	joinDone := make(chan bool, 1)
	joinExited := make(chan struct{})
	t.Cleanup(func() {
		cancelCaller()
		cancelClient()
		if barrierActive {
			h.finishRoomMembershipRevocation(barrier, epoch, userID, roomID, true, nil)
			barrier.release()
		}
		if joinStarted && !joinFinished {
			select {
			case <-joinExited:
			case <-time.After(2 * time.Second):
				t.Error("caller-canceled join did not exit during cleanup")
			}
		}
	})

	caller := &observedDoneContext{Context: callerCtx, observed: make(chan struct{})}
	go func() {
		defer close(joinExited)
		joinDone <- client.authorizeRoomJoin(caller, roomID, func() bool {
			commitCalls.Add(1)
			return true
		})
	}()
	joinStarted = true
	waitRoomMembershipSignal(t, caller.observed, "join did not wait on the active barrier")
	cancelCaller()
	select {
	case allowed := <-joinDone:
		require.False(t, allowed, "caller cancellation must stop a barrier-waiting join")
	case <-time.After(2 * time.Second):
		t.Fatal("room join ignored caller-context cancellation")
	}
	waitRoomMembershipSignal(t, joinExited, "canceled join worker did not exit")
	joinFinished = true
	require.NoError(t, clientCtx.Err(), "caller cancellation must not cancel the still-live client")
	require.Zero(t, authorizationCalls.Load(), "canceled join must not call backend authorization")
	require.Zero(t, commitCalls.Load(), "canceled join must not commit membership")

	h.finishRoomMembershipRevocation(barrier, epoch, userID, roomID, true, nil)
	barrier.release()
	barrierActive = false
}

func TestFinishAuthorizedRoomJoinSkipsReplayAfterCallerCancellation(t *testing.T) {
	const roomID = "22222222-2222-2222-2222-222222222222"

	h := setupTestHub()
	callerCtx, cancelCaller := context.WithCancel(context.Background())
	client := &Client{
		ID: "canceled-replay-launch", UserID: "11111111-1111-1111-1111-111111111111",
		Hub: h, Rooms: make(map[string]bool), Send: make(chan []byte, 1),
		ctx: callerCtx, cancel: cancelCaller,
	}
	replayCtx, state := client.prepareRoomReplay(callerCtx, roomID)
	pullStarted := make(chan struct{})
	releasePull := make(chan struct{})
	h.js = &scriptedPullSubscription{pull: func(string, string, ...nats.SubOpt) (*nats.Subscription, error) {
		close(pullStarted)
		<-releasePull
		return nil, errors.New("canceled replay must not open a pull subscription")
	}}
	baseline := testutil.ToFloat64(ActiveGoroutines)
	t.Cleanup(func() {
		cancelCaller()
		close(releasePull)
		require.Eventually(t, func() bool {
			return testutil.ToFloat64(ActiveGoroutines) == baseline
		}, 2*time.Second, time.Millisecond, "canceled replay worker remained active during cleanup")
	})

	cancelCaller()
	client.finishAuthorizedRoomJoin(callerCtx, Message{Type: "join", Room: roomID}, &roomJoinDecision{
		replayEnabled: true,
		replayCtx:     replayCtx,
		replayState:   state,
	})
	require.ErrorIs(t, state.ctx.Err(), context.Canceled)
	client.replayMu.Lock()
	remaining := client.replays[roomID]
	client.replayMu.Unlock()
	require.Nil(t, remaining, "a canceled replay launch must remove its replay barrier")
	require.Equal(t, baseline, testutil.ToFloat64(ActiveGoroutines),
		"canceled caller must not start a tracked replay worker")
	select {
	case <-pullStarted:
		t.Fatal("canceled replay launch must not create a JetStream pull subscription")
	default:
	}
}
