package hub

import (
	"context"
	"crypto/rand"
	"errors"
	"fmt"
	"log/slog"
	"os"
	"strings"
	"testing"
	"time"

	"github.com/nats-io/nats.go"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

const (
	aud511TestUserID = "11111111-1111-1111-1111-111111111111"
	aud511TestRoomID = "22222222-2222-2222-2222-222222222222"
)

func aud511CacheInvalidationMessage(subject string, data []byte, streamSequence uint64, publishedAt time.Time) *nats.Msg {
	return &nats.Msg{
		Subject: subject,
		Data:    data,
		Sub:     &nats.Subscription{},
		Reply: fmt.Sprintf(
			"$JS.ACK.CACHE_INVALIDATIONS.ws-hub-cache.1.%d.1.%d.0",
			streamSequence,
			publishedAt.UnixNano(),
		),
	}
}

func TestAUD511ExpiredPublishTimeDoesNotKeepPendingMarker(t *testing.T) {
	oldNak := jetStreamNakFunc
	t.Cleanup(func() { jetStreamNakFunc = oldNak })
	jetStreamNakFunc = func(*nats.Msg, time.Duration) error { return nil }

	const publishSequence = 41
	publishedAt := time.Now().Add(-126 * time.Second)
	auth := &membershipRecordingAuthClient{
		memberships: map[[2]string]bool{{aud511TestUserID, aud511TestRoomID}: true},
		refreshErr:  errors.New("authorization refresh unavailable"),
	}
	h := newNatsTestHub(auth, "internal-secret", 10)
	payload := signedInvalidationPayload(t, "internal-secret", invalidationData{
		EvictRoom: true,
		RoomID:    aud511TestRoomID,
		UserID:    aud511TestUserID,
	})
	msg := aud511CacheInvalidationMessage("cache.revoke", payload, publishSequence, publishedAt)
	metadata, err := msg.Metadata()
	require.NoError(t, err)
	assert.Equal(t, uint64(publishSequence), metadata.Sequence.Stream)
	assert.Equal(t, publishedAt.UnixNano(), metadata.Timestamp.UnixNano())

	h.handleCacheInvalidation(context.Background())(msg)

	assert.False(t, h.isRoomRevocationPending(aud511TestUserID, aud511TestRoomID),
		"an authorization failure must not retain a marker beyond publish-time expiry")
}

func TestAUD511MarkerExpiryUsesPublishTimeAndOnlyNewSequencesRenew(t *testing.T) {
	oldNak := jetStreamNakFunc
	t.Cleanup(func() { jetStreamNakFunc = oldNak })
	jetStreamNakFunc = func(*nats.Msg, time.Duration) error { return nil }

	auth := &membershipRecordingAuthClient{
		memberships: map[[2]string]bool{{aud511TestUserID, aud511TestRoomID}: true},
		refreshErr:  errors.New("authorization refresh unavailable"),
	}
	h := newNatsTestHub(auth, "internal-secret", 10)
	process := h.handleCacheInvalidation(context.Background())
	publishedAt := time.Now().Add(-time.Second)
	payload := signedInvalidationPayload(t, "internal-secret", invalidationData{
		EvictRoom: true,
		RoomID:    aud511TestRoomID,
		UserID:    aud511TestUserID,
	})
	first := aud511CacheInvalidationMessage("cache.revoke", payload, 50, publishedAt)
	process(first)
	marker := aud511PendingMarker(t, h)
	require.False(t, marker.sticky)
	assert.Equal(t, publishedAt.Add(pendingRoomRevocationTTL).UnixNano(), marker.expiresAt.UnixNano(),
		"expiry is anchored to the immutable JetStream publish timestamp")

	process(first)
	redelivered := aud511PendingMarker(t, h)
	assert.Equal(t, marker.expiresAt, redelivered.expiresAt,
		"redelivering the same stream sequence must not renew its expiry")

	newerPublishedAt := publishedAt.Add(time.Second)
	process(aud511CacheInvalidationMessage("cache.revoke", payload, 51, newerPublishedAt))
	newer := aud511PendingMarker(t, h)
	assert.Equal(t, uint64(51), newer.streamSequence)
	assert.Equal(t, newerPublishedAt.Add(pendingRoomRevocationTTL).UnixNano(), newer.expiresAt.UnixNano(),
		"a fresh newer stream sequence receives its own publish-time expiry")

	process(first)
	olderReplay := aud511PendingMarker(t, h)
	assert.Equal(t, uint64(51), olderReplay.streamSequence,
		"an older replay cannot replace a newer revocation marker")
	assert.Equal(t, newer.expiresAt, olderReplay.expiresAt)
}

func TestAUD511NoRefresherMarkerStaysStickyAndFailsClosedPastExpiry(t *testing.T) {
	h := newNatsTestHub(&mockAuthClient{allowed: true}, "", 10)
	require.Error(t, h.evictRoomMembership(context.Background(), aud511TestUserID, aud511TestRoomID))
	marker := aud511PendingMarker(t, h)
	require.True(t, marker.sticky, "a missing authoritative refresher cannot age into a cached allow")

	removed := h.pruneExpiredRoomRevocations(time.Now().Add(10 * pendingRoomRevocationTTL))
	assert.Zero(t, removed, "sticky fail-closed markers are not removed by expiry cleanup")
	assert.True(t, h.isRoomRevocationPending(aud511TestUserID, aud511TestRoomID))
	assert.False(t, authorizeRoomJoinForTest(h, context.Background(), aud511TestUserID, aud511TestRoomID),
		"a stale positive result from a non-refreshing auth client remains denied")
}

func TestAUD511MarkerMergePreservesStickyAndNonShorteningExpiry(t *testing.T) {
	h := newNatsTestHub(&membershipRecordingAuthClient{}, "", 10)
	now := time.Now()
	publication := roomRevocationPublication{
		publishedAt:    now.Add(-10 * time.Second),
		streamSequence: 70,
	}
	h.markRoomRevocationPending(aud511TestUserID, aud511TestRoomID, publication, false)
	first := aud511PendingMarker(t, h)

	// An anomalously old timestamp on a newer sequence must not shorten the
	// already-established fail-closed window.
	h.markRoomRevocationPending(aud511TestUserID, aud511TestRoomID, roomRevocationPublication{
		publishedAt:    now.Add(-20 * time.Second),
		streamSequence: 71,
	}, false)
	newer := aud511PendingMarker(t, h)
	assert.Equal(t, uint64(71), newer.streamSequence)
	assert.Equal(t, first.expiresAt.UnixNano(), newer.expiresAt.UnixNano())

	h.markRoomRevocationPending(aud511TestUserID, aud511TestRoomID, roomRevocationPublication{
		publishedAt:    now,
		streamSequence: 72,
	}, true)
	sticky := aud511PendingMarker(t, h)
	require.True(t, sticky.sticky, "a no-refresher failure upgrades a finite marker to sticky")

	h.markRoomRevocationPending(aud511TestUserID, aud511TestRoomID, roomRevocationPublication{
		publishedAt:    now.Add(time.Second),
		streamSequence: 73,
	}, false)
	assert.True(t, aud511PendingMarker(t, h).sticky,
		"a later transient event must not weaken an unresolved sticky revocation")
}

func TestAUD511ZeroPublicationTimeAndExpiredNewSequenceAreHandled(t *testing.T) {
	h := newNatsTestHub(&membershipRecordingAuthClient{}, "", 10)
	h.markRoomRevocationPending(aud511TestUserID, aud511TestRoomID, roomRevocationPublication{}, false)
	marker := aud511PendingMarker(t, h)
	assert.False(t, marker.expiresAt.IsZero(), "missing metadata uses a bounded local fallback")

	expiredPublication := roomRevocationPublication{
		publishedAt:    time.Now().Add(-pendingRoomRevocationTTL - time.Second),
		streamSequence: marker.streamSequence + 1,
	}
	h.markRoomRevocationPending(aud511TestUserID, aud511TestRoomID, expiredPublication, false)
	assert.Equal(t, marker.streamSequence, aud511PendingMarker(t, h).streamSequence,
		"an expired newer event must not replace an active marker")

	key := roomMembershipKey{userID: "expired-user", roomID: "expired-room"}
	h.pendingRoomRevocationsMu.Lock()
	h.pendingRoomRevocations[key] = pendingRoomRevocation{
		streamSequence: 74,
		expiresAt:      time.Now().Add(-time.Second),
	}
	h.pendingRoomRevocationsMu.Unlock()
	assert.False(t, h.isRoomRevocationPending(key.userID, key.roomID))
	h.pendingRoomRevocationsMu.RLock()
	_, exists := h.pendingRoomRevocations[key]
	h.pendingRoomRevocationsMu.RUnlock()
	assert.False(t, exists, "checking a stale marker also reclaims it")
}

func TestAUD511PeriodicCleanupReclaimsExpiredMarkersWithoutUserReturn(t *testing.T) {
	h := newNatsTestHub(&membershipRecordingAuthClient{}, "", 10)
	h.limiterCleanupInterval = 10 * time.Millisecond
	key := roomMembershipKey{userID: aud511TestUserID, roomID: aud511TestRoomID}
	h.pendingRoomRevocationsMu.Lock()
	h.pendingRoomRevocations = map[roomMembershipKey]pendingRoomRevocation{
		key: {streamSequence: 60, expiresAt: time.Now().Add(-time.Millisecond)},
	}
	h.pendingRoomRevocationsMu.Unlock()

	ctx, cancel := context.WithCancel(context.Background())
	h.StartLimiterCleanup(ctx)
	t.Cleanup(func() {
		cancel()
		h.limiterCleanupWG.Wait()
	})

	assert.Eventually(t, func() bool {
		h.pendingRoomRevocationsMu.RLock()
		defer h.pendingRoomRevocationsMu.RUnlock()
		_, exists := h.pendingRoomRevocations[key]
		return !exists
	}, time.Second, 10*time.Millisecond,
		"the scheduled cleanup must reclaim an expired marker even if the user never rejoins")
}

func TestAUD511NoSocketRevocationMarkerExpiresWithoutUserReturn(t *testing.T) {
	auth := &membershipRecordingAuthClient{
		memberships: map[[2]string]bool{{aud511TestUserID, aud511TestRoomID}: true},
		refreshErr:  errors.New("temporary authorization refresh failure"),
	}
	h := newNatsTestHub(auth, "", 10)
	h.limiterCleanupInterval = 10 * time.Millisecond

	publication := roomRevocationPublication{
		publishedAt:    time.Now().Add(-pendingRoomRevocationTTL + time.Second),
		streamSequence: 81,
	}
	err := h.evictRoomMembershipAt(
		context.Background(),
		aud511TestUserID,
		aud511TestRoomID,
		publication,
	)
	require.Error(t, err, "a transient refresh failure is not treated as success")

	h.mu.RLock()
	roomSocketCount := len(h.Rooms[aud511TestRoomID])
	h.mu.RUnlock()
	require.Zero(t, roomSocketCount, "the revoked user has no socket to return on")

	marker := aud511PendingMarker(t, h)
	require.False(t, marker.sticky, "a refresh-capable auth client keeps a finite marker")
	require.True(
		t,
		marker.expiresAt.After(time.Now()),
		"the marker remains pending until its publish-time expiry",
	)

	ctx, cancel := context.WithCancel(context.Background())
	h.StartLimiterCleanup(ctx)
	t.Cleanup(func() {
		cancel()
		h.limiterCleanupWG.Wait()
	})

	assert.Eventually(t, func() bool {
		h.pendingRoomRevocationsMu.RLock()
		defer h.pendingRoomRevocationsMu.RUnlock()
		_, exists := h.pendingRoomRevocations[roomMembershipKey{
			userID: aud511TestUserID,
			roomID: aud511TestRoomID,
		}]
		return !exists
	}, 3*time.Second, 10*time.Millisecond,
		"scheduled expiry cleanup reclaims the marker without a socket return")
}

func TestAUD511CanceledEvictionDoesNotCreatePendingMarker(t *testing.T) {
	h := newNatsTestHub(&membershipRecordingAuthClient{}, "", 10)
	barrier := h.roomMembershipLock(aud511TestUserID, aud511TestRoomID)
	barrier.Lock()
	barrier.entry.mutationPending = true
	barrier.unlockRetained()

	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	err := h.evictRoomMembershipAt(ctx, aud511TestUserID, aud511TestRoomID, roomRevocationPublication{
		publishedAt:    time.Now(),
		streamSequence: 80,
	})
	require.Error(t, err)
	assert.False(t, h.isRoomRevocationPending(aud511TestUserID, aud511TestRoomID))

	barrier.Lock()
	barrier.entry.mutationPending = false
	barrier.entry.signalChangedLocked()
	barrier.Unlock()
}

func aud511PendingMarker(t *testing.T, h *Hub) pendingRoomRevocation {
	t.Helper()
	h.pendingRoomRevocationsMu.RLock()
	defer h.pendingRoomRevocationsMu.RUnlock()
	marker, exists := h.pendingRoomRevocations[roomMembershipKey{
		userID: aud511TestUserID,
		roomID: aud511TestRoomID,
	}]
	require.True(t, exists, "pending room revocation marker should exist")
	return marker
}

func TestAUD512RecoveredNATSPanicsTerminateMessages(t *testing.T) {
	oldUnmarshal := hubJSONUnmarshalFunc
	oldTerm := jetStreamTermFunc
	oldNak := jetStreamNakFunc
	t.Cleanup(func() {
		hubJSONUnmarshalFunc = oldUnmarshal
		jetStreamTermFunc = oldTerm
		jetStreamNakFunc = oldNak
	})
	hubJSONUnmarshalFunc = func([]byte, any) error { panic("decoder panic") }

	tests := []struct {
		name    string
		subject string
		handler func(*Hub) nats.MsgHandler
	}{
		{
			name:    "chat",
			subject: "chat.room",
			handler: func(h *Hub) nats.MsgHandler { return h.handleChatDelivery(context.Background(), true) },
		},
		{
			name:    "notifications",
			subject: "notifications." + aud511TestUserID,
			handler: func(h *Hub) nats.MsgHandler { return h.handleNotifications(context.Background()) },
		},
		{
			name:    "cache invalidation",
			subject: "cache.invalidate",
			handler: func(h *Hub) nats.MsgHandler { return h.handleCacheInvalidation(context.Background()) },
		},
		{
			name:    "control",
			subject: "ws_hub.control",
			handler: func(h *Hub) nats.MsgHandler { return h.handleControlMessage(context.Background()) },
		},
	}

	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			termCalls := 0
			nakCalls := 0
			jetStreamTermFunc = func(*nats.Msg) error { termCalls++; return nil }
			jetStreamNakFunc = func(*nats.Msg, time.Duration) error { nakCalls++; return nil }

			h := newNatsTestHub(&mockAuthClient{allowed: true}, "internal-secret", 10)
			test.handler(h)(&nats.Msg{Subject: test.subject, Data: []byte("{}")})

			assert.Equal(t, 1, termCalls, "a recovered callback panic is a permanent poison message")
			assert.Zero(t, nakCalls, "a successful TERM should not schedule another delivery")
		})
	}
}

func TestAUD512PanicTermFailureFallsBackToFiveSecondNak(t *testing.T) {
	oldUnmarshal := hubJSONUnmarshalFunc
	oldTerm := jetStreamTermFunc
	oldNak := jetStreamNakFunc
	t.Cleanup(func() {
		hubJSONUnmarshalFunc = oldUnmarshal
		jetStreamTermFunc = oldTerm
		jetStreamNakFunc = oldNak
	})
	hubJSONUnmarshalFunc = func([]byte, any) error { panic("decoder panic") }
	termCalls := 0
	nakDelays := make([]time.Duration, 0, 1)
	jetStreamTermFunc = func(*nats.Msg) error { termCalls++; return errors.New("term transport unavailable") }
	jetStreamNakFunc = func(_ *nats.Msg, delay time.Duration) error {
		nakDelays = append(nakDelays, delay)
		return nil
	}

	h := newNatsTestHub(&mockAuthClient{allowed: true}, "internal-secret", 10)
	h.handleNotifications(context.Background())(&nats.Msg{
		Subject: "notifications." + aud511TestUserID,
		Data:    []byte("{}"),
	})

	assert.Equal(t, 1, termCalls)
	assert.Equal(t, []time.Duration{5 * time.Second}, nakDelays,
		"a failed TERM must preserve the existing bounded retry delay")
}

func TestAUD512UnboundPanicMessageDoesNotScheduleNak(t *testing.T) {
	oldTerm := jetStreamTermFunc
	oldNak := jetStreamNakFunc
	t.Cleanup(func() {
		jetStreamTermFunc = oldTerm
		jetStreamNakFunc = oldNak
	})
	nakCalls := 0
	jetStreamTermFunc = func(*nats.Msg) error { return nats.ErrMsgNotBound }
	jetStreamNakFunc = func(*nats.Msg, time.Duration) error { nakCalls++; return nil }

	h := &Hub{}
	h.handleNATSCallbackPanic(context.Background(), &nats.Msg{Subject: "core.subject"}, "core")
	assert.Zero(t, nakCalls, "core NATS messages do not have JetStream redelivery controls")

	// The nil message path cannot be acknowledged, and remains safe to handle.
	h.handleNATSCallbackPanic(context.Background(), nil, "synthetic")
}

func TestAUD512RecoveredPanicAndTermErrorAreNotLogged(t *testing.T) {
	oldUnmarshal := hubJSONUnmarshalFunc
	oldTerm := jetStreamTermFunc
	oldNak := jetStreamNakFunc
	t.Cleanup(func() {
		hubJSONUnmarshalFunc = oldUnmarshal
		jetStreamTermFunc = oldTerm
		jetStreamNakFunc = oldNak
	})

	canary := "aud512-" + rand.Text()
	hubJSONUnmarshalFunc = func([]byte, any) error { panic(canary) }
	termCalls := 0
	nakDelays := make([]time.Duration, 0, 1)
	jetStreamTermFunc = func(*nats.Msg) error {
		termCalls++
		return fmt.Errorf("transport error included canary %s", canary)
	}
	jetStreamNakFunc = func(_ *nats.Msg, delay time.Duration) error {
		nakDelays = append(nakDelays, delay)
		return nil
	}

	var logs strings.Builder
	h := newNatsTestHub(&mockAuthClient{allowed: true}, "internal-secret", 10)
	h.Logger = slog.New(slog.NewTextHandler(&logs, nil))
	h.handleNotifications(context.Background())(&nats.Msg{
		Subject: "notifications." + aud511TestUserID,
		Data:    []byte("{}"),
	})

	logOutput := logs.String()
	assert.NotContains(t, logOutput, canary, "panic and TERM error details may contain credentials")
	assert.NotContains(t, logOutput, "notifications."+aud511TestUserID,
		"the concrete per-user subject must not be logged")
	assert.Contains(t, logOutput, "Recovered panic in NATS callback")
	assert.Contains(t, logOutput, "callback=notifications")
	assert.Contains(t, logOutput, `subject=notifications.*`, "logs use the safe subscription pattern")
	assert.Contains(t, logOutput, "Could not TERM NATS message after callback panic; retry NAK attempted")
	assert.Equal(t, 1, termCalls)
	assert.Equal(t, []time.Duration{5 * time.Second}, nakDelays,
		"a TERM error remains observable and schedules the existing bounded retry")
}

func aud512PanicNilForCompatibilityTest() {
	panic(nil)
}

func TestAUD512PanicNilIsTerminatedWithPanicNilCompatibility(t *testing.T) {
	settings := strings.Split(os.Getenv("GODEBUG"), ",")
	filteredSettings := make([]string, 0, len(settings)+1)
	for _, setting := range settings {
		name, _, _ := strings.Cut(setting, "=")
		if setting != "" && name != "panicnil" {
			filteredSettings = append(filteredSettings, setting)
		}
	}
	filteredSettings = append(filteredSettings, "panicnil=1")
	t.Setenv("GODEBUG", strings.Join(filteredSettings, ","))

	var recovered any
	completed := false
	func() {
		defer func() { recovered = recover() }()
		aud512PanicNilForCompatibilityTest()
		completed = true
	}()
	require.False(t, completed, "panic(nil) must unwind the callback")
	require.Nil(t, recovered, "GODEBUG panicnil=1 must restore nil from recover")

	oldUnmarshal := hubJSONUnmarshalFunc
	oldTerm := jetStreamTermFunc
	oldNak := jetStreamNakFunc
	t.Cleanup(func() {
		hubJSONUnmarshalFunc = oldUnmarshal
		jetStreamTermFunc = oldTerm
		jetStreamNakFunc = oldNak
	})
	hubJSONUnmarshalFunc = func([]byte, any) error {
		aud512PanicNilForCompatibilityTest()
		return nil
	}
	termCalls := 0
	nakCalls := 0
	jetStreamTermFunc = func(*nats.Msg) error { termCalls++; return nil }
	jetStreamNakFunc = func(*nats.Msg, time.Duration) error { nakCalls++; return nil }

	h := newNatsTestHub(&mockAuthClient{allowed: true}, "internal-secret", 10)
	t.Cleanup(h.Stop)
	h.Logger = nil
	h.handleNotifications(context.Background())(&nats.Msg{
		Subject: "notifications." + aud511TestUserID,
		Data:    []byte("{}"),
	})
	assert.Equal(t, 1, termCalls, "panic(nil) must be handled even when recover returns nil")
	assert.Zero(t, nakCalls, "a successful TERM does not schedule another delivery")
}

func TestAUD512NormalCallbackEarlyReturnsDoNotTerminateMessages(t *testing.T) {
	oldTerm := jetStreamTermFunc
	oldNak := jetStreamNakFunc
	t.Cleanup(func() {
		jetStreamTermFunc = oldTerm
		jetStreamNakFunc = oldNak
	})
	termCalls := 0
	nakCalls := 0
	jetStreamTermFunc = func(*nats.Msg) error { termCalls++; return nil }
	jetStreamNakFunc = func(*nats.Msg, time.Duration) error { nakCalls++; return nil }

	handlers := []struct {
		name    string
		subject string
		handler func(*Hub, context.Context) nats.MsgHandler
	}{
		{name: "chat", subject: "chat.room", handler: func(h *Hub, ctx context.Context) nats.MsgHandler {
			return h.handleChatDelivery(ctx, false)
		}},
		{name: "notifications", subject: "notifications." + aud511TestUserID, handler: func(h *Hub, ctx context.Context) nats.MsgHandler {
			return h.handleNotifications(ctx)
		}},
		{name: "cache invalidation", subject: "cache.invalidate", handler: func(h *Hub, ctx context.Context) nats.MsgHandler {
			return h.handleCacheInvalidation(ctx)
		}},
		{name: "control", subject: "ws_hub.control", handler: func(h *Hub, ctx context.Context) nats.MsgHandler {
			return h.handleControlMessage(ctx)
		}},
	}

	for _, test := range handlers {
		t.Run(test.name, func(t *testing.T) {
			ctx, cancel := context.WithCancel(context.Background())
			cancel()
			test.handler(&Hub{}, ctx)(&nats.Msg{Subject: test.subject})
		})
	}

	assert.Zero(t, termCalls, "normal early returns must not be treated as panics")
	assert.Zero(t, nakCalls, "normal early returns must not schedule a retry")
}

func TestAUD512TransientRevocationFailureStillUsesFiveSecondNak(t *testing.T) {
	oldNak := jetStreamNakFunc
	t.Cleanup(func() { jetStreamNakFunc = oldNak })
	nakDelays := make([]time.Duration, 0, 1)
	jetStreamNakFunc = func(_ *nats.Msg, delay time.Duration) error {
		nakDelays = append(nakDelays, delay)
		return nil
	}

	auth := &membershipRecordingAuthClient{
		memberships: map[[2]string]bool{{aud511TestUserID, aud511TestRoomID}: true},
		refreshErr:  errors.New("authorization refresh unavailable"),
	}
	h := newNatsTestHub(auth, "internal-secret", 10)
	payload := signedInvalidationPayload(t, "internal-secret", invalidationData{
		EvictRoom: true,
		RoomID:    aud511TestRoomID,
		UserID:    aud511TestUserID,
	})
	msg := aud511CacheInvalidationMessage("cache.revoke", payload, 42, time.Now())
	h.handleCacheInvalidation(context.Background())(msg)

	assert.Equal(t, []time.Duration{5 * time.Second}, nakDelays,
		"an ordinary authorization failure remains retryable")
	assert.True(t, h.isRoomRevocationPending(aud511TestUserID, aud511TestRoomID),
		"a not-yet-expired revocation failure remains fail-closed")
}
