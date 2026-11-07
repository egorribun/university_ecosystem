package hub

import (
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"github.com/redis/go-redis/v9"
	"github.com/stretchr/testify/require"
)

// aud478BackendAnswer serves the participant check with a fixed status and counts calls.
func aud478BackendAnswer(t *testing.T, status int) (*httptest.Server, *atomic.Int32) {
	t.Helper()
	var calls atomic.Int32
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		calls.Add(1)
		w.WriteHeader(status)
	}))
	t.Cleanup(server.Close)
	return server, &calls
}

// TestAUD478ResetDropsEveryGenerationOfLocalAndSharedCache is the reset contract: after
// a reset no L1 or L2 entry from before it can answer, including entries for other
// users, and the next join is decided by the backend.
func TestAUD478ResetDropsEveryGenerationOfLocalAndSharedCache(t *testing.T) {
	mr, rc := newMiniredisClient(t)
	server, calls := aud478BackendAnswer(t, http.StatusOK)
	c := mustNewTestAuthClient(t, server.URL, "", rc)
	ctx := context.Background()

	require.True(t, c.CanJoinRoom(ctx, rdUser, rdRoom))
	require.Equal(t, int32(1), calls.Load())
	const otherUser = "44444444-4444-4444-4444-444444444444"
	require.NoError(t, mr.Set("auth:perms:"+otherUser+":"+rdRoom2, "0"))

	require.NoError(t, c.ResetAuthorizationCache(ctx))
	require.Zero(t, c.cache.Len(), "every L1 entry must be dropped")
	require.False(t, mr.Exists("auth:perms:"+rdUser+":"+rdRoom), "the shared entry for the joining user must be removed")
	require.False(t, mr.Exists("auth:perms:"+otherUser+":"+rdRoom2), "shared entries for every user must be removed")

	require.True(t, c.CanJoinRoom(ctx, rdUser, rdRoom))
	require.Equal(t, int32(2), calls.Load(), "the first join after a reset must reach the backend")
}

// TestAUD478InFlightAnswerFromRetiredGenerationIsNotCached covers a backend check that
// started before a reset and completes after it. The retired answer must neither
// authorize the caller nor populate L1 or L2 for the new generation.
func TestAUD478InFlightAnswerFromRetiredGenerationIsNotCached(t *testing.T) {
	mr, rc := newMiniredisClient(t)
	started := make(chan struct{})
	release := make(chan struct{})
	var calls atomic.Int32
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		if calls.Add(1) == 1 {
			close(started)
			<-release
		}
		w.WriteHeader(http.StatusOK)
	}))
	t.Cleanup(server.Close)
	c := mustNewTestAuthClient(t, server.URL, "", rc)
	ctx := context.Background()

	done := make(chan bool, 1)
	go func() { done <- c.CanJoinRoom(ctx, rdUser, rdRoom) }()
	<-started
	require.NoError(t, c.ResetAuthorizationCache(ctx), "a reset must not wait for an unrelated in-flight backend call")
	close(release)

	select {
	case allowed := <-done:
		require.False(t, allowed, "the caller must not receive an allow from a retired generation")
	case <-time.After(5 * time.Second):
		require.FailNow(t, "in-flight join did not complete")
	}
	_, cached := c.cache.Get(rdUser + ":" + rdRoom)
	require.False(t, cached, "an answer from a retired generation must not enter L1")
	require.False(t, mr.Exists("auth:perms:"+rdUser+":"+rdRoom), "an answer from a retired generation must not enter L2")

	require.True(t, c.CanJoinRoom(ctx, rdUser, rdRoom))
	require.Equal(t, int32(2), calls.Load(), "the next join must ask the backend, not the retired generation")
}

func TestAUD478ResetAllowsNewFlightWhileOldFlightIsPending(t *testing.T) {
	oldStarted, newStarted := make(chan struct{}), make(chan struct{})
	oldRelease, newRelease := make(chan struct{}), make(chan struct{})
	var oldOnce, newOnce sync.Once
	var calls atomic.Int32
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch calls.Add(1) {
		case 1:
			close(oldStarted)
			select {
			case <-oldRelease:
			case <-r.Context().Done():
				return
			}
			w.WriteHeader(http.StatusOK)
		case 2:
			close(newStarted)
			select {
			case <-newRelease:
			case <-r.Context().Done():
				return
			}
			w.WriteHeader(http.StatusForbidden)
		default:
			t.Error("a current-generation waiter created an extra backend request")
			w.WriteHeader(http.StatusForbidden)
		}
	}))
	t.Cleanup(server.Close)
	t.Cleanup(func() {
		oldOnce.Do(func() { close(oldRelease) })
		newOnce.Do(func() { close(newRelease) })
	})
	client := mustNewTestAuthClient(t, server.URL, "", nil)
	oldDone := make(chan bool, 1)
	go func() { oldDone <- client.CanJoinRoom(context.Background(), rdUser, rdRoom) }()
	waitRoomMembershipSignal(t, oldStarted, "old flight did not start")
	require.NoError(t, client.ResetAuthorizationCache(context.Background()))
	newDone := make(chan bool, 1)
	go func() { newDone <- client.CanJoinRoom(context.Background(), rdUser, rdRoom) }()
	waitRoomMembershipSignal(t, newStarted, "post-reset authorization joined the retired flight")
	require.EqualValues(t, 2, calls.Load())
	client.callMu.Lock()
	currentFlight := client.calls[rdUser+":"+rdRoom]
	client.callMu.Unlock()
	require.NotNil(t, currentFlight)
	oldOnce.Do(func() { close(oldRelease) })
	require.False(t, <-oldDone, "the retired flight must not authorize its original caller")
	client.callMu.Lock()
	retainedFlight := client.calls[rdUser+":"+rdRoom]
	client.callMu.Unlock()
	require.Same(t, currentFlight, retainedFlight, "retiring the old flight must not remove the new one")

	observed := &observedDoneContext{Context: context.Background(), observed: make(chan struct{})}
	waiterDone := make(chan bool, 1)
	go func() { waiterDone <- client.CanJoinRoom(observed, rdUser, rdRoom) }()
	waitRoomMembershipSignal(t, observed.observed, "current-generation waiter did not attach")
	newOnce.Do(func() { close(newRelease) })
	require.False(t, <-newDone, "the new flight must use the current backend denial")
	require.False(t, <-waiterDone)
	require.EqualValues(t, 2, calls.Load())
}

func TestAUD478SingleFlightWaiterHonorsCancellation(t *testing.T) {
	started := make(chan struct{})
	release := make(chan struct{})
	var releaseOnce sync.Once
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		close(started)
		select {
		case <-release:
		case <-r.Context().Done():
			return
		}
		w.WriteHeader(http.StatusOK)
	}))
	t.Cleanup(server.Close)
	t.Cleanup(func() { releaseOnce.Do(func() { close(release) }) })
	client := mustNewTestAuthClient(t, server.URL, "", nil)
	leaderDone := make(chan bool, 1)
	go func() { leaderDone <- client.CanJoinRoom(context.Background(), rdUser, rdRoom) }()
	waitRoomMembershipSignal(t, started, "leader did not start")
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	observed := &observedDoneContext{Context: ctx, observed: make(chan struct{})}
	waiterDone := make(chan bool, 1)
	go func() { waiterDone <- client.CanJoinRoom(observed, rdUser, rdRoom) }()
	select {
	case <-observed.observed:
	case <-time.After(time.Second):
		t.Fatal("waiter did not observe its cancellation context")
	}
	cancel()
	select {
	case allowed := <-waiterDone:
		require.False(t, allowed)
	case <-time.After(time.Second):
		t.Fatal("cancelled waiter remained blocked on the leader")
	}
	releaseOnce.Do(func() { close(release) })
	require.True(t, <-leaderDone, "a cancelled waiter must not cancel the leader")
}

func TestAUD478RetiredLookupCannotReplaceCurrentFlight(t *testing.T) {
	currentStarted, staleStarted := make(chan struct{}), make(chan struct{})
	release := make(chan struct{})
	var releaseOnce sync.Once
	var calls atomic.Int32
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if calls.Add(1) == 1 {
			close(currentStarted)
		} else {
			close(staleStarted)
		}
		select {
		case <-release:
		case <-r.Context().Done():
			return
		}
		w.WriteHeader(http.StatusOK)
	}))
	t.Cleanup(server.Close)
	t.Cleanup(func() { releaseOnce.Do(func() { close(release) }) })
	client := mustNewTestAuthClient(t, server.URL, "", nil)
	require.NoError(t, client.ResetAuthorizationCache(context.Background()))
	currentDone := make(chan bool, 1)
	go func() { currentDone <- client.CanJoinRoom(context.Background(), rdUser, rdRoom) }()
	waitRoomMembershipSignal(t, currentStarted, "current-generation flight did not start")
	client.callMu.Lock()
	currentFlight := client.calls[rdUser+":"+rdRoom]
	client.callMu.Unlock()
	require.NotNil(t, currentFlight)

	// Model a caller that completed the cache lookup before reset but was
	// delayed before entering the single-flight map.
	retiredDone := make(chan bool, 1)
	go func() {
		retiredDone <- client.requestRoomAuthorization(context.Background(), rdUser, rdRoom, rdUser+":"+rdRoom, 0)
	}()
	select {
	case allowed := <-retiredDone:
		require.False(t, allowed)
	case <-staleStarted:
		t.Fatal("retired lookup started a backend request and replaced the current flight")
	case <-time.After(time.Second):
		t.Fatal("retired lookup did not fail closed")
	}
	client.callMu.Lock()
	retainedFlight := client.calls[rdUser+":"+rdRoom]
	client.callMu.Unlock()
	require.Same(t, currentFlight, retainedFlight)
	require.EqualValues(t, 1, calls.Load())
	releaseOnce.Do(func() { close(release) })
	require.True(t, <-currentDone)
}

// TestAUD478StaleGenerationEntryIsNeverServed checks the read side: an L1 entry tagged
// with another generation is treated as a miss even while its TTL is still live.
func TestAUD478StaleGenerationEntryIsNeverServed(t *testing.T) {
	cases := []struct {
		name       string
		entryGen   uint64
		wantCalled bool
	}{
		{name: "current generation is served from L1", entryGen: 0, wantCalled: false},
		{name: "retired generation is ignored", entryGen: 7, wantCalled: true},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			server, calls := aud478BackendAnswer(t, http.StatusForbidden)
			c := mustNewTestAuthClient(t, server.URL, "", nil)
			c.cache.Add(rdUser+":"+rdRoom, cacheEntry{
				allowed:    true,
				expiresAt:  time.Now().Add(authCacheTTL),
				generation: tc.entryGen,
			})

			allowed := c.CanJoinRoom(context.Background(), rdUser, rdRoom)
			if tc.wantCalled {
				require.False(t, allowed, "the backend denies, so the stale allow must not be served")
				require.Equal(t, int32(1), calls.Load())
				return
			}
			require.True(t, allowed)
			require.Zero(t, calls.Load())
		})
	}
}

// TestAUD478ResetFailureIsReturnedToTheBarrier checks that a failed shared-cache purge is
// reported, so the admission barrier stays closed rather than treating the reset as done.
func TestAUD478ResetFailureIsReturnedToTheBarrier(t *testing.T) {
	_, rc := newMiniredisClient(t)
	server, _ := aud478BackendAnswer(t, http.StatusOK)
	c := mustNewTestAuthClient(t, server.URL, "", rc)
	require.NoError(t, rc.Close())

	err := c.ResetAuthorizationCache(context.Background())
	require.Error(t, err, "a purge that cannot reach the shared cache must fail")
}

// TestAUD478ResetWithoutSharedCacheOnlyPurgesLocalState covers a replica with no Redis
// L2: the reset still drops L1 and succeeds.
func TestAUD478ResetWithoutSharedCacheOnlyPurgesLocalState(t *testing.T) {
	server, _ := aud478BackendAnswer(t, http.StatusOK)
	c := mustNewTestAuthClient(t, server.URL, "", nil)
	c.cache.Add(rdUser+":"+rdRoom, cacheEntry{allowed: true, expiresAt: time.Now().Add(authCacheTTL)})

	require.NoError(t, c.ResetAuthorizationCache(context.Background()))
	require.Zero(t, c.cache.Len())
}

// delFailureHook makes every DEL fail while leaving SCAN and the other commands intact,
// so a reset can find shared entries and then fail to remove them.
type delFailureHook struct{}

func (delFailureHook) DialHook(next redis.DialHook) redis.DialHook { return next }

func (delFailureHook) ProcessHook(next redis.ProcessHook) redis.ProcessHook {
	return func(ctx context.Context, cmd redis.Cmder) error {
		if cmd.Name() == "del" {
			cmd.SetErr(errors.New("synthetic DEL failure"))
			return cmd.Err()
		}
		return next(ctx, cmd)
	}
}

func (delFailureHook) ProcessPipelineHook(next redis.ProcessPipelineHook) redis.ProcessPipelineHook {
	return next
}

// TestAUD478ResetReportsAFailedSharedEntryRemoval covers a shared entry that cannot be
// removed. The reset reports the failure, so the barrier stays closed.
func TestAUD478ResetReportsAFailedSharedEntryRemoval(t *testing.T) {
	mr, _ := newMiniredisClient(t)
	rc := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	t.Cleanup(func() { _ = rc.Close() }) //nolint:errcheck // best-effort cleanup
	rc.AddHook(delFailureHook{})
	require.NoError(t, mr.Set("auth:perms:"+rdUser+":"+rdRoom, "1"))
	server, _ := aud478BackendAnswer(t, http.StatusOK)
	c := mustNewTestAuthClient(t, server.URL, "", rc)

	err := c.ResetAuthorizationCache(context.Background())
	require.ErrorContains(t, err, "delete shared authorization cache entry")
}
