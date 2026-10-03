package hub

import (
	"context"
	"errors"
	"sync"
	"testing"
	"time"

	"github.com/alicebob/miniredis/v2"
	"github.com/gorilla/websocket"
	goredis "github.com/redis/go-redis/v9"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestWritePumpChecksDurableSessionBeforePrivateDelivery(t *testing.T) {
	for _, test := range []struct {
		name     string
		rejected bool
	}{{"active session", false}, {"missed revocation notice", true}} {
		t.Run(test.name, func(t *testing.T) {
			h := setupTestHub()
			store := miniredis.RunT(t)
			redisClient := goredis.NewClient(&goredis.Options{Addr: store.Addr()})
			t.Cleanup(func() { require.NoError(t, redisClient.Close()) })
			h.revocationRedisClient = redisClient
			h.sessionRevocationCheck = h.checkJTINotRevoked
			client, session := newRevocationTestClient(h, "passive", "user", validSessionJTI, "websocket")
			t.Cleanup(client.cancel)
			client.JoinRoom("private-room")
			if test.rejected {
				require.NoError(t, store.Set(revokedJTIKeyPrefix+validSessionJTI, "1"))
			}
			client.Send <- []byte(`{"type":"new_message","room":"private-room","payload":"secret"}`)
			safeClose(client.Send)
			client.WritePump()
			delivered := false
			for _, write := range session.writes {
				delivered = delivered || write.messageType == websocket.TextMessage
			}
			assert.Equal(t, !test.rejected, delivered)
			assert.Equal(t, test.rejected, client.sessionRevoked.Load())
		})
	}
}

func TestWritePumpFailsClosedWhenDeliveryLookupFails(t *testing.T) {
	h := setupTestHub()
	h.sessionRevocationCheck = func(ctx context.Context, _ string) error {
		deadline, ok := ctx.Deadline()
		assert.True(t, ok)
		assert.LessOrEqual(t, time.Until(deadline), sessionActionRevocationTimeout)
		return errors.New("security store unavailable")
	}
	client, session := newRevocationTestClient(h, "passive", "user", validSessionJTI, "webtransport")
	defer client.cancel()
	client.Send <- []byte(`{"type":"notification","payload":"secret"}`)
	safeClose(client.Send)
	client.WritePump()
	for _, write := range session.writes {
		assert.NotEqual(t, websocket.TextMessage, write.messageType)
	}
	assert.True(t, client.sessionRevoked.Load())
}

func TestPassivePongOnlySessionClosesAfterMissedRevocationNotice(t *testing.T) {
	h := setupTestHub()
	store := miniredis.RunT(t)
	redisClient := goredis.NewClient(&goredis.Options{Addr: store.Addr()})
	t.Cleanup(func() { require.NoError(t, redisClient.Close()) })
	h.revocationRedisClient = redisClient
	h.sessionRevocationCheck = h.checkJTINotRevoked
	server, peer := newConnPair(t)
	client := newClientOn(h, server, "passive-pong", "user")
	client.SessionJTI = validSessionJTI
	h.Unregister = make(chan *Client, 1)
	var pumps sync.WaitGroup
	pumps.Add(2)
	go func() { defer pumps.Done(); client.ReadPump(client.ctx) }()
	go func() { defer pumps.Done(); client.WritePump() }()
	t.Cleanup(func() { client.cancel(); _ = server.Close(); pumps.Wait() })
	client.Send <- []byte(`{"type":"notification","payload":"before revocation"}`)
	require.NoError(t, peer.SetReadDeadline(time.Now().Add(3*time.Second)))
	kind, _, err := peer.ReadMessage()
	require.NoError(t, err)
	require.Equal(t, websocket.TextMessage, kind)
	// Pongs refresh the transport deadline but must never extend authority.
	require.NoError(t, peer.WriteMessage(websocket.PongMessage, nil))
	require.NoError(t, store.Set(revokedJTIKeyPrefix+validSessionJTI, "1"))
	// Deliberately do not publish: the durable tombstone alone must suffice.
	_, _, err = peer.ReadMessage()
	require.True(t, websocket.IsCloseError(err, websocket.ClosePolicyViolation), "expected session close after missed notice, got %v", err)
	pumps.Wait()
	assert.True(t, client.sessionRevoked.Load())
}

func TestClosedRevocationSubscriptionDisconnectsActiveSessions(t *testing.T) {
	h := setupTestHub()
	client, session := newRevocationTestClient(h, "listener-lost", "user", validSessionJTI, "websocket")
	defer client.cancel()
	h.Clients[client.ID] = client
	messages := make(chan *goredis.Message)
	close(messages)
	h.consumeSessionRevocationMessages(context.Background(), messages)
	assert.True(t, session.wasClosed())
	assert.True(t, client.sessionRevoked.Load())
}

func TestUpgradeTicketRequiresCanonicalUnexpiredSessionCutoff(t *testing.T) {
	for _, expiry := range []string{"", "0", "-1", "+9999999999", "09999999999", "9999999999 ", "９９９９９９９９９９", "1e20", "9223372036854775808", "1", "9999999999:extra"} {
		t.Run(expiry, func(t *testing.T) {
			payload := "user:" + validSessionJTI
			if expiry != "" {
				payload += ":" + expiry
			}
			h := hubWithTicketRedis(t, payload)
			_, err := h.validateUpgradeTicketIdentity(context.Background(), validTicket)
			require.Error(t, err)
		})
	}
	t.Run("active session cutoff", func(t *testing.T) {
		h := hubWithTicketRedis(t, "user:"+validSessionJTI+":9999999999")
		_, err := h.validateUpgradeTicketIdentity(context.Background(), validTicket)
		require.NoError(t, err)
	})
}

func TestSessionDeliveryCacheIsBoundedAndCannotExtendExpiry(t *testing.T) {
	h := setupTestHub()
	calls := 0
	h.sessionRevocationCheck = func(context.Context, string) error { calls++; return nil }
	client, _ := newRevocationTestClient(h, "cached", "user", validSessionJTI, "websocket")
	defer client.cancel()
	now := time.Now().Add(time.Minute)
	client.SessionExpiresAt = now.Add(2 * time.Second)
	require.NoError(t, client.authorizeSession(client.ctx, now, true))
	for range 100 {
		require.NoError(t, client.authorizeSession(client.ctx, now.Add(time.Millisecond), true))
	}
	assert.Equal(t, 1, calls, "broadcast bursts share one bounded successful lookup")
	require.NoError(t, client.authorizeSession(client.ctx, now.Add(sessionDeliveryRecheckInterval), true))
	assert.Equal(t, 2, calls)
	require.NoError(t, client.authorizeSession(client.ctx, now.Add(sessionDeliveryRecheckInterval), false))
	assert.Equal(t, 3, calls, "inbound actions never rely on a cached verdict")
	require.Error(t, client.authorizeSession(client.ctx, client.SessionExpiresAt, true))
	assert.Equal(t, 3, calls, "the exact expiry cutoff fails before consulting Redis")
}

func TestExpiredSessionCannotDeliverEvenAfterTombstoneExpires(t *testing.T) {
	h := setupTestHub()
	client, session := newRevocationTestClient(h, "expired", "user", validSessionJTI, "websocket")
	defer client.cancel()
	client.SessionExpiresAt = time.Now().Add(-time.Second)
	client.sessionCheckedUntil = time.Now().Add(time.Hour)
	client.Send <- []byte(`{"type":"notification","payload":"secret"}`)
	safeClose(client.Send)
	client.WritePump()
	for _, write := range session.writes {
		assert.NotEqual(t, websocket.TextMessage, write.messageType)
	}
	assert.True(t, client.sessionRevoked.Load())
}

func TestDeliveryLookupFailureCannotBeReauthorizedBeforeDisconnect(t *testing.T) {
	h := setupTestHub()
	client, _ := newRevocationTestClient(h, "lookup-failed", "user", validSessionJTI, "websocket")
	defer client.cancel()
	h.sessionRevocationCheck = func(context.Context, string) error { return errors.New("lookup failed") }
	require.Error(t, client.authorizeSession(client.ctx, time.Now(), true))
	h.sessionRevocationCheck = func(context.Context, string) error { return nil }
	require.Error(t, client.authorizeSession(client.ctx, time.Now(), true), "an overlapping pump cannot revive a failed-closed session")
}

func TestCancelledSessionCannotUseCachedDeliveryVerdict(t *testing.T) {
	h := setupTestHub()
	client, _ := newRevocationTestClient(h, "cancelled", "user", validSessionJTI, "websocket")
	require.NoError(t, client.authorizeSession(client.ctx, time.Now(), true))
	client.cancel()
	require.Error(t, client.authorizeSession(client.ctx, time.Now(), true))
}

func TestRateLimitedFrameDoesNotAmplifyDurableSessionChecks(t *testing.T) {
	h := setupTestHub()
	h.clientMsgRateLimit = 1
	h.clientMsgRateBurst = 1
	calls := 0
	h.sessionRevocationCheck = func(context.Context, string) error { calls++; return nil }
	client, _ := newRevocationTestClient(h, "rate-limited", "user", validSessionJTI, "websocket", []byte(`{"type":"leave"}`), []byte(`{"type":"leave"}`))
	defer client.cancel()
	assert.True(t, client.processNextMessage(client.ctx))
	assert.True(t, client.processNextMessage(client.ctx))
	assert.Equal(t, 1, calls)
	select {
	case notice := <-client.Send:
		assert.JSONEq(t, `{"type":"rate_limit_exceeded"}`, string(notice))
	default:
		t.Fatal("rate-limited frame must receive the existing rate-limit notice")
	}
}

func TestQueuedDeliveryWithoutTransportIsHarmless(t *testing.T) {
	h := setupTestHub()
	client, _ := newRevocationTestClient(h, "detached", "user", validSessionJTI, "websocket")
	defer client.cancel()
	client.Conn = nil
	require.NoError(t, client.writeQueuedMessage([]byte(`{"type":"notification"}`), true))
}

func TestSessionAuthorizationRefreshesPreContentionTime(t *testing.T) {
	h := setupTestHub()
	client, _ := newRevocationTestClient(h, "stale-clock", "user", validSessionJTI, "websocket")
	defer client.cancel()
	// A caller can wait for sessionCheckMu after capturing its timestamp.
	// Even with a positive cache, that old timestamp cannot extend expiry.
	now := time.Now()
	client.SessionExpiresAt = now.Add(-time.Second)
	client.sessionCheckedUntil = now.Add(time.Hour)
	require.Error(t, client.authorizeSession(client.ctx, now.Add(-time.Minute), true))
	assert.True(t, client.sessionRevoked.Load())
}
