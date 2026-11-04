package hub

import (
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
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
// started before a reset and completes after it. The caller still gets that answer, but
// it must not populate L1 or L2 for the new generation.
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
		require.True(t, allowed, "the caller receives the answer it asked for")
	case <-time.After(5 * time.Second):
		require.FailNow(t, "in-flight join did not complete")
	}
	_, cached := c.cache.Get(rdUser + ":" + rdRoom)
	require.False(t, cached, "an answer from a retired generation must not enter L1")
	require.False(t, mr.Exists("auth:perms:"+rdUser+":"+rdRoom), "an answer from a retired generation must not enter L2")

	require.True(t, c.CanJoinRoom(ctx, rdUser, rdRoom))
	require.Equal(t, int32(2), calls.Load(), "the next join must ask the backend, not the retired generation")
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
