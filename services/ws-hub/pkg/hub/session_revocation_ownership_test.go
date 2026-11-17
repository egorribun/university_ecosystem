package hub

import (
	"context"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"github.com/alicebob/miniredis/v2"
	goredis "github.com/redis/go-redis/v9"
	"github.com/stretchr/testify/require"
)

func TestRevocationStopPublicationRejectsSupersededBootstrap(t *testing.T) {
	server := miniredis.RunT(t)
	client := goredis.NewClient(&goredis.Options{Addr: server.Addr()})
	t.Cleanup(func() { require.NoError(t, client.Close()) })
	h := mustNewTestHub(t, nil, newTestLogger(), nil, nil, nil, client)
	ctx, cancel := context.WithCancel(context.Background())
	t.Cleanup(func() {
		cancel()
		h.Stop()
	})
	require.NoError(t, h.StartSessionRevocationListener(ctx))
	h.lifecycleMu.Lock()
	oldGeneration := h.sessionRevocationGeneration
	h.lifecycleMu.Unlock()

	validated := make(chan struct{})
	resume := make(chan struct{})
	var resumeOnce sync.Once
	release := func() { resumeOnce.Do(func() { close(resume) }) }
	t.Cleanup(release)
	published := make(chan bool, 1)
	var staleCalled atomic.Bool
	// Hold the old startup precisely after its successful pre-publication
	// validation, without timing sleeps or changing the production scheduler.
	go func() {
		h.lifecycleMu.Lock()
		validationErr := h.sessionRevocationBootstrapErrorLocked(oldGeneration, nil, ctx)
		h.lifecycleMu.Unlock()
		if validationErr != nil {
			published <- true
			close(validated)
			return
		}
		close(validated)
		<-resume
		published <- h.installSessionRevocationStop(oldGeneration, nil, ctx, func() { staleCalled.Store(true) }) == nil
	}()
	select {
	case <-validated:
	case <-time.After(time.Second):
		t.Fatal("old bootstrap did not reach publication barrier")
	}
	// A complete real replacement subscribes before the stale startup resumes.
	replacementErr := h.StartSessionRevocationListener(ctx)
	release()
	require.NoError(t, replacementErr)
	select {
	case accepted := <-published:
		require.False(t, accepted, "old startup must not overwrite the replacement's closer")
	case <-time.After(time.Second):
		t.Fatal("old publication did not return")
	}

	stopped := make(chan struct{})
	go func() {
		h.Stop()
		close(stopped)
	}()
	select {
	case <-stopped:
	case <-time.After(time.Second):
		cancel()
		t.Fatal("Stop lost ownership of the active replacement")
	}
	require.False(t, staleCalled.Load())
	// The server releases a closed subscriber connection asynchronously.
	require.Eventually(t, func() bool {
		return server.PubSubNumSub(sessionRevocationsChannel)[sessionRevocationsChannel] == 0
	}, time.Second, 10*time.Millisecond)
}

func TestRevocationStopPublicationKeepsExistingOwnerOnRejection(t *testing.T) {
	for _, testCase := range []string{"stopped", "superseded", "cancelled"} {
		t.Run(testCase, func(t *testing.T) {
			h := setupTestHub()
			t.Cleanup(h.Stop)
			ctx, cancel := context.WithCancel(context.Background())
			defer cancel()
			h.sessionRevocationGeneration = 3
			ownerCalled := false
			staleCalled := false
			h.sessionRevocationCancel = func() { ownerCalled = true }
			switch testCase {
			case "stopped":
				h.stopped.Store(true)
			case "superseded":
				h.sessionRevocationGeneration = 4
			case "cancelled":
				cancel()
			}
			require.Error(t, h.installSessionRevocationStop(3, nil, ctx, func() { staleCalled = true }))
			h.sessionRevocationCancel()
			require.True(t, ownerCalled)
			require.False(t, staleCalled)
		})
	}
}

func TestRevocationStopPublicationInstallsCurrentOwner(t *testing.T) {
	h := setupTestHub()
	t.Cleanup(h.Stop)
	h.sessionRevocationGeneration = 7
	called := false
	require.NoError(t, h.installSessionRevocationStop(7, nil, context.Background(), func() { called = true }))
	h.Stop()
	require.True(t, called)
}
