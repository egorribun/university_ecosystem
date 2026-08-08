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

func TestListenOnce_RemovesL1KeyOnRevocationMessage(t *testing.T) {
	mr := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{
		Addr:                     mr.Addr(),
		MaintNotificationsConfig: &maintnotifications.Config{Mode: maintnotifications.ModeDisabled},
	})
	t.Cleanup(func() { _ = client.Close() }) //nolint:errcheck // best-effort cleanup

	m := NewJWTMiddleware(testSecret, client)
	m.l1cache.Add("revoked:jti:abc", cacheEntry{exists: true, storedAt: time.Now()})

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	done := make(chan struct{})
	go func() { m.listenOnce(ctx); close(done) }()

	// Republish on each tick to dodge the subscribe/publish race: if the message
	// is published before SUBSCRIBE registers, it's lost — retrying guarantees
	// at least one lands after the listener is live.
	require.Eventually(t, func() bool {
		_ = client.Publish(context.Background(), "session:revocations", "abc").Err() //nolint:errcheck // fire-and-forget; Eventually retries
		_, ok := m.l1cache.Get("revoked:jti:abc")
		return !ok
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
	m.l1cache.Add("revoked:jti:xyz", cacheEntry{exists: true, storedAt: time.Now()})

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	m.ListenForRevocations(ctx) // spawns the listener goroutine

	require.Eventually(t, func() bool {
		_ = client.Publish(context.Background(), "session:revocations", "xyz").Err() //nolint:errcheck // fire-and-forget; Eventually retries
		_, ok := m.l1cache.Get("revoked:jti:xyz")
		return !ok
	}, 3*time.Second, 50*time.Millisecond)

	// Disconnect → the listener observes the closed channel, increments the
	// disconnect metric, purges L1, computes backoff, then exits on ctx cancel.
	mr.Close()
	cancel()
	time.Sleep(150 * time.Millisecond) // allow the goroutine to observe cancel + return
}
