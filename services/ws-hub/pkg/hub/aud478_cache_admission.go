package hub

import (
	"context"
	"errors"
	"fmt"
	"time"

	"github.com/nats-io/nats.go"
	"github.com/university-ecosystem/ws-hub/pkg/config"
)

// authCacheResetRetryInterval paces retries while a reset or resubscription fails.
// Admission stays closed for the whole retry period.
const authCacheResetRetryInterval = time.Second

// AUD-478 authorization-cache admission lifecycle.
//
// ws-hub keeps an authorization cache (L1 in process, L2 in shared Redis). Events
// that would have invalidated it while this replica was not subscribed are not
// replayed: the owner decision is NO replay. Instead, the replica treats its cache
// as unknown at startup and after every NATS (re)connect:
//
//  1. the live cache-invalidation consumer is (re)created with DeliverNew, so only
//     messages published after it exists are delivered;
//  2. the local and shared authorization cache is reset, dropping every generation;
//  3. only then does admission reopen.
//
// While the barrier is closed, WebSocket and WebTransport admission return 503 before
// the one-time ticket is consumed, and readiness reports not ready.
//
// The seven-day CACHE_INVALIDATIONS retention is not part of this contract. Nothing
// is replayed from the stream on start or reconnect, so a shorter or longer
// retention changes nothing here. The only bounded replay left is the cache.revoke
// window, which is limited by the access-token lifetime.

// natsReconnects returns the live NATS reconnect count. Before a connection exists,
// or in tests without a connection, it reports zero.
func (h *Hub) natsReconnects() uint64 {
	if h.natsReconnectCount != nil {
		return h.natsReconnectCount(h.Nats)
	}
	if h.Nats == nil {
		return 0
	}
	return h.Nats.Stats().Reconnects
}

// AdmissionClosed reports whether WebSocket and WebTransport admission and readiness
// must fail closed. It is true while the revocation replay drains, while the
// authorization cache is unknown, and during the window between a NATS reconnect and
// the reset that follows it. The live reconnect comparison closes that window
// synchronously, so admission does not wait for the watcher's next poll.
func (h *Hub) AdmissionClosed() bool {
	if h.RevocationCatchingUp() {
		return true
	}
	if !h.authCacheTracked.Load() {
		return false
	}
	return h.authCacheAdmissionClosed.Load() || h.natsReconnects() != h.observedNATSReconnects.Load()
}

// resetAuthorizationCache resets the authorization cache when the configured client
// holds one. Hubs without a resettable client have no local or shared cache state to
// clear, so they report success.
func (h *Hub) resetAuthorizationCache(ctx context.Context) error {
	resetter, ok := h.authClient.(RoomAuthCacheResetter)
	if !ok {
		return nil
	}
	return resetter.ResetAuthorizationCache(ctx)
}

// completeAuthCacheReset closes the barrier, resets the cache, and reopens admission
// only when the reset succeeded. A failed reset leaves admission closed.
func (h *Hub) completeAuthCacheReset(ctx context.Context) error {
	h.authCacheAdmissionClosed.Store(true)
	if err := h.resetAuthorizationCache(ctx); err != nil {
		return err
	}
	h.authCacheAdmissionClosed.Store(false)
	return nil
}

// closeAndObserveNATSSession closes admission and then records the reconnect count it
// covers. The order is required: the barrier must already be closed when the new count
// becomes visible. Recording the count first leaves a window where live == observed and
// the closed flag is still false, so admission would read open with a pre-reconnect cache.
func (h *Hub) closeAndObserveNATSSession(live uint64) {
	h.authCacheAdmissionClosed.Store(true)
	if h.reconnectTransitionHook != nil {
		h.reconnectTransitionHook()
	}
	h.observedNATSReconnects.Store(live)
}

// startAuthCacheAdmission starts the admission lifecycle. The first reset runs
// synchronously, after the live invalidation consumer exists and before SubscribeToNATS
// returns, so a healthy startup serves its first client with a reset cache. If that
// first attempt fails, the watcher retries and admission stays closed.
func (h *Hub) startAuthCacheAdmission(appCtx context.Context) {
	h.closeAndObserveNATSSession(h.natsReconnects())
	// Tracking turns on only after the barrier is closed, so no window opens where
	// the session is tracked but admission still reads open.
	h.authCacheTracked.Store(true)
	firstResetDone := false
	if err := h.completeAuthCacheReset(appCtx); err != nil {
		h.Logger.WarnContext(appCtx, "Authorization cache reset failed at startup; WebSocket admission closed until it succeeds",
			"err", err)
	} else {
		firstResetDone = true
		h.Logger.InfoContext(appCtx, "Authorization cache reset at startup; WebSocket admission enabled")
	}
	StartTrackedGoroutine(func() { h.runAuthCacheAdmission(appCtx, firstResetDone) })
}

// runAuthCacheAdmission drives reconnect detection, resubscription and reset until the
// context ends or the hub stops. It only ever opens admission after a successful reset.
func (h *Hub) runAuthCacheAdmission(ctx context.Context, resetDone bool) {
	needSubscribe := false
	needReset := !resetDone
	pollInterval := h.revocationWatchdogInterval
	if pollInterval <= 0 {
		pollInterval = time.Second
	}
	timer := time.NewTimer(pollInterval)
	defer timer.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-timer.C:
		}
		if h.stopped.Load() {
			return
		}
		if live := h.natsReconnects(); live != h.observedNATSReconnects.Load() {
			h.closeAndObserveNATSSession(live)
			needSubscribe, needReset = true, true
			h.Logger.WarnContext(ctx, "NATS reconnected; WebSocket admission closed until the authorization cache is reset")
		}
		if !h.natsConnectionUp() {
			h.authCacheAdmissionClosed.Store(true)
			needReset = true
			timer.Reset(revocationCatchUpPollInterval)
			continue
		}
		if needSubscribe {
			if err := h.resubscribeCacheInvalidation(ctx); err != nil {
				h.Logger.WarnContext(ctx, "Cache invalidation resubscription failed; retrying", "err", err)
				timer.Reset(authCacheResetRetryInterval)
				continue
			}
			needSubscribe = false
		}
		if needReset {
			if err := h.completeAuthCacheReset(ctx); err != nil {
				h.Logger.WarnContext(ctx, "Authorization cache reset failed; retrying", "err", err)
				timer.Reset(authCacheResetRetryInterval)
				continue
			}
			needReset = false
			h.Logger.InfoContext(ctx, "Authorization cache reset after NATS reconnect; WebSocket admission enabled")
		}
		timer.Reset(pollInterval)
	}
}

// resubscribeCacheInvalidation replaces the live invalidation consumer with a fresh
// one that starts at new messages. An ephemeral consumer can be removed while the
// replica is disconnected, so the old subscription is never trusted after a reconnect.
func (h *Hub) resubscribeCacheInvalidation(ctx context.Context) error {
	h.subsMu.Lock()
	previous := h.invalidationSub
	h.subsMu.Unlock()

	fresh, err := h.openCacheInvalidationSubscription(ctx)
	if err != nil {
		return fmt.Errorf("resubscribe cache invalidation: %w", err)
	}

	h.subsMu.Lock()
	if h.stopped.Load() {
		h.subsMu.Unlock()
		if fresh != nil {
			if unsubErr := fresh.Unsubscribe(); unsubErr != nil && !errors.Is(unsubErr, nats.ErrBadSubscription) {
				h.Logger.WarnContext(ctx, "Could not unsubscribe a cache invalidation consumer opened during shutdown", "err", unsubErr)
			}
		}
		return errors.New("hub is stopping")
	}
	h.invalidationSub = fresh
	if previous != nil {
		h.subs = removeSubscription(h.subs, previous)
	}
	if fresh != nil {
		h.subs = append(h.subs, fresh)
	}
	h.subsMu.Unlock()

	if previous != nil {
		if unsubErr := previous.Unsubscribe(); unsubErr != nil && !errors.Is(unsubErr, nats.ErrBadSubscription) {
			h.Logger.WarnContext(ctx, "Could not unsubscribe the previous cache invalidation consumer", "err", unsubErr)
		}
	}
	return nil
}

// removeSubscription returns subs without target.
func removeSubscription(subs []*nats.Subscription, target *nats.Subscription) []*nats.Subscription {
	kept := subs[:0]
	for _, sub := range subs {
		if sub != target {
			kept = append(kept, sub)
		}
	}
	return kept
}

// resolveNATSConsumerSettings fills unset fields with the chart-matching defaults and
// validates the result. A value that is set but outside the contract is an error.
func resolveNATSConsumerSettings(settings config.NATSConsumerSettings) (config.NATSConsumerSettings, error) {
	defaults := config.DefaultNATSConsumerSettings()
	if settings.AckPolicy == "" {
		settings.AckPolicy = defaults.AckPolicy
	}
	if settings.AckWaitSeconds == 0 {
		settings.AckWaitSeconds = defaults.AckWaitSeconds
	}
	if settings.MaxDeliver == 0 {
		settings.MaxDeliver = defaults.MaxDeliver
	}
	if settings.InactiveThresholdSeconds == 0 {
		settings.InactiveThresholdSeconds = defaults.InactiveThresholdSeconds
	}
	if err := settings.Validate(); err != nil {
		return config.NATSConsumerSettings{}, err
	}
	return settings, nil
}
