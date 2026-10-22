package hub

import (
	"context"
	"encoding/json"
	"errors"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"github.com/nats-io/nats.go"
	"github.com/prometheus/client_golang/prometheus/testutil"
	"github.com/stretchr/testify/require"
)

type observedDoneContext struct {
	context.Context
	observed chan struct{}
	once     sync.Once
}

func (c *observedDoneContext) Done() <-chan struct{} {
	c.once.Do(func() { close(c.observed) })
	return c.Context.Done()
}

func TestConcurrentRoomEvictionsIgnoreStaleRefreshAndRotateNotificationGeneration(t *testing.T) {
	const userID = "11111111-1111-1111-1111-111111111111"
	const roomID = "22222222-2222-2222-2222-222222222222"

	refreshStarted := []chan struct{}{make(chan struct{}), make(chan struct{})}
	refreshResult := []chan bool{make(chan bool, 1), make(chan bool, 1)}
	var refreshCalls atomic.Int32
	auth := &controlledRoomMembershipAuth{
		canJoin: func(context.Context, string, string) bool { return true },
		refresh: func(context.Context, string, string) (bool, error) {
			index := int(refreshCalls.Add(1)) - 1
			if index >= len(refreshStarted) {
				return false, errors.New("unexpected extra authorization refresh")
			}
			close(refreshStarted[index])
			return <-refreshResult[index], nil
		},
	}
	h := newNatsTestHub(auth, "", 10)
	ctx, cancel := context.WithCancel(context.Background())
	client := &Client{
		ID: "overlapping-evictions", UserID: userID, Hub: h,
		Rooms: make(map[string]bool), Send: make(chan []byte, 2), ctx: ctx, cancel: cancel,
	}
	client.JoinRoom(roomID)

	firstLock := h.roomMembershipLock(userID, roomID)
	firstLock.Lock()
	firstGeneration := firstLock.entry.changedLocked()
	firstLock.unlockRetained()
	firstLockHeld := true

	var secondGenerationLock *roomMembershipLock
	secondGenerationHeld := false
	firstDone := make(chan error, 1)
	firstExited := make(chan struct{})
	secondDone := make(chan error, 1)
	secondExited := make(chan struct{})
	firstStarted := false
	secondStarted := false
	t.Cleanup(func() {
		cancel()
		select {
		case refreshResult[0] <- false:
		default:
		}
		select {
		case refreshResult[1] <- false:
		default:
		}
		if firstLockHeld {
			firstLock.release()
		}
		if secondGenerationHeld {
			secondGenerationLock.release()
		}
		if firstStarted {
			select {
			case <-firstExited:
			case <-time.After(2 * time.Second):
				t.Error("first eviction did not exit during cleanup")
			}
		}
		if secondStarted {
			select {
			case <-secondExited:
			case <-time.After(2 * time.Second):
				t.Error("second eviction did not exit during cleanup")
			}
		}
	})

	go func() {
		defer close(firstExited)
		firstDone <- h.evictRoomMembership(context.Background(), userID, roomID)
	}()
	firstStarted = true
	waitRoomMembershipSignal(t, refreshStarted[0], "first eviction did not start its authoritative refresh")
	waitRoomMembershipSignal(t, firstGeneration, "first eviction did not notify the prior admission generation")

	secondGenerationLock = h.roomMembershipLock(userID, roomID)
	secondGenerationLock.Lock()
	secondGeneration := secondGenerationLock.entry.changedLocked()
	secondGenerationLock.unlockRetained()
	secondGenerationHeld = true

	go func() {
		defer close(secondExited)
		secondDone <- h.evictRoomMembership(context.Background(), userID, roomID)
	}()
	secondStarted = true
	waitRoomMembershipSignal(t, refreshStarted[1], "overlapping eviction did not start its refresh")

	refreshResult[0] <- false
	select {
	case err := <-firstDone:
		require.NoError(t, err)
	case <-time.After(2 * time.Second):
		t.Fatal("stale first eviction did not finish")
	}
	require.True(t, client.isInRoom(roomID),
		"a stale denial must not remove membership after a newer eviction owns the epoch")
	select {
	case <-secondGeneration:
		t.Fatal("an older eviction must not signal the newer revocation generation")
	default:
	}

	refreshResult[1] <- true
	select {
	case err := <-secondDone:
		require.NoError(t, err)
	case <-time.After(2 * time.Second):
		t.Fatal("current eviction did not finish")
	}
	waitRoomMembershipSignal(t, secondGeneration, "current eviction did not notify its waiters")
	require.True(t, client.isInRoom(roomID), "the newest authoritative allow must retain local membership")
	require.False(t, h.isRoomRevocationPending(userID, roomID))
	require.EqualValues(t, 2, refreshCalls.Load())

	firstLock.release()
	firstLockHeld = false
	secondGenerationLock.release()
	secondGenerationHeld = false
	h.roomMembershipLocks.mu.Lock()
	remainingEntries := len(h.roomMembershipLocks.entries)
	h.roomMembershipLocks.mu.Unlock()
	require.Zero(t, remainingEntries, "completed overlapping operations must release the keyed registry entry")
}

func TestConcurrentEvictionHonorsContextWhilePriorRemovalIsPending(t *testing.T) {
	const userID = "11111111-1111-1111-1111-111111111111"
	const roomID = "22222222-2222-2222-2222-222222222222"

	refreshStarted := make(chan struct{})
	var refreshCalls atomic.Int32
	auth := &controlledRoomMembershipAuth{
		canJoin: func(context.Context, string, string) bool { return true },
		refresh: func(context.Context, string, string) (bool, error) {
			refreshCalls.Add(1)
			close(refreshStarted)
			return false, nil
		},
	}
	h := newNatsTestHub(auth, "", 10)
	ctx, cancel := context.WithCancel(context.Background())
	client := &Client{
		ID: "pending-removal", UserID: userID, Hub: h,
		Rooms: make(map[string]bool), Send: make(chan []byte, 2), ctx: ctx, cancel: cancel,
	}
	client.JoinRoom(roomID)
	client.mu.Lock()
	clientMuHeld := true

	firstDone := make(chan error, 1)
	firstExited := make(chan struct{})
	firstStarted := false
	secondDone := make(chan error, 1)
	secondExited := make(chan struct{})
	secondStarted := false
	secondBase, cancelSecond := context.WithCancel(context.Background())
	secondContext := &observedDoneContext{Context: secondBase, observed: make(chan struct{})}
	t.Cleanup(func() {
		cancel()
		cancelSecond()
		if clientMuHeld {
			client.mu.Unlock()
		}
		if firstStarted {
			select {
			case <-firstExited:
			case <-time.After(2 * time.Second):
				t.Error("blocked first eviction did not exit during cleanup")
			}
		}
		if secondStarted {
			select {
			case <-secondExited:
			case <-time.After(2 * time.Second):
				t.Error("cancelled overlapping eviction did not exit during cleanup")
			}
		}
	})

	go func() {
		defer close(firstExited)
		firstDone <- h.evictRoomMembership(context.Background(), userID, roomID)
	}()
	firstStarted = true
	waitRoomMembershipSignal(t, refreshStarted, "first eviction did not start refresh")
	require.Eventually(t, func() bool {
		lock := h.roomMembershipLock(userID, roomID)
		lock.Lock()
		pending := lock.entry.mutationPending
		lock.Unlock()
		return pending
	}, time.Second, time.Millisecond, "first eviction did not enter its local membership removal")

	secondStarted = true
	go func() {
		defer close(secondExited)
		secondDone <- h.evictRoomMembership(secondContext, userID, roomID)
	}()
	waitRoomMembershipSignal(t, secondContext.observed, "second eviction did not reach the pending-mutation wait")
	cancelSecond()
	select {
	case err := <-secondDone:
		require.ErrorIs(t, err, context.Canceled,
			"an overlapping eviction must honor its caller context while waiting for mutation completion")
	case <-time.After(2 * time.Second):
		t.Fatal("overlapping eviction ignored cancellation while membership removal was pending")
	}

	client.mu.Unlock()
	clientMuHeld = false
	select {
	case err := <-firstDone:
		require.NoError(t, err)
	case <-time.After(2 * time.Second):
		t.Fatal("first eviction did not finish after the blocked member lock was released")
	}
	require.False(t, client.isInRoom(roomID))
	require.False(t, h.isRoomRevocationPending(userID, roomID))
	require.EqualValues(t, 1, refreshCalls.Load(),
		"the cancelled overlapping eviction must not perform a second authorization refresh")
}

func TestRoomJoinStopsWhenClientContextIsCanceledBehindRevocation(t *testing.T) {
	const userID = "11111111-1111-1111-1111-111111111111"
	const roomID = "22222222-2222-2222-2222-222222222222"

	refreshStarted := make(chan struct{})
	refreshResult := make(chan bool, 1)
	var authorizationCalls atomic.Int32
	auth := &controlledRoomMembershipAuth{
		canJoin: func(context.Context, string, string) bool {
			authorizationCalls.Add(1)
			return true
		},
		refresh: func(context.Context, string, string) (bool, error) {
			close(refreshStarted)
			return <-refreshResult, nil
		},
	}
	h := newNatsTestHub(auth, "", 10)
	clientCtx, cancelClient := context.WithCancel(context.Background())
	client := &Client{
		ID: "cancelled-barrier-join", UserID: userID, Hub: h,
		Rooms: make(map[string]bool), Send: make(chan []byte, 2), ctx: clientCtx, cancel: cancelClient,
	}
	evictionDone := make(chan error, 1)
	evictionExited := make(chan struct{})
	evictionStarted := false
	joinDone := make(chan bool, 1)
	joinExited := make(chan struct{})
	joinStarted := false
	var commitCalled atomic.Bool

	t.Cleanup(func() {
		cancelClient()
		select {
		case refreshResult <- false:
		default:
		}
		if evictionStarted {
			select {
			case <-evictionExited:
			case <-time.After(2 * time.Second):
				t.Error("eviction did not exit during cleanup")
			}
		}
		if joinStarted {
			select {
			case <-joinExited:
			case <-time.After(2 * time.Second):
				t.Error("barrier-blocked join did not exit during cleanup")
			}
		}
	})

	go func() {
		defer close(evictionExited)
		evictionDone <- h.evictRoomMembership(context.Background(), userID, roomID)
	}()
	evictionStarted = true
	waitRoomMembershipSignal(t, refreshStarted, "revocation did not reach its authoritative refresh")

	joinLock := h.roomMembershipLock(userID, roomID)
	joinLock.Lock()
	joinLockLocked := true
	joinLockHeld := true
	t.Cleanup(func() {
		if joinLockLocked {
			joinLock.unlockRetained()
			joinLockLocked = false
		}
		if joinLockHeld {
			joinLock.release()
		}
	})
	joinStarted = true
	go func() {
		defer close(joinExited)
		joinDone <- client.authorizeRoomJoin(context.Background(), roomID, func() bool {
			commitCalled.Store(true)
			return true
		})
	}()
	require.Eventually(t, func() bool {
		h.roomMembershipLocks.mu.Lock()
		defer h.roomMembershipLocks.mu.Unlock()
		entry := h.roomMembershipLocks.entries[roomMembershipKey{userID: userID, roomID: roomID}]
		return entry != nil && entry.references >= 3
	}, time.Second, time.Millisecond, "join did not register behind the held revocation entry")

	joinLock.unlockRetained()
	joinLockLocked = false
	require.Eventually(t, func() bool {
		h.roomMembershipLocks.mu.Lock()
		defer h.roomMembershipLocks.mu.Unlock()
		entry := h.roomMembershipLocks.entries[roomMembershipKey{userID: userID, roomID: roomID}]
		return entry != nil && entry.references == 2
	}, time.Second, time.Millisecond, "join did not release its keyed reference before waiting")

	cancelClient()
	select {
	case allowed := <-joinDone:
		require.False(t, allowed, "a disconnected client cannot finish room authorization")
	case <-time.After(2 * time.Second):
		t.Fatal("room join did not honor client-context cancellation behind the barrier")
	}
	require.Zero(t, authorizationCalls.Load(), "backend authorization must not run through an active revocation barrier")
	require.False(t, commitCalled.Load(), "membership commit must not run after client cancellation")

	refreshResult <- false
	select {
	case err := <-evictionDone:
		require.NoError(t, err)
	case <-time.After(2 * time.Second):
		t.Fatal("revocation did not finish after refresh was released")
	}
	joinLock.release()
	joinLockHeld = false
	h.roomMembershipLocks.mu.Lock()
	remainingEntries := len(h.roomMembershipLocks.entries)
	h.roomMembershipLocks.mu.Unlock()
	require.Zero(t, remainingEntries, "cancelled join and completed eviction must reclaim their lock entry")
}

type replayCloseObservedSession struct {
	recordingSession
	closed chan struct{}
	once   sync.Once
}

func (s *replayCloseObservedSession) Close() error {
	s.once.Do(func() { close(s.closed) })
	return nil
}

func TestSupersededRoomReplayCannotCloseLiveClient(t *testing.T) {
	h := setupTestHub()
	h.js = &scriptedPullSubscription{pull: func(string, string, ...nats.SubOpt) (*nats.Subscription, error) {
		return &nats.Subscription{}, nil
	}}
	h.Unregister = make(chan *Client, 1)

	clientCtx, cancelClient := context.WithCancel(context.Background())
	session := &replayCloseObservedSession{closed: make(chan struct{})}
	client := &Client{
		ID: "replacement-replay", UserID: "replacement-replay-user", Hub: h,
		Rooms: make(map[string]bool), Send: make(chan []byte, 2), Conn: session,
		ctx: clientCtx, cancel: cancelClient, replays: make(map[string]*roomReplayState),
	}
	oldReplayCtx, cancelOldReplay := context.WithCancel(clientCtx)
	var replacement *roomReplayState
	var replacementCtx context.Context
	var cancelReplacement context.CancelFunc
	oldState := &roomReplayState{
		ctx: oldReplayCtx, cancel: cancelOldReplay, buffered: make(map[uint64][]byte),
	}
	client.replays["room"] = oldState
	fetchStarted := make(chan struct{})
	releaseFetch := make(chan struct{})
	var releaseOnce sync.Once
	originalFetch := fetchPullMessagesFunc
	originalUnsubscribe := unsubscribePullFunc
	t.Cleanup(func() {
		fetchPullMessagesFunc = originalFetch
		unsubscribePullFunc = originalUnsubscribe
	})
	fetchPullMessagesFunc = func(*nats.Subscription, int, ...nats.PullOpt) ([]*nats.Msg, error) {
		close(fetchStarted)
		<-releaseFetch
		return nil, errors.New("old replay fetch failed after replacement")
	}
	unsubscribePullFunc = func(*nats.Subscription) error { return nil }

	baseline := testutil.ToFloat64(ActiveGoroutines)
	workerStarted := false
	t.Cleanup(func() {
		releaseOnce.Do(func() { close(releaseFetch) })
		cancelOldReplay()
		if cancelReplacement != nil {
			cancelReplacement()
		}
		cancelClient()
		if workerStarted {
			require.Eventually(t, func() bool {
				return testutil.ToFloat64(ActiveGoroutines) == baseline
			}, 2*time.Second, time.Millisecond, "tracked replay worker did not exit during cleanup")
		}
	})

	client.runRoomReplay(clientCtx, "room", 7, "", oldState)
	workerStarted = true
	waitRoomMembershipSignal(t, fetchStarted, "old replay did not reach its blocked pull")
	replacementCtx, cancelReplacement = context.WithCancel(context.Background())
	replacement = &roomReplayState{ctx: replacementCtx, cancel: cancelReplacement, buffered: make(map[uint64][]byte)}
	client.replayMu.Lock()
	oldState.cancelReplay()
	client.replays["room"] = replacement
	client.replayMu.Unlock()
	releaseOnce.Do(func() { close(releaseFetch) })

	require.Eventually(t, func() bool {
		return testutil.ToFloat64(ActiveGoroutines) == baseline
	}, 2*time.Second, time.Millisecond, "superseded replay worker did not finish")
	workerStarted = false

	client.replayMu.Lock()
	current := client.replays["room"]
	client.replayMu.Unlock()
	require.Same(t, replacement, current, "stale replay completion must not remove the replacement state")
	require.NoError(t, clientCtx.Err(), "failure from an already-cancelled child replay must not revoke its live client")
	select {
	case <-session.closed:
		t.Fatal("stale child replay failure closed the replacement session")
	default:
	}
	select {
	case got := <-h.Unregister:
		t.Fatalf("stale child replay unexpectedly unregistered client %p", got)
	default:
	}

	cancelReplacement()
	cancelClient()
}

func TestSubscribeOfflineReplayWithoutJetStreamFailsClosed(t *testing.T) {
	testCases := []struct {
		name string
		hub  *Hub
	}{
		{name: "missing hub"},
		{name: "missing JetStream", hub: &Hub{}},
	}

	for _, testCase := range testCases {
		t.Run(testCase.name, func(t *testing.T) {
			client := &Client{Hub: testCase.hub}
			sub, subscribed := client.subscribeOfflineReplay(context.Background(), "room", 7, "")

			require.Nil(t, sub)
			require.False(t, subscribed)
		})
	}
}

func TestReplayOfflineMessagesUnsubscribesWhenCanceledBeforeFirstFetch(t *testing.T) {
	replayCtx, cancel := context.WithCancel(context.Background())
	t.Cleanup(cancel)

	subscription := &nats.Subscription{}
	var pullCalls, fetchCalls, unsubscribeCalls int
	h := &Hub{
		js: &scriptedPullSubscription{pull: func(subject, durable string, _ ...nats.SubOpt) (*nats.Subscription, error) {
			require.Equal(t, "chat.room", subject)
			require.Empty(t, durable)
			pullCalls++
			cancel()
			return subscription, nil
		}},
	}
	client := &Client{Hub: h}

	originalFetch := fetchPullMessagesFunc
	originalUnsubscribe := unsubscribePullFunc
	t.Cleanup(func() {
		fetchPullMessagesFunc = originalFetch
		unsubscribePullFunc = originalUnsubscribe
	})
	fetchPullMessagesFunc = func(*nats.Subscription, int, ...nats.PullOpt) ([]*nats.Msg, error) {
		fetchCalls++
		return nil, nil
	}
	unsubscribePullFunc = func(got *nats.Subscription) error {
		require.Same(t, subscription, got)
		unsubscribeCalls++
		return nil
	}

	maxSequence, completed := client.replayOfflineMessagesContext(replayCtx, "room", 7, "")

	require.Equal(t, uint64(7), maxSequence)
	require.False(t, completed, "cancellation after subscription must stop replay")
	require.Equal(t, 1, pullCalls, "replay must establish then release its pull subscription")
	require.Zero(t, fetchCalls, "canceled replay must not fetch messages")
	require.Equal(t, 1, unsubscribeCalls, "the established subscription must be released")
	require.ErrorIs(t, replayCtx.Err(), context.Canceled)
}

func TestReplayOfflineMessagesStopsAtLoopBoundaryAfterSuccessfulBatch(t *testing.T) {
	callerCtx, cancelCaller := context.WithCancel(context.Background())
	t.Cleanup(cancelCaller)
	replayCtx, cancelReplay := context.WithCancel(callerCtx)
	t.Cleanup(cancelReplay)

	h := setupTestHub()
	enableSecureReplayForTest(h)
	subscription := &nats.Subscription{}
	var pullCalls, fetchCalls, ackCalls, unsubscribeCalls int
	h.js = &scriptedPullSubscription{pull: func(subject, durable string, _ ...nats.SubOpt) (*nats.Subscription, error) {
		require.Equal(t, "chat.room", subject)
		require.Empty(t, durable)
		pullCalls++
		return subscription, nil
	}}
	client := &Client{UserID: "replay-user", Hub: h, ctx: replayCtx, Send: make(chan []byte, 1)}

	originalFetch := fetchPullMessagesFunc
	originalAck := ackOfflineMessageFunc
	originalUnsubscribe := unsubscribePullFunc
	t.Cleanup(func() {
		fetchPullMessagesFunc = originalFetch
		ackOfflineMessageFunc = originalAck
		unsubscribePullFunc = originalUnsubscribe
	})
	fetchPullMessagesFunc = func(_ *nats.Subscription, batch int, _ ...nats.PullOpt) ([]*nats.Msg, error) {
		require.Equal(t, offlineReplayBatchSize, batch)
		fetchCalls++
		return []*nats.Msg{replayMessage(8)}, nil
	}
	ackOfflineMessageFunc = func(msg *nats.Msg) error {
		require.Equal(t, "chat.room", msg.Subject)
		ackCalls++
		cancelReplay()
		return nil
	}
	unsubscribePullFunc = func(got *nats.Subscription) error {
		require.Same(t, subscription, got)
		unsubscribeCalls++
		return nil
	}

	maxSequence, completed := client.replayOfflineMessagesContext(replayCtx, "room", 7, "")

	require.Equal(t, uint64(8), maxSequence)
	require.False(t, completed, "cancellation after a successful batch must stop the next fetch")
	require.Equal(t, 1, pullCalls)
	require.Equal(t, 1, fetchCalls)
	require.Equal(t, 1, ackCalls)
	require.Equal(t, 1, unsubscribeCalls, "the established subscription must be released")
	require.NoError(t, callerCtx.Err(), "state replay cancellation must not cancel the caller")
	require.ErrorIs(t, replayCtx.Err(), context.Canceled)
	require.Len(t, client.Send, 1, "successful replay delivery must be queued")
	queued := <-client.Send
	var replayed map[string]any
	require.NoError(t, json.Unmarshal(queued, &replayed))
	require.Equal(t, float64(8), replayed["seq"])
}
