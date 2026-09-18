package file_processorv1

import (
	"context"
	"errors"
	"sync"
	"time"
)

// DefaultCapabilityReplayCapacity bounds the process-local replay registry.
// Capability lifetimes are limited to 15 minutes, so expired entries are
// removed on every admission and cannot grow without bound.
const DefaultCapabilityReplayCapacity = 100_000

// ErrCapabilityReplayRegistryFull is returned instead of evicting a live
// nonce. Evicting an active nonce would silently re-enable replay under load;
// fail-closed admission is the safer behavior for a security boundary.
var ErrCapabilityReplayRegistryFull = errors.New("processing capability replay registry is full")

// CapabilityReplayGuard is the shared one-time-admission contract used by all
// file-processing ingresses. Implementations must make Consume atomic for a
// given nonce and retain the admission until expiry.
type CapabilityReplayGuard interface {
	Consume(context.Context, string, time.Time) (bool, error)
}

// ConsumeCapabilityReplay routes an admission through a deterministic clock
// seam when the guard exposes one, while preserving the small production
// interface used by distributed implementations. The transport boundaries
// pass the same clock used to validate the capability so an expired proof can
// never be admitted merely because two clock reads straddle its expiry.
func ConsumeCapabilityReplay(ctx context.Context, guard CapabilityReplayGuard, nonce string, expiresAt, now time.Time) (bool, error) {
	if guard == nil {
		return false, errors.New("processing capability replay guard is nil")
	}
	if deterministic, ok := guard.(interface {
		ConsumeAt(context.Context, string, time.Time, time.Time) (bool, error)
	}); ok {
		return deterministic.ConsumeAt(ctx, nonce, expiresAt, now)
	}
	return guard.Consume(ctx, nonce, expiresAt)
}

// CapabilityReplayRegistry is a bounded, concurrency-safe in-process replay
// registry. The main file-processor process shares one instance between HTTP
// GraphQL, gRPC and NATS. Deployments with multiple file-processor replicas
// must provide an equivalent shared implementation at the orchestration layer
// before claiming cross-replica one-time semantics.
type CapabilityReplayRegistry struct {
	mu         sync.Mutex
	entries    map[string]time.Time
	maxEntries int
}

// NewCapabilityReplayRegistry constructs a bounded replay registry. A
// non-positive capacity selects the documented default.
func NewCapabilityReplayRegistry(maxEntries int) *CapabilityReplayRegistry {
	if maxEntries <= 0 {
		maxEntries = DefaultCapabilityReplayCapacity
	}
	return &CapabilityReplayRegistry{
		entries:    make(map[string]time.Time, maxEntries),
		maxEntries: maxEntries,
	}
}

// Consume atomically admits a nonce once. It returns false when the nonce has
// already been admitted and returns an error when the bounded registry cannot
// safely admit another live nonce. A cancelled context never mutates state.
func (r *CapabilityReplayRegistry) Consume(ctx context.Context, nonce string, expiresAt time.Time) (bool, error) {
	return r.consumeAt(ctx, nonce, expiresAt, time.Now().UTC())
}

// ConsumeAt is a deterministic test seam for Consume. Production code should
// use Consume so the registry uses its own wall clock consistently.
func (r *CapabilityReplayRegistry) ConsumeAt(ctx context.Context, nonce string, expiresAt, now time.Time) (bool, error) {
	return r.consumeAt(ctx, nonce, expiresAt, now)
}

func (r *CapabilityReplayRegistry) consumeAt(ctx context.Context, nonce string, expiresAt, now time.Time) (bool, error) {
	if r == nil {
		return false, errors.New("processing capability replay registry is nil")
	}
	if ctx == nil {
		return false, errors.New("processing capability replay context is nil")
	}
	if err := ctx.Err(); err != nil {
		return false, err
	}
	if nonce == "" || !expiresAt.After(now) {
		return false, errors.New("processing capability replay admission is invalid")
	}

	r.mu.Lock()
	defer r.mu.Unlock()
	for key, expiry := range r.entries {
		if !expiry.After(now) {
			delete(r.entries, key)
		}
	}
	if _, exists := r.entries[nonce]; exists {
		return false, nil
	}
	if len(r.entries) >= r.maxEntries {
		return false, ErrCapabilityReplayRegistryFull
	}
	r.entries[nonce] = expiresAt
	return true, nil
}
