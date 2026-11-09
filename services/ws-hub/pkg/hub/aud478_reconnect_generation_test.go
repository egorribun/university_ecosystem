package hub

import (
	"context"
	"errors"
	"io"
	"log/slog"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"github.com/nats-io/nats.go"
	"github.com/stretchr/testify/require"
)

// aud478GenerationHub isolates admission and the consumer position without a broker.
func aud478GenerationHub() (*Hub, *atomic.Uint64, *atomic.Bool) {
	generation := &atomic.Uint64{}
	connected := &atomic.Bool{}
	connected.Store(true)
	h := &Hub{
		Logger:                     slog.New(slog.NewTextHandler(io.Discard, nil)),
		revocationWatchdogInterval: time.Second,
		revocationConnected:        func(*nats.Conn) bool { return connected.Load() },
		natsReconnectCount:         func(*nats.Conn) uint64 { return generation.Load() },
	}
	h.authCacheTracked.Store(true)
	h.revocationCatchingUp.Store(true)
	return h, generation, connected
}

func TestAUD478ReconnectGenerationWaitsForReplay(t *testing.T) {
	cases := []struct {
		name       string
		pending    uint64
		ackPending int
	}{
		{name: "undelivered", pending: 2},
		{name: "unacknowledged", ackPending: 1},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			h, generation, _ := aud478GenerationHub()
			info := &nats.ConsumerInfo{}
			old := revocationConsumerInfoFunc
			revocationConsumerInfoFunc = func(*nats.Subscription) (*nats.ConsumerInfo, error) { return info, nil }
			t.Cleanup(func() { revocationConsumerInfoFunc = old })
			reason := ""
			h.checkRevocationCatchUp(context.Background(), nil, &reason)
			require.False(t, h.AdmissionClosed(), "drained original session starts ready")

			info.NumPending = 1
			h.checkRevocationCatchUp(context.Background(), nil, &reason)
			require.False(t, h.AdmissionClosed(), "ordinary live pending work does not close admission")

			info.NumPending, info.NumAckPending = tc.pending, tc.ackPending
			generation.Store(1)
			// The reset lifecycle can complete before the revocation watcher polls.
			h.observedNATSReconnects.Store(1)
			require.True(t, h.AdmissionClosed(), "a new session is closed before its first replay poll")
			h.checkRevocationCatchUp(context.Background(), nil, &reason)
			require.True(t, h.AdmissionClosed(), "reconnect backlog must hold admission closed")
			require.True(t, h.RevocationCatchingUp())

			info.NumPending, info.NumAckPending = 0, 0
			h.checkRevocationCatchUp(context.Background(), nil, &reason)
			require.False(t, h.AdmissionClosed(), "only a drained new session can reopen admission")
		})
	}
}

func TestAUD478ReconnectGenerationRequiresCacheResetAndReadablePosition(t *testing.T) {
	h, generation, _ := aud478GenerationHub()
	info := &nats.ConsumerInfo{}
	var infoErr error
	old := revocationConsumerInfoFunc
	revocationConsumerInfoFunc = func(*nats.Subscription) (*nats.ConsumerInfo, error) { return info, infoErr }
	t.Cleanup(func() { revocationConsumerInfoFunc = old })
	reason := ""
	h.checkRevocationCatchUp(context.Background(), nil, &reason)
	require.False(t, h.AdmissionClosed())

	// Existing reset mock fails twice; a drained revocation replay cannot bypass it.
	resetter := &aud478ResetClient{events: &aud478EventLog{}}
	resetter.failures.Store(2)
	h.authClient = resetter
	generation.Store(1)
	h.closeAndObserveNATSSession(1)
	h.checkRevocationCatchUp(context.Background(), nil, &reason)
	for range 2 {
		require.Error(t, h.completeAuthCacheReset(context.Background()))
		require.True(t, h.AdmissionClosed())
	}
	require.NoError(t, h.completeAuthCacheReset(context.Background()))
	require.False(t, h.AdmissionClosed())

	infoErr = errors.New("synthetic consumer position unavailable")
	for range 3 {
		h.checkRevocationCatchUp(context.Background(), nil, &reason)
		require.True(t, h.AdmissionClosed(), "repeated unreadable positions stay closed")
	}
	infoErr = nil
	info.NumPending = 1
	h.checkRevocationCatchUp(context.Background(), nil, &reason)
	require.True(t, h.AdmissionClosed(), "a readable but undrained position stays closed")
	info.NumPending = 0
	h.checkRevocationCatchUp(context.Background(), nil, &reason)
	require.False(t, h.AdmissionClosed())
}

func TestAUD478PositionReadCannotOutliveItsSession(t *testing.T) {
	for _, tc := range []struct {
		name      string
		reconnect bool
	}{
		{name: "reconnect", reconnect: true},
		{name: "disconnect"},
	} {
		t.Run(tc.name, func(t *testing.T) {
			h, generation, connected := aud478GenerationHub()
			entered, release, done := make(chan struct{}), make(chan struct{}), make(chan struct{})
			var releaseOnce sync.Once
			old := revocationConsumerInfoFunc
			revocationConsumerInfoFunc = func(*nats.Subscription) (*nats.ConsumerInfo, error) {
				close(entered)
				<-release
				return &nats.ConsumerInfo{}, nil
			}
			t.Cleanup(func() {
				releaseOnce.Do(func() { close(release) })
				<-done
				revocationConsumerInfoFunc = old
			})
			reason := ""
			go func() {
				defer close(done)
				h.checkRevocationCatchUp(context.Background(), nil, &reason)
			}()
			select {
			case <-entered:
			case <-time.After(3 * time.Second):
				t.Fatal("consumer position request did not start")
			}

			if tc.reconnect {
				generation.Store(1)
				h.observedNATSReconnects.Store(1)
			} else {
				connected.Store(false)
			}
			releaseOnce.Do(func() { close(release) })
			select {
			case <-done:
			case <-time.After(3 * time.Second):
				t.Fatal("consumer position request did not finish")
			}
			require.True(t, h.RevocationCatchingUp(), "an old response cannot clear replay state")
			require.True(t, h.AdmissionClosed(), "an old response cannot make the new session ready")
		})
	}
}
