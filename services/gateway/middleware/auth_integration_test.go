//go:build integration

package middleware

import (
	"context"
	"fmt"
	"testing"
	"time"

	"github.com/prometheus/client_golang/prometheus/testutil"
	"github.com/redis/go-redis/v9"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"github.com/testcontainers/testcontainers-go"
	tclog "github.com/testcontainers/testcontainers-go/log"
	tcredis "github.com/testcontainers/testcontainers-go/modules/redis"
)

// startRedisContainerForAuth spins up a real redis:7-alpine container for
// auth-middleware integration tests. Mirrors the helper used in
// ratelimit_integration_test.go, kept separate (per ADR-022 §"ownership stays
// with service code") rather than promoted to a shared package.
func startRedisContainerForAuth(t *testing.T) *redis.Client {
	t.Helper()
	ctx := context.Background()

	rc, err := tcredis.Run(ctx, "redis:7.4.2-alpine",
		testcontainers.WithLogger(tclog.TestLogger(t)),
	)
	require.NoError(t, err)
	t.Cleanup(func() {
		_ = rc.Terminate(context.Background()) //nolint:errcheck // best-effort cleanup
	})

	connStr, err := rc.ConnectionString(ctx)
	require.NoError(t, err)
	opts, err := redis.ParseURL(connStr)
	require.NoError(t, err)
	client := redis.NewClient(opts)
	t.Cleanup(func() {
		_ = client.Close() //nolint:errcheck // best-effort cleanup
	})
	return client
}

// TestIntegration_L1CacheXFetchProbabilisticRefresh verifies the wiring of
// the XFetch probabilistic refresh path (PERF-31-02) end-to-end:
//
//	verifySession (auth.go:512) → checkL1Cache (auth.go:467) →
//	  shouldRefreshProbabilistic (auth.go:450) → l1ProbRefreshes.Inc → forced miss
//	  → checkSessionInRedis → cache write with storedAt = time.Now() (auth.go:502)
//
// This integration tier complements TestShouldRefreshProbabilistic_BoundaryAndStatistical
// (in auth_test.go), which verifies the math directly. Here we verify:
//   - cacheEntry.storedAt is populated correctly from time.Now() in
//     checkSessionInRedis (auth.go:502)
//   - checkL1Cache invokes shouldRefreshProbabilistic on the real LRU's stored
//     entry
//   - the metric l1ProbRefreshes increments through the real call chain
//
// Uses an L1 TTL of 500ms (large enough that Windows/Docker timing jitter is
// a small fraction of the remaining-time budget). After 400ms of sleep (80% of
// TTL elapsed → 100ms remaining), the per-session refresh probability is
// e^-0.2 ≈ 81.9%; over 100 sessions we expect ~82, with 99.7%-confidence
// range ~70-94 by Wald approximation.
//
// Original 200ms TTL + 150ms sleep flaked once across 5 runs (delta=96 > 95)
// because Windows/Docker jitter pushed actual remaining time as low as ~8ms,
// at which point e^(-8/200) ≈ 96%. Wider TTL window damps the jitter.
//
// Bounds (30 < delta <= 100): catches wiring breakage (delta=0 or near 0
// would mean shouldRefreshProbabilistic never fired), accommodates the
// upper-jitter tail (delta near 100 means most entries near-expired), still
// asserts non-trivial probabilistic behavior. The exact statistical math
// is verified by TestShouldRefreshProbabilistic_BoundaryAndStatistical.
func TestIntegration_L1CacheXFetchProbabilisticRefresh(t *testing.T) {
	rdb := startRedisContainerForAuth(t)

	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	t.Cleanup(cancel)

	const (
		sessionCount = 100
		l1TTL        = 500 * time.Millisecond
		sleepDur     = 400 * time.Millisecond // 80% of l1TTL elapsed → remaining=100ms
	)

	// Build JWTMiddleware with short L1 TTL via NewJWTMiddlewareWithConfig
	// (the production constructor at auth.go:124). MaxSize > sessionCount so
	// no LRU evictions during this test.
	m := NewJWTMiddlewareWithConfig(
		"test-secret",
		"", // no RSA public key for this test
		rdb,
		L1CacheConfig{MaxSize: sessionCount * 10, TTL: l1TTL},
	)

	// Pre-populate Redis with `sessionCount` revoked-JTI entries. The
	// production Redis key format (auth.go:528) is `revoked:jti:{jti}`.
	// We seed each with a long TTL so they stay alive across the L1 dance.
	for i := 0; i < sessionCount; i++ {
		key := fmt.Sprintf("revoked:jti:test-%d", i)
		require.NoError(t, rdb.Set(ctx, key, "1", 30*time.Second).Err())
	}

	// Capture metric counters at baseline.
	beforeRefreshes := testutil.ToFloat64(l1ProbRefreshes)
	beforeMisses := testutil.ToFloat64(l1Misses)

	// Round 1: warm the L1 cache. Each verifySession call:
	//   - checkL1Cache: empty initially → miss → l1Misses++
	//   - checkSessionInRedis: fetch from Redis → cache write with storedAt
	//     = time.Now()
	for i := 0; i < sessionCount; i++ {
		_, _, err := m.verifySession(ctx, fmt.Sprintf("test-%d", i), true)
		require.NoError(t, err, "Round 1 verifySession[%d] must not error", i)
	}

	round1Misses := testutil.ToFloat64(l1Misses) - beforeMisses
	require.Equal(t, float64(sessionCount), round1Misses,
		"Round 1 must populate L1 cache with %d misses, got %.0f", sessionCount, round1Misses)

	// Wait until ~75% of TTL elapsed.
	time.Sleep(sleepDur)

	// Round 2: same sessions, different cache state. checkL1Cache finds the
	// entry, calls shouldRefreshProbabilistic, and probabilistically returns
	// "miss" (forcing a Redis re-check + l1ProbRefreshes++). Per math:
	//   refresh probability = e^(-remaining/ttl) = e^(-100/500) ≈ 81.9%
	// Expect ~82 of 100 trials to refresh. Bounds 30 < delta <= 100 are
	// loose enough to absorb timing jitter while still catching wiring
	// regressions (delta near 0 would mean the XFetch path never fired).
	for i := 0; i < sessionCount; i++ {
		_, _, _ = m.verifySession(ctx, fmt.Sprintf("test-%d", i), true) //nolint:errcheck // probabilistic counter is the assertion
	}

	delta := int(testutil.ToFloat64(l1ProbRefreshes) - beforeRefreshes)
	require.Greater(t, delta, 30,
		"expected >30 probabilistic refreshes near expiry (math says ~82), got %d — XFetch wiring may be broken", delta)
	require.LessOrEqual(t, delta, sessionCount,
		"refresh count cannot exceed sessionCount=%d, got %d (counter regression?)", sessionCount, delta)
}

func TestIntegration_WarmL1Cache(t *testing.T) {
	rdb := startRedisContainerForAuth(t)

	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	t.Cleanup(cancel)

	m := NewJWTMiddleware("test-secret", rdb)

	// Set revoked keys in Redis
	require.NoError(t, rdb.Set(ctx, "revoked:jti:jti-warm-1", "1", 30*time.Second).Err())
	require.NoError(t, rdb.Set(ctx, "revoked:jti:jti-warm-2", "1", 30*time.Second).Err())

	// L1 Cache should be empty initially
	_, ok1 := m.l1cache.Get("revoked:jti:jti-warm-1")
	_, ok2 := m.l1cache.Get("revoked:jti:jti-warm-2")
	require.False(t, ok1)
	require.False(t, ok2)

	// Warm cache
	m.WarmL1Cache(ctx)

	// Now keys should be present in L1 Cache
	val1, ok1 := m.l1cache.Get("revoked:jti:jti-warm-1")
	val2, ok2 := m.l1cache.Get("revoked:jti:jti-warm-2")
	require.True(t, ok1)
	require.True(t, ok2)
	assert.True(t, val1.exists)
	assert.True(t, val2.exists)
}

func TestIntegration_ListenForRevocations(t *testing.T) {
	rdb := startRedisContainerForAuth(t)

	ctx, cancel := context.WithCancel(context.Background())
	t.Cleanup(cancel)

	m := NewJWTMiddleware("test-secret", rdb)

	// Start listener
	m.ListenForRevocations(ctx)

	// Wait a tiny bit for the connection to establish
	time.Sleep(100 * time.Millisecond)

	// Manually add key to L1 cache
	key := "revoked:jti:jti-pubsub-test"
	m.l1cache.Add(key, cacheEntry{exists: true, storedAt: time.Now()})

	// Verify key exists in L1 cache
	_, ok := m.l1cache.Get(key)
	require.True(t, ok)

	// Publish revocation message
	require.NoError(t, rdb.Publish(ctx, "session:revocations", "jti-pubsub-test").Err())

	// Wait for pubsub delivery
	time.Sleep(150 * time.Millisecond)

	// Verify key is evicted from L1 cache
	_, ok = m.l1cache.Get(key)
	assert.False(t, ok, "key should be evicted from L1 cache on revocation publication")
}

