package file_processorv1

import (
	"context"
	"errors"
	"sync"
	"testing"
	"time"

	"github.com/stretchr/testify/require"
)

func TestCapabilityReplayRegistryConsumesNonceOnce(t *testing.T) {
	now := time.Unix(1_700_000_000, 0)
	registry := NewCapabilityReplayRegistry(2)
	expires := now.Add(time.Minute)

	accepted, err := registry.ConsumeAt(context.Background(), "nonce-1", expires, now)
	require.NoError(t, err)
	require.True(t, accepted)
	accepted, err = registry.ConsumeAt(context.Background(), "nonce-1", expires, now)
	require.NoError(t, err)
	require.False(t, accepted)
}

func TestCapabilityReplayRegistryPurgesExpiredAndRejectsCapacityOverflow(t *testing.T) {
	now := time.Unix(1_700_000_000, 0)
	registry := NewCapabilityReplayRegistry(1)
	accepted, err := registry.ConsumeAt(context.Background(), "expired", now, now.Add(-time.Second))
	require.NoError(t, err)
	require.True(t, accepted)
	accepted, err = registry.ConsumeAt(context.Background(), "live", now.Add(time.Minute), now)
	require.NoError(t, err)
	require.True(t, accepted)
	accepted, err = registry.ConsumeAt(context.Background(), "another", now.Add(time.Minute), now)
	require.ErrorIs(t, err, ErrCapabilityReplayRegistryFull)
	require.False(t, accepted)
}

func TestCapabilityReplayRegistryRejectsInvalidOrCancelledAdmission(t *testing.T) {
	now := time.Unix(1_700_000_000, 0)
	registry := NewCapabilityReplayRegistry(1)
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	accepted, err := registry.ConsumeAt(ctx, "nonce", now.Add(time.Minute), now)
	require.ErrorIs(t, err, context.Canceled)
	require.False(t, accepted)
	accepted, err = registry.ConsumeAt(context.Background(), "", now.Add(time.Minute), now)
	require.Error(t, err)
	require.False(t, accepted)
	accepted, err = registry.ConsumeAt(context.Background(), "nonce", now, now)
	require.Error(t, err)
	require.False(t, accepted)

	var nilRegistry *CapabilityReplayRegistry
	accepted, err = nilRegistry.Consume(context.Background(), "nonce", time.Now().Add(time.Minute))
	require.Error(t, err)
	require.False(t, accepted)
}

func TestCapabilityReplayRegistryRejectsNilContext(t *testing.T) {
	now := time.Unix(1_700_000_000, 0)
	registry := NewCapabilityReplayRegistry(1)

	accepted, err := registry.ConsumeAt(nil, "nonce", now.Add(time.Minute), now)

	require.Error(t, err)
	require.False(t, accepted)
}

func TestCapabilityReplayRegistryIsAtomicForConcurrentConsumers(t *testing.T) {
	registry := NewCapabilityReplayRegistry(10)
	expires := time.Now().Add(time.Minute)
	const attempts = 32
	results := make(chan bool, attempts)
	errs := make(chan error, attempts)
	var wg sync.WaitGroup
	for i := 0; i < attempts; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			accepted, err := registry.Consume(context.Background(), "same-nonce", expires)
			results <- accepted
			errs <- err
		}()
	}
	wg.Wait()
	close(results)
	close(errs)
	acceptedCount := 0
	for accepted := range results {
		if accepted {
			acceptedCount++
		}
	}
	for err := range errs {
		require.NoError(t, err)
	}
	require.Equal(t, 1, acceptedCount)
}

func TestCapabilityReplayRegistryErrorSentinelIsStable(t *testing.T) {
	require.True(t, errors.Is(ErrCapabilityReplayRegistryFull, ErrCapabilityReplayRegistryFull))
}
