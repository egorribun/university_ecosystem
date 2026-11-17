package file_processorv1

import (
	"context"
	"sync"
	"testing"
	"time"

	"github.com/stretchr/testify/require"
)

// Capture the first pre-lock Err result before notifying the test. Cancellation
// after checked closes cannot change that already-observed result.
type replayAdmissionObservedContext struct {
	context.Context
	checked chan struct{}
	once    sync.Once
}

func (ctx *replayAdmissionObservedContext) Err() error {
	err := ctx.Context.Err()
	ctx.once.Do(func() { close(ctx.checked) })
	return err
}

func TestCapabilityReplayCancellationWhileWaitingDoesNotMutateRegistry(t *testing.T) {
	for _, deterministic := range []bool{false, true} {
		name := "Consume"
		if deterministic {
			name = "ConsumeAt"
		}
		t.Run(name, func(t *testing.T) {
			now := time.Now().UTC()
			expired := now.Add(-time.Minute)
			expires := now.Add(time.Minute)
			registry := NewCapabilityReplayRegistry(1)
			registry.entries["expired"] = expired
			parent, cancel := context.WithCancel(context.Background())
			defer cancel()
			ctx := &replayAdmissionObservedContext{
				Context: parent,
				checked: make(chan struct{}),
			}
			type result struct {
				accepted bool
				err      error
			}
			done := make(chan result, 1)
			registry.mu.Lock()
			unlock := sync.OnceFunc(registry.mu.Unlock)
			defer unlock()
			go func() {
				var accepted bool
				var err error
				if deterministic {
					accepted, err = registry.ConsumeAt(ctx, "retryable", expires, now)
				} else {
					accepted, err = registry.Consume(ctx, "retryable", expires)
				}
				done <- result{accepted, err}
			}()
			select {
			case <-ctx.checked:
			case <-time.After(5 * time.Second):
				t.Fatal("admission did not reach its pre-lock context check")
			}
			cancel()
			unlock()

			select {
			case got := <-done:
				require.ErrorIs(t, got.err, context.Canceled)
				require.False(t, got.accepted)
			case <-time.After(5 * time.Second):
				t.Fatal("cancelled admission did not finish")
			}
			// Even expiry cleanup must not mutate state for a cancelled caller.
			require.Equal(t, map[string]time.Time{"expired": expired}, registry.entries)
			accepted, err := registry.ConsumeAt(context.Background(), "retryable", expires, now)
			require.NoError(t, err)
			require.True(t, accepted)
			require.Equal(t, map[string]time.Time{"retryable": expires}, registry.entries)
		})
	}
}
