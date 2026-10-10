package hub

// Coverage tests (testing session 16) for the Redis L2 paths in the internal-API
// auth client. The existing auth_client_test.go builds every client with a nil
// *redis.Client, so the L2 read-hit / write-back / Invalidate-delete branches in
// CanJoinRoom + Invalidate never executed. miniredis gives a real go-redis L2
// without Docker. Also covers StartEviction (a documented no-op since Wave 7).

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/alicebob/miniredis/v2"
	"github.com/redis/go-redis/v9"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

const (
	rdUser  = "11111111-1111-1111-1111-111111111111"
	rdRoom  = "22222222-2222-2222-2222-222222222222"
	rdRoom2 = "33333333-3333-3333-3333-333333333333"
)

func newMiniredisClient(t *testing.T) (*miniredis.Miniredis, *redis.Client) {
	t.Helper()
	mr := miniredis.RunT(t)
	rc := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	t.Cleanup(func() { _ = rc.Close() }) //nolint:errcheck // best-effort cleanup
	return mr, rc
}

func TestStartEviction_NoOpIsSafe(t *testing.T) {
	c := NewInternalAPIAuthClientWithToken("http://localhost", "", nil)
	c.StartEviction(context.Background()) // no-op since Wave 7; just exercises it
}

func TestCanJoinRoom_RedisL2Hit(t *testing.T) {
	mr, rc := newMiniredisClient(t)
	require.NoError(t, mr.Set("auth:perms:"+rdUser+":"+rdRoom, "1"))

	c := NewInternalAPIAuthClientWithToken("http://unused.invalid", "", rc)
	assert.True(t, c.CanJoinRoom(context.Background(), rdUser, rdRoom),
		"L2 hit of \"1\" must allow without an HTTP call")

	// L1 must be populated from L2.
	entry, ok := c.cache.Get(rdUser + ":" + rdRoom)
	require.True(t, ok)
	assert.True(t, entry.allowed)
}

func TestCanJoinRoom_SlowPathWritesRedisL2(t *testing.T) {
	mr, rc := newMiniredisClient(t)
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusOK) // backend says allowed
	}))
	defer server.Close()

	c := NewInternalAPIAuthClientWithToken(server.URL, "", rc)
	assert.True(t, c.CanJoinRoom(context.Background(), rdUser, rdRoom))

	// The slow path must write the decision back to L2.
	val, err := mr.Get("auth:perms:" + rdUser + ":" + rdRoom)
	require.NoError(t, err)
	assert.Equal(t, "1", val)
}

func TestInvalidate_SingleRoomDeletesRedisL2(t *testing.T) {
	mr, rc := newMiniredisClient(t)
	key := "auth:perms:" + rdUser + ":" + rdRoom
	require.NoError(t, mr.Set(key, "1"))

	c := NewInternalAPIAuthClientWithToken("http://localhost", "", rc)
	c.Invalidate(rdUser, rdRoom)
	assert.False(t, mr.Exists(key), "single-room invalidation must delete the L2 key")
}

func TestInvalidate_WildcardDeletesAllUserRedisL2(t *testing.T) {
	mr, rc := newMiniredisClient(t)
	k1 := "auth:perms:" + rdUser + ":" + rdRoom
	k2 := "auth:perms:" + rdUser + ":" + rdRoom2
	require.NoError(t, mr.Set(k1, "1"))
	require.NoError(t, mr.Set(k2, "0"))

	c := NewInternalAPIAuthClientWithToken("http://localhost", "", rc)
	c.Invalidate(rdUser, "") // wildcard: SCAN + DEL every auth:perms:<user>:* key

	assert.False(t, mr.Exists(k1))
	assert.False(t, mr.Exists(k2))
}

func TestRefreshRoomAuthorizationBypassesStaleCaches(t *testing.T) {
	mr, rc := newMiniredisClient(t)
	key := "auth:perms:" + rdUser + ":" + rdRoom
	require.NoError(t, mr.Set(key, "1"))
	var requests int
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		requests++
		w.WriteHeader(http.StatusForbidden)
	}))
	defer server.Close()

	c := NewInternalAPIAuthClientWithToken(server.URL, "", rc)
	c.cache.Add(rdUser+":"+rdRoom, cacheEntry{allowed: true, expiresAt: time.Now().Add(time.Minute)})

	allowed, err := c.RefreshRoomAuthorization(context.Background(), rdUser, rdRoom)

	require.NoError(t, err)
	assert.False(t, allowed, "refresh must use the current backend authorization")
	assert.Equal(t, 1, requests, "refresh must bypass both cached allow entries")
	assert.False(t, mr.Exists(key), "fresh authorization must not leave the stale L2 entry")
}

func TestRefreshRoomAuthorizationRejectsInvalidIdentifiers(t *testing.T) {
	backendRequests := 0
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		backendRequests++
		w.WriteHeader(http.StatusOK)
	}))
	defer server.Close()

	client := NewInternalAPIAuthClientWithToken(server.URL, "", nil)
	for _, testCase := range []struct {
		name   string
		userID string
		roomID string
	}{
		{name: "invalid user id", userID: "not-a-uuid", roomID: rdRoom},
		{name: "invalid room id", userID: rdUser, roomID: "not-a-uuid"},
	} {
		t.Run(testCase.name, func(t *testing.T) {
			allowed, err := client.RefreshRoomAuthorization(
				context.Background(), testCase.userID, testCase.roomID,
			)

			assert.Error(t, err)
			assert.False(t, allowed)
		})
	}
	assert.Zero(t, backendRequests, "invalid identifiers must be rejected before contacting the backend")
}

func TestRefreshRoomAuthorizationDoesNotConfirmFailedRedisInvalidation(t *testing.T) {
	mr, rc := newMiniredisClient(t)
	require.NoError(t, mr.Set("auth:perms:"+rdUser+":"+rdRoom, "1"))
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		t.Error("backend must not be queried until stale Redis permission is deleted")
		w.WriteHeader(http.StatusForbidden)
	}))
	defer server.Close()

	c := NewInternalAPIAuthClientWithToken(server.URL, "", rc)
	mr.Close()

	allowed, err := c.RefreshRoomAuthorization(context.Background(), rdUser, rdRoom)

	assert.Error(t, err, "failed L2 invalidation must leave the revocation unconfirmed")
	assert.False(t, allowed)
}
