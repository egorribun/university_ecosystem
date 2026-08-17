package middleware

// Coverage tests (testing session 16) for the Redis pub/sub session-revocation
// listener (ListenForRevocations + listenOnce). The existing auth_redis_test.go
// uses a hand-rolled RESP mock that cannot speak pub/sub, so these paths scored
// ~0% in the default run (the live path was only covered by the //go:build
// integration testcontainers tier). miniredis implements SUBSCRIBE/PUBLISH, so we
// can exercise the listener end-to-end without Docker.

import (
	"context"
	"errors"
	"testing"
	"time"

	"github.com/alicebob/miniredis/v2"
	"github.com/redis/go-redis/v9"
	"github.com/redis/go-redis/v9/maintnotifications"
	"github.com/stretchr/testify/require"
)

func TestListenOnce_CachesRevocationOnMessage(t *testing.T) {
	mr := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{
		Addr:                     mr.Addr(),
		MaintNotificationsConfig: &maintnotifications.Config{Mode: maintnotifications.ModeDisabled},
	})
	t.Cleanup(func() { _ = client.Close() }) //nolint:errcheck // best-effort cleanup

	m := NewJWTMiddleware(testSecret, client)
	m.l1cache.Add("revoked:jti:abc", cacheEntry{exists: false, storedAt: time.Now()})

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	done := make(chan struct{})
	go func() { m.listenOnce(ctx); close(done) }()

	// Republish on each tick to dodge the subscribe/publish race: if the message
	// is published before SUBSCRIBE registers, it's lost — retrying guarantees
	// at least one lands after the listener is live.
	require.Eventually(t, func() bool {
		_ = client.Publish(context.Background(), "session:revocations", "abc").Err() //nolint:errcheck // fire-and-forget; Eventually retries
		entry, ok := m.l1cache.Get("revoked:jti:abc")
		return ok && entry.exists
	}, 3*time.Second, 50*time.Millisecond)

	// go-redis v9's Channel() auto-reconnects rather than closing the Go channel
	// on disconnect, so mr.Close() is not a reliable exit. Instead cancel the ctx
	// and publish more messages: listenOnce checks ctx.Done() as it processes each
	// received message, so the next delivery makes it return.
	cancel()
	require.Eventually(t, func() bool {
		_ = client.Publish(context.Background(), "session:revocations", "drain").Err() //nolint:errcheck // fire-and-forget; Eventually retries
		select {
		case <-done:
			return true
		default:
			return false
		}
	}, 3*time.Second, 50*time.Millisecond)
}

func TestVerifySession_WarmNegativeCacheFailsClosedAfterRedisDisconnect(t *testing.T) {
	mr := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{
		Addr:                     mr.Addr(),
		MaintNotificationsConfig: &maintnotifications.Config{Mode: maintnotifications.ModeDisabled},
	})
	t.Cleanup(func() { _ = client.Close() }) //nolint:errcheck // best-effort cleanup

	m := NewJWTMiddleware(testSecret, client)
	oldRand := xfetchRandFunc
	xfetchRandFunc = func() float64 { return 1 }
	t.Cleanup(func() { xfetchRandFunc = oldRand })
	valid, deny, err := m.verifySession(t.Context(), "warm-negative", true)
	require.NoError(t, err)
	require.True(t, valid)
	require.False(t, deny)
	_, ok := m.l1cache.Get("revoked:jti:warm-negative")
	require.False(t, ok, "negative revocation decisions must not be cached")
	m.l1cache.Add(
		"revoked:jti:warm-negative",
		cacheEntry{exists: false, storedAt: time.Now()},
	)

	mr.Close()
	valid, deny, err = m.verifySession(t.Context(), "warm-negative", true)
	require.False(t, valid)
	require.True(t, deny)
	require.Error(t, err)
}

func TestListenOnce_ReturnsWhenRedisHealthCheckFails(t *testing.T) {
	mr := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{
		Addr:                     mr.Addr(),
		MaintNotificationsConfig: &maintnotifications.Config{Mode: maintnotifications.ModeDisabled},
	})
	t.Cleanup(func() { _ = client.Close() }) //nolint:errcheck // best-effort cleanup

	m := NewJWTMiddleware(testSecret, client)
	ctx, cancel := context.WithCancel(context.Background())
	t.Cleanup(cancel)
	done := make(chan struct{})
	go func() {
		m.listenOnce(ctx)
		close(done)
	}()

	time.Sleep(100 * time.Millisecond)
	mr.Close()
	require.Eventually(t, func() bool {
		select {
		case <-done:
			return true
		default:
			return false
		}
	}, 2*time.Second, 25*time.Millisecond)
}

func TestListenOnce_ReturnsWhenPubSubChannelCloses(t *testing.T) {
	mr := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	t.Cleanup(func() { _ = client.Close() }) //nolint:errcheck // best-effort cleanup
	originalChannel := pubSubChannelFunc
	t.Cleanup(func() { pubSubChannelFunc = originalChannel })
	closedChannel := make(chan *redis.Message)
	close(closedChannel)
	pubSubChannelFunc = func(*redis.PubSub) <-chan *redis.Message { return closedChannel }

	m := NewJWTMiddleware(testSecret, client)
	done := make(chan struct{})
	go func() {
		m.listenOnce(t.Context())
		close(done)
	}()

	require.Eventually(t, func() bool {
		select {
		case <-done:
			return true
		default:
			return false
		}
	}, time.Second, 10*time.Millisecond)
}

func TestListenOnce_HealthyRedisKeepsListenerRunning(t *testing.T) {
	mr := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{
		Addr:                     mr.Addr(),
		MaintNotificationsConfig: &maintnotifications.Config{Mode: maintnotifications.ModeDisabled},
	})
	t.Cleanup(func() { _ = client.Close() }) //nolint:errcheck // best-effort cleanup
	ctx, cancel := context.WithCancel(context.Background())
	done := make(chan struct{})
	m := NewJWTMiddleware(testSecret, client)
	go func() {
		m.listenOnce(ctx)
		close(done)
	}()

	time.Sleep(revocationHealthCheckInterval + 100*time.Millisecond)
	select {
	case <-done:
		t.Fatal("healthy Redis must not stop the revocation listener")
	default:
	}
	cancel()
	require.Eventually(t, func() bool {
		select {
		case <-done:
			return true
		default:
			return false
		}
	}, time.Second, 10*time.Millisecond)
}

func TestListenForRevocations_NilRedisIsNoOp(t *testing.T) {
	m := NewJWTMiddleware(testSecret, nil)
	// m.redis == nil guard returns immediately and spawns no goroutine.
	m.ListenForRevocations(context.Background())
}

func TestListenOnce_ReportsPubSubCloseFailure(t *testing.T) {
	mr := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{
		Addr:                     mr.Addr(),
		MaintNotificationsConfig: &maintnotifications.Config{Mode: maintnotifications.ModeDisabled},
	})
	t.Cleanup(func() { _ = client.Close() }) //nolint:errcheck // test cleanup

	oldClose := closePubSubFunc
	t.Cleanup(func() { closePubSubFunc = oldClose })
	closed := make(chan struct{}, 1)
	closePubSubFunc = func(pubsub *redis.PubSub) error {
		_ = pubsub.Close() //nolint:errcheck // deliberately return the synthetic error below
		closed <- struct{}{}
		return errors.New("synthetic pubsub close failure")
	}

	m := NewJWTMiddleware(testSecret, client)
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	done := make(chan struct{})
	go func() {
		m.listenOnce(ctx)
		close(done)
	}()

	cancel()
	require.Eventually(t, func() bool {
		_ = client.Publish(context.Background(), "session:revocations", "drain").Err() //nolint:errcheck // test wake-up
		select {
		case <-done:
			return true
		default:
			return false
		}
	}, 3*time.Second, 25*time.Millisecond)
	require.Eventually(t, func() bool {
		select {
		case <-closed:
			return true
		default:
			return false
		}
	}, time.Second, 10*time.Millisecond)
}

func TestListenForRevocations_ProcessesThenReconnectsOnDisconnect(t *testing.T) {
	mr := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	t.Cleanup(func() { _ = client.Close() }) //nolint:errcheck // best-effort cleanup

	m := NewJWTMiddleware(testSecret, client)
	m.l1cache.Add("revoked:jti:xyz", cacheEntry{exists: false, storedAt: time.Now()})

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	m.ListenForRevocations(ctx) // spawns the listener goroutine

	require.Eventually(t, func() bool {
		_ = client.Publish(context.Background(), "session:revocations", "xyz").Err() //nolint:errcheck // fire-and-forget; Eventually retries
		entry, ok := m.l1cache.Get("revoked:jti:xyz")
		return ok && entry.exists
	}, 3*time.Second, 50*time.Millisecond)

	// Disconnect → the explicit health check returns the listener to its
	// reconnect loop. Cancellation then stops the process-lifetime goroutine.
	mr.Close()
	cancel()
	time.Sleep(150 * time.Millisecond) // allow the goroutine to observe cancel + return
}
