package hub

import (
	"context"
	"net/http"
	"net/http/httptest"
	"sync/atomic"
	"testing"
	"time"

	"github.com/stretchr/testify/require"
)

func TestRoomAuthorizationL1CannotExtendRemainingRedisTTL(t *testing.T) {
	for _, value := range []string{"0", "1"} {
		t.Run(value, func(t *testing.T) {
			mr, rc := newMiniredisClient(t)
			key := "auth:perms:" + rdUser + ":" + rdRoom
			require.NoError(t, mr.Set(key, value))
			mr.SetTTL(key, authCacheTTL)
			mr.FastForward(authCacheTTL - 10*time.Second)
			c := mustNewTestAuthClient(t, "http://127.0.0.1:1", "", rc)
			started := time.Now()

			allowed := c.CanJoinRoom(context.Background(), rdUser, rdRoom)

			require.Equal(t, value == "1", allowed)
			entry, ok := c.cache.Get(rdUser + ":" + rdRoom)
			require.True(t, ok)
			require.True(t, entry.expiresAt.After(started))
			require.False(t, entry.expiresAt.After(started.Add(10*time.Second)),
				"an L2 hit must retain its remaining lease, not restart sixty seconds")
			require.Equal(t, 10*time.Second, mr.TTL(key), "reads must not refresh L2")
		})
	}
}

func TestRoomAuthorizationL2WithoutLiveLeaseRequiresBackend(t *testing.T) {
	for _, state := range []string{"persistent", "expired", "wrong-type", "redis-error"} {
		t.Run(state, func(t *testing.T) {
			mr, rc := newMiniredisClient(t)
			key := "auth:perms:" + rdUser + ":" + rdRoom
			if state == "wrong-type" {
				_, err := rc.LPush(context.Background(), key, "1").Result()
				require.NoError(t, err)
			} else {
				require.NoError(t, mr.Set(key, "1"))
				if state == "expired" {
					mr.SetTTL(key, time.Second)
					mr.FastForward(time.Second)
				}
			}
			if state == "redis-error" {
				mr.SetError("NOPERM simulated transaction permission failure")
			}
			var calls atomic.Int32
			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
				calls.Add(1)
				w.WriteHeader(http.StatusForbidden)
			}))
			t.Cleanup(server.Close)
			c := mustNewTestAuthClient(t, server.URL, "", rc)

			require.False(t, c.CanJoinRoom(context.Background(), rdUser, rdRoom))
			require.EqualValues(t, 1, calls.Load(), "unbounded or invalid shared data is not authorization")
			entry, ok := c.cache.Get(rdUser + ":" + rdRoom)
			require.True(t, ok)
			require.False(t, entry.allowed, "only the fresh backend denial may populate L1")
		})
	}
}

func TestRoomAuthorizationL1CapsUnexpectedlyLongRedisLease(t *testing.T) {
	mr, rc := newMiniredisClient(t)
	key := "auth:perms:" + rdUser + ":" + rdRoom
	require.NoError(t, mr.Set(key, "1"))
	mr.SetTTL(key, 10*authCacheTTL)
	c := mustNewTestAuthClient(t, "http://127.0.0.1:1", "", rc)
	started := time.Now()

	require.True(t, c.CanJoinRoom(context.Background(), rdUser, rdRoom))

	entry, ok := c.cache.Get(rdUser + ":" + rdRoom)
	require.True(t, ok)
	require.False(t, entry.expiresAt.After(started.Add(authCacheTTL)))
}
