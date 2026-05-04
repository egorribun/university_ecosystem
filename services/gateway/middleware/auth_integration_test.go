//go:build integration

package middleware

import (
	"context"
	"fmt"
	"testing"
	"time"

	"github.com/prometheus/client_golang/prometheus/testutil"
	"github.com/redis/go-redis/v9"
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

	rc, err := tcredis.Run(ctx, "redis:7-alpine",
		testcontainers.WithLogger(tclog.TestLogger(t)),
	)
	require.NoError(t, err)
	t.Cleanup(func() { _ = rc.Terminate(context.Background()) })

	connStr, err := rc.ConnectionString(ctx)
	require.NoError(t, err)
	opts, err := redis.ParseURL(connStr)
	require.NoError(t, err)
	client := redis.NewClient(opts)
	t.Cleanup(func() { _ = client.Close() })
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
// Uses a short L1 TTL (200ms) to avoid 30s+ wall-clock test time. After 150ms
// of sleep (75% of TTL elapsed → 25% remaining), the refresh probability
// per session is e^-0.25 ≈ 77.9%; over 100 sessions we expect 50-95 refreshes.
// Loose bounds (10-95) accommodate timing jitter where some entries may have
// just barely been LRU-evicted vs probabilistically refreshed.
func TestIntegration_L1CacheXFetchProbabilisticRefresh(t *testing.T) {
	rdb := startRedisContainerForAuth(t)

	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	t.Cleanup(cancel)

	const (
		sessionCount = 100
		l1TTL        = 200 * time.Millisecond
		sleepDur     = 150 * time.Millisecond // 75% of l1TTL elapsed → remaining=50ms
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
	//   refresh probability = e^(-remaining/ttl) = e^(-50/200) ≈ 77.9%
	// Expect 50-90 of 100 trials to refresh. Loose bound 10-95 accommodates
	// jitter (timer drift, GC, LRU eviction at the boundary).
	for i := 0; i < sessionCount; i++ {
		_, _, _ = m.verifySession(ctx, fmt.Sprintf("test-%d", i), true)
	}

	delta := int(testutil.ToFloat64(l1ProbRefreshes) - beforeRefreshes)
	require.Greater(t, delta, 10,
		"expected >10 probabilistic refreshes near expiry (math says ~78), got %d", delta)
	require.Less(t, delta, 95,
		"expected <95 probabilistic refreshes (some misses are LRU-evicted, not XFetch), got %d", delta)
}
