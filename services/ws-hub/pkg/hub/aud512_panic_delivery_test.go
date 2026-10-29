package hub

import (
	"context"
	"crypto/rand"
	"errors"
	"log/slog"
	"os"
	"strings"
	"testing"
	"time"

	"github.com/nats-io/nats.go"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

type aud512RefreshAuth struct {
	panicNext    bool
	panicValue   any
	refreshErr   error
	allowed      bool
	refreshCalls int
	joinCalls    int
}

func (a *aud512RefreshAuth) CanJoinRoom(context.Context, string, string) bool {
	a.joinCalls++
	return a.allowed
}

func (a *aud512RefreshAuth) Invalidate(string, string) {}

func (a *aud512RefreshAuth) RefreshRoomAuthorization(context.Context, string, string) (bool, error) {
	a.refreshCalls++
	if a.panicNext {
		a.panicNext = false
		panic(a.panicValue)
	}
	return a.allowed, a.refreshErr
}

type aud512InvalidateAuth struct {
	cached          bool
	panicNext       bool
	panicValue      any
	invalidateCalls int
}

func (a *aud512InvalidateAuth) CanJoinRoom(context.Context, string, string) bool {
	return a.cached
}

func (a *aud512InvalidateAuth) Invalidate(string, string) {
	a.invalidateCalls++
	if a.panicNext {
		a.panicNext = false
		panic(a.panicValue)
	}
	a.cached = false
}

func aud512UseNilPanicCompatibility(t *testing.T) {
	t.Helper()
	var settings []string
	for _, setting := range strings.Split(os.Getenv("GODEBUG"), ",") {
		name, _, _ := strings.Cut(setting, "=")
		if setting != "" && name != "panicnil" {
			settings = append(settings, setting)
		}
	}
	t.Setenv("GODEBUG", strings.Join(append(settings, "panicnil=1"), ","))
	var recovered any
	completed := false
	func() {
		defer func() { recovered = recover() }()
		aud512PanicNilForCompatibilityTest()
		completed = true
	}()
	require.False(t, completed, "panic(nil) must unwind")
	require.Nil(t, recovered, "compatibility mode must make recover return nil")
}

func TestAUD512RefreshPanicRetainsRevocationAndAllowsRetry(t *testing.T) {
	t.Run("panic value", func(t *testing.T) {
		canary := rand.Text()
		aud512AssertRefreshPanicRetry(t, canary, canary)
	})
	t.Run("nil panic value under compatibility mode", func(t *testing.T) {
		aud512UseNilPanicCompatibility(t)
		aud512AssertRefreshPanicRetry(t, nil, rand.Text())
	})
}

func aud512AssertRefreshPanicRetry(t *testing.T, panicValue any, panicCanary string) {
	t.Helper()
	oldAck, oldNak, oldTerm := jetStreamAckFunc, jetStreamNakFunc, jetStreamTermFunc
	t.Cleanup(func() {
		jetStreamAckFunc, jetStreamNakFunc, jetStreamTermFunc = oldAck, oldNak, oldTerm
	})
	var dispositions []string
	jetStreamAckFunc = func(*nats.Msg) error {
		dispositions = append(dispositions, "ack")
		return nil
	}
	jetStreamNakFunc = func(_ *nats.Msg, delay time.Duration) error {
		assert.Equal(t, 5*time.Second, delay)
		dispositions = append(dispositions, "nak")
		return nil
	}
	jetStreamTermFunc = func(*nats.Msg) error {
		dispositions = append(dispositions, "term")
		return nil
	}

	secret := rand.Text()
	auth := &aud512RefreshAuth{panicNext: true, panicValue: panicValue, allowed: true}
	h := newNatsTestHub(auth, secret, 10)
	var logs strings.Builder
	h.Logger = slog.New(slog.NewTextHandler(&logs, nil))
	ctx := context.Background()
	member := &Client{ID: "aud512-member", UserID: aud511TestUserID, Hub: h,
		Rooms: make(map[string]bool), Send: make(chan []byte, 1), ctx: ctx}
	member.JoinRoom(aud511TestRoomID)
	require.True(t, member.isInRoom(aud511TestRoomID))

	// Keep the keyed entry alive as a concurrent join/write would. Losing the
	// revocation count on panic must not strand that other reference forever.
	retained := h.roomMembershipLock(aud511TestUserID, aud511TestRoomID)
	t.Cleanup(retained.release)
	payload := signedInvalidationPayload(t, secret, invalidationData{
		EvictRoom: true,
		RoomID:    aud511TestRoomID,
		UserID:    aud511TestUserID,
	})
	handler := h.handleCacheInvalidation(ctx)
	msg := aud511CacheInvalidationMessage(payload, 42, time.Now())
	handler(msg)

	assert.Equal(t, []string{"nak"}, dispositions, "an unconfirmed revocation is retryable, not acknowledged or terminated")
	assert.False(t, member.isInRoom(aud511TestRoomID), "an unconfirmed revocation must remove the active member")
	assert.True(t, h.isRoomRevocationPending(aud511TestUserID, aud511TestRoomID), "the temporary fail-closed marker must survive")
	assert.NotContains(t, logs.String(), panicCanary, "panic values may contain sensitive data")
	retained.Lock()
	remainingRevocations := retained.entry.revocations
	retained.unlockRetained()
	assert.Zero(t, remainingRevocations, "the completed callback must release its revocation barrier")

	// A distinct client must pass the released barrier and reach current
	// authority. If the refresh is still unavailable, it must remain denied.
	auth.refreshErr = errors.New("authorization unavailable")
	other := &Client{ID: "aud512-other", UserID: aud511TestUserID, Hub: h,
		Rooms: make(map[string]bool), Send: make(chan []byte, 1), ctx: ctx}
	joinCtx, cancel := context.WithTimeout(ctx, 250*time.Millisecond)
	defer cancel()
	assert.False(t, other.authorizeRoomJoin(joinCtx, aud511TestRoomID, func() bool { return true }))
	assert.Equal(t, 2, auth.refreshCalls, "the join must reach authority rather than wait on a leaked barrier")
	assert.True(t, h.isRoomRevocationPending(aud511TestUserID, aud511TestRoomID))

	// The same signed event can then be redelivered after authority recovers.
	auth.refreshErr = nil
	auth.allowed = false
	handler(msg)
	assert.Equal(t, []string{"nak", "ack"}, dispositions)
	assert.Equal(t, 3, auth.refreshCalls)
	assert.False(t, h.isRoomRevocationPending(aud511TestUserID, aud511TestRoomID))
	assert.False(t, member.isInRoom(aud511TestRoomID))
	lastJoinCtx, cancelLastJoin := context.WithTimeout(ctx, 250*time.Millisecond)
	defer cancelLastJoin()
	assert.False(t, other.authorizeRoomJoin(lastJoinCtx, aud511TestRoomID, func() bool { return true }),
		"current authority still denies a removed user after the event is acknowledged")
	assert.Equal(t, 1, auth.joinCalls, "the retry must leave the join barrier usable")
}

func TestAUD512FailedPanicTerminationNeverAcknowledges(t *testing.T) {
	oldUnmarshal, oldAck, oldNak, oldTerm := hubJSONUnmarshalFunc, jetStreamAckFunc, jetStreamNakFunc, jetStreamTermFunc
	t.Cleanup(func() {
		hubJSONUnmarshalFunc, jetStreamAckFunc, jetStreamNakFunc, jetStreamTermFunc = oldUnmarshal, oldAck, oldNak, oldTerm
	})
	hubJSONUnmarshalFunc = func([]byte, any) error { panic("decoder failure") }
	for _, nakFails := range []bool{false, true} {
		t.Run(map[bool]string{false: "nak succeeds", true: "nak fails"}[nakFails], func(t *testing.T) {
			var dispositions []string
			jetStreamAckFunc = func(*nats.Msg) error {
				dispositions = append(dispositions, "ack")
				return nil
			}
			jetStreamTermFunc = func(*nats.Msg) error {
				dispositions = append(dispositions, "term")
				return errors.New("termination unavailable")
			}
			jetStreamNakFunc = func(_ *nats.Msg, delay time.Duration) error {
				assert.Equal(t, 5*time.Second, delay)
				dispositions = append(dispositions, "nak")
				if nakFails {
					return errors.New("retry unavailable")
				}
				return nil
			}
			h := newNatsTestHub(&mockAuthClient{allowed: true}, rand.Text(), 10)
			h.handleNotifications(context.Background())(&nats.Msg{Subject: "notifications.user", Data: []byte("{}")})
			assert.Equal(t, []string{"term", "nak"}, dispositions, "failed disposition must never produce a false ACK")
		})
	}
}

func TestAUD512ValidCacheInvalidationPanicRetriesWithoutAcknowledging(t *testing.T) {
	t.Run("panic value", func(t *testing.T) {
		canary := rand.Text()
		aud512AssertInvalidationPanicRetry(t, canary, canary)
	})
	t.Run("nil panic value under compatibility mode", func(t *testing.T) {
		aud512UseNilPanicCompatibility(t)
		aud512AssertInvalidationPanicRetry(t, nil, rand.Text())
	})
}

func aud512AssertInvalidationPanicRetry(t *testing.T, panicValue any, panicCanary string) {
	t.Helper()
	auth := &aud512InvalidateAuth{cached: true, panicNext: true, panicValue: panicValue}
	oldAck, oldNak, oldTerm := jetStreamAckFunc, jetStreamNakFunc, jetStreamTermFunc
	t.Cleanup(func() {
		jetStreamAckFunc, jetStreamNakFunc, jetStreamTermFunc = oldAck, oldNak, oldTerm
	})
	var dispositions []string
	jetStreamAckFunc = func(*nats.Msg) error {
		assert.False(t, auth.cached, "the cache must be invalidated before ACK")
		dispositions = append(dispositions, "ack")
		return nil
	}
	jetStreamNakFunc = func(_ *nats.Msg, delay time.Duration) error {
		assert.Equal(t, 5*time.Second, delay)
		dispositions = append(dispositions, "nak")
		return nil
	}
	jetStreamTermFunc = func(*nats.Msg) error {
		dispositions = append(dispositions, "term")
		return nil
	}
	secret := rand.Text()
	h := newNatsTestHub(auth, secret, 10)
	var logs strings.Builder
	h.Logger = slog.New(slog.NewTextHandler(&logs, nil))
	ctx := context.Background()
	msg := aud511CacheInvalidationMessage(signedInvalidationPayload(t, secret, invalidationData{
		RoomID: aud511TestRoomID,
		UserID: aud511TestUserID,
	}), 43, time.Now())
	handler := h.handleCacheInvalidation(ctx)

	handler(msg)
	assert.Equal(t, []string{"nak"}, dispositions, "an unapplied valid invalidation must be retried")
	assert.True(t, auth.CanJoinRoom(ctx, aud511TestUserID, aud511TestRoomID), "the panic left the cached authorization intact")
	assert.NotContains(t, logs.String(), panicCanary)
	handler(msg)
	assert.Equal(t, []string{"nak", "ack"}, dispositions)
	assert.False(t, auth.CanJoinRoom(ctx, aud511TestUserID, aud511TestRoomID), "retry must invalidate the cache before ACK")
	assert.Equal(t, 2, auth.invalidateCalls)
}

func TestAUD512InvalidRevocationDisposition(t *testing.T) {
	oldAck, oldNak, oldTerm := jetStreamAckFunc, jetStreamNakFunc, jetStreamTermFunc
	t.Cleanup(func() {
		jetStreamAckFunc, jetStreamNakFunc, jetStreamTermFunc = oldAck, oldNak, oldTerm
	})
	tests := []struct {
		name    string
		termErr error
		nakErr  error
		want    []string
	}{
		{name: "successful termination", want: []string{"term"}},
		{name: "termination unavailable", termErr: errors.New("termination unavailable"), want: []string{"term", "nak"}},
		{name: "termination and retry unavailable", termErr: errors.New("termination unavailable"), nakErr: errors.New("retry unavailable"), want: []string{"term", "nak"}},
		{name: "unbound message", termErr: nats.ErrMsgNotBound, want: []string{"term"}},
		{name: "core message", termErr: nats.ErrNotJSMessage, want: []string{"term"}},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			var dispositions []string
			jetStreamAckFunc = func(*nats.Msg) error {
				dispositions = append(dispositions, "ack")
				return nil
			}
			jetStreamTermFunc = func(*nats.Msg) error {
				dispositions = append(dispositions, "term")
				return tc.termErr
			}
			jetStreamNakFunc = func(_ *nats.Msg, delay time.Duration) error {
				assert.Equal(t, 5*time.Second, delay)
				dispositions = append(dispositions, "nak")
				return tc.nakErr
			}
			h := newNatsTestHub(&mockAuthClient{allowed: true}, rand.Text(), 10)
			h.handleCacheInvalidation(context.Background())(&nats.Msg{Subject: "cache.invalidate", Data: []byte("{")})
			assert.Equal(t, tc.want, dispositions,
				"a rejected payload is permanent, but a failed TERM needs delayed redelivery and must not ACK")
		})
	}
}
