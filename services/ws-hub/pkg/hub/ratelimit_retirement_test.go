package hub

import (
	"sync"
	"testing"
	"time"

	"github.com/stretchr/testify/require"
)

func TestUpgradeGCDoesNotRetireRefreshedBucket(t *testing.T) {
	limiter := &WSUpgradeRateLimiter{capacity: 2, ratePerSec: 0, idleTimeout: time.Minute}
	old := &wsUpgradeBucket{tokens: 2, lastRefr: time.Now().Add(-time.Hour)}
	limiter.buckets.Store("client", old)
	sweepTime := time.Now()
	// An admission wins before the sweep obtains the bucket lock.
	require.True(t, limiter.Allow("client"))
	limiter.expireBucket("client", old, sweepTime)
	current, ok := limiter.buckets.Load("client")
	require.True(t, ok)
	require.Same(t, old, current)
	require.True(t, limiter.Allow("client"))
	require.False(t, limiter.Allow("client"), "GC must not recreate the consumed budget")
}

func TestUpgradeAdmissionRetriesBucketRetiredAfterLookup(t *testing.T) {
	limiter := &WSUpgradeRateLimiter{capacity: 2, ratePerSec: 0, idleTimeout: time.Minute}
	old := &wsUpgradeBucket{tokens: 2, lastRefr: time.Now().Add(-time.Hour)}
	limiter.buckets.Store("client", old)
	loaded := limiter.bucketFor("client")
	retired := make(chan struct{})
	go func() {
		limiter.expireBucket("client", old, time.Now())
		close(retired)
	}()
	select {
	case <-retired:
	case <-time.After(5 * time.Second):
		t.Fatal("retirement did not finish")
	}
	// This is the production continuation after LoadOrStore. The old pointer
	// must not authorize from a separate, orphaned token budget.
	require.True(t, limiter.Allow("client"))
	require.True(t, limiter.allowFromBucket("client", loaded))
	require.False(t, limiter.Allow("client"))
	require.Equal(t, float64(2), old.tokens)
	require.True(t, old.retired)
	allowed, stale := old.allowCurrent(2, 0)
	require.False(t, allowed)
	require.True(t, stale)
}

func TestUpgradeStaleSweepPreservesReplacement(t *testing.T) {
	limiter := &WSUpgradeRateLimiter{capacity: 1, ratePerSec: 0, idleTimeout: time.Minute}
	old := &wsUpgradeBucket{tokens: 1, lastRefr: time.Now().Add(-time.Hour)}
	replacement := &wsUpgradeBucket{tokens: 0, lastRefr: time.Now()}
	limiter.buckets.Store("client", replacement)
	limiter.expireBucket("client", old, time.Now())
	current, ok := limiter.buckets.Load("client")
	require.True(t, ok)
	require.Same(t, replacement, current)
	require.False(t, limiter.Allow("client"))
	require.True(t, limiter.Allow("unrelated"))
}

func TestUpgradeConcurrentRetirementAndAdmissionKeepOneBudget(t *testing.T) {
	limiter := &WSUpgradeRateLimiter{capacity: 8, ratePerSec: 0, idleTimeout: time.Minute}
	old := &wsUpgradeBucket{tokens: 8, lastRefr: time.Now().Add(-time.Hour)}
	limiter.buckets.Store("client", old)
	sweepTime := time.Now()
	start := make(chan struct{})
	results := make(chan bool, 32)
	var workers sync.WaitGroup
	workers.Add(33)
	go func() {
		defer workers.Done()
		<-start
		limiter.expireBucket("client", old, sweepTime)
	}()
	for range 32 {
		go func() {
			defer workers.Done()
			<-start
			results <- limiter.Allow("client")
		}()
	}
	close(start)
	workers.Wait()
	close(results)
	allowed := 0
	for result := range results {
		if result {
			allowed++
		}
	}
	require.Equal(t, 8, allowed)
	require.False(t, limiter.Allow("client"))
}
