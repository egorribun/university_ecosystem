package hub

import (
	"context"
	"net/http"
	"net/http/httptest"
	"os"
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestIsValidUUID(t *testing.T) {
	tests := []struct {
		name  string
		input string
		want  bool
	}{
		{"valid v4", "550e8400-e29b-41d4-a716-446655440000", true},
		{"empty", "", false},
		{"garbage", "not-a-uuid", false},
		{"sql injection attempt", "550e8400-e29b-41d4-a716-446655440000; DROP TABLE users", false},
		{"too long", "550e8400-e29b-41d4-a716-446655440000-extra", false},
		{"invalid format", "550e8400e29b41d4a716446655440000", true}, // pragma: allowlist secret
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			assert.Equal(t, tt.want, isValidUUID(tt.input))
		})
	}
}

func TestAuthClientMaxConnsPerHost(t *testing.T) {
	t.Run("default", func(t *testing.T) {
		err := os.Unsetenv("AUTH_CLIENT_MAX_CONNS_PER_HOST")
		require.NoError(t, err)
		assert.Equal(t, 20, authClientMaxConnsPerHost())
	})

	t.Run("override", func(t *testing.T) {
		t.Setenv("AUTH_CLIENT_MAX_CONNS_PER_HOST", "50")
		assert.Equal(t, 50, authClientMaxConnsPerHost())
	})

	t.Run("invalid", func(t *testing.T) {
		t.Setenv("AUTH_CLIENT_MAX_CONNS_PER_HOST", "abc")
		assert.Equal(t, 20, authClientMaxConnsPerHost())
	})
}

func TestInternalAPIAuthClient_Invalidate(t *testing.T) {
	client := NewInternalAPIAuthClient("http://localhost", nil)
	userID := "550e8400-e29b-41d4-a716-446655440000"
	roomID := "660e8400-e29b-41d4-a716-446655441111"

	t.Run("single room invalidation", func(t *testing.T) {
		key := userID + ":" + roomID
		client.cache.Add(key, cacheEntry{allowed: true, expiresAt: time.Now().Add(time.Hour)})

		client.Invalidate(userID, roomID)

		_, ok := client.cache.Get(key)
		assert.False(t, ok, "entry should be removed from cache")
	})

	t.Run("wildcard user invalidation", func(t *testing.T) {
		room1 := "660e8400-e29b-41d4-a716-446655441111"
		room2 := "770e8400-e29b-41d4-a716-446655442222"

		client.cache.Add(userID+":"+room1, cacheEntry{allowed: true, expiresAt: time.Now().Add(time.Hour)})
		client.cache.Add(userID+":"+room2, cacheEntry{allowed: true, expiresAt: time.Now().Add(time.Hour)})
		client.cache.Add("other-user:"+room1, cacheEntry{allowed: true, expiresAt: time.Now().Add(time.Hour)})

		client.Invalidate(userID, "")

		_, ok1 := client.cache.Get(userID + ":" + room1)
		_, ok2 := client.cache.Get(userID + ":" + room2)
		_, ok3 := client.cache.Get("other-user:" + room1)

		assert.False(t, ok1, "room1 for user should be removed")
		assert.False(t, ok2, "room2 for user should be removed")
		assert.True(t, ok3, "other user's entry should remain")
	})
}

func TestInternalAPIAuthClient_CanJoinRoom(t *testing.T) {
	userID := "550e8400-e29b-41d4-a716-446655440000"
	roomID := "660e8400-e29b-41d4-a716-446655441111"

	t.Run("cache hit", func(t *testing.T) {
		client := NewInternalAPIAuthClient("http://localhost", nil)
		key := userID + ":" + roomID
		client.cache.Add(key, cacheEntry{allowed: true, expiresAt: time.Now().Add(time.Hour)})

		assert.True(t, client.CanJoinRoom(context.Background(), userID, roomID))
	})

	t.Run("http request success", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			assert.Equal(t, "/api/v1/chat/check-participant", r.URL.Path)
			assert.Equal(t, userID, r.URL.Query().Get("user_id"))
			assert.Equal(t, roomID, r.URL.Query().Get("room_id"))
			w.WriteHeader(http.StatusOK)
		}))
		defer server.Close()

		client := NewInternalAPIAuthClient(server.URL, nil)
		assert.True(t, client.CanJoinRoom(context.Background(), userID, roomID))

		// Check L1 cache population
		entry, ok := client.cache.Get(userID + ":" + roomID)
		require.True(t, ok)
		assert.True(t, entry.allowed)
	})

	t.Run("http request forbidden", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			w.WriteHeader(http.StatusForbidden)
		}))
		defer server.Close()

		client := NewInternalAPIAuthClient(server.URL, nil)
		assert.False(t, client.CanJoinRoom(context.Background(), userID, roomID))
	})

	t.Run("circuit breaker trips on 5xx", func(t *testing.T) {
		// Mock server that returns 500
		callCount := 0
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			callCount++
			w.WriteHeader(http.StatusInternalServerError)
		}))
		defer server.Close()

		client := NewInternalAPIAuthClient(server.URL, nil)

		// Trip the breaker (threshold is 10 consecutive failures)
		for i := 0; i < 11; i++ {
			client.CanJoinRoom(context.Background(), userID, roomID)
			// Clear cache between attempts to force HTTP call
			client.cache.Remove(userID + ":" + roomID)
		}

		assert.GreaterOrEqual(t, callCount, 10)

		// Next call should fail immediately without hitting the server
		lastCallCount := callCount
		assert.False(t, client.CanJoinRoom(context.Background(), userID, roomID))
		assert.Equal(t, lastCallCount, callCount, "should not hit server when breaker is open")
	})
}

func TestInternalAPIAuthClient_Invalidate_RejectsInvalidIDs(t *testing.T) {
	client := NewInternalAPIAuthClient("http://localhost", nil)
	validUser := "550e8400-e29b-41d4-a716-446655440000"
	validRoom := "660e8400-e29b-41d4-a716-446655441111"

	// A malformed userID is a no-op (guard at the top) — must not panic or touch cache.
	client.cache.Add(validUser+":"+validRoom, cacheEntry{allowed: true, expiresAt: time.Now().Add(time.Hour)})
	client.Invalidate("not-a-uuid", validRoom)
	_, ok := client.cache.Get(validUser + ":" + validRoom)
	assert.True(t, ok, "invalid userID must leave the cache untouched")

	// A malformed roomID (non-wildcard) is also a no-op — the single-room guard.
	client.Invalidate(validUser, "not-a-uuid")
	_, ok = client.cache.Get(validUser + ":" + validRoom)
	assert.True(t, ok, "invalid roomID must leave the cache untouched")
}

func TestInternalAPIAuthClient_CanJoinRoom_RejectsInvalidIDs(t *testing.T) {
	client := NewInternalAPIAuthClient("http://localhost", nil)
	validUser := "550e8400-e29b-41d4-a716-446655440000"
	validRoom := "660e8400-e29b-41d4-a716-446655441111"

	// Malformed IDs are rejected before any cache lookup or HTTP request.
	assert.False(t, client.CanJoinRoom(context.Background(), "not-a-uuid", validRoom))
	assert.False(t, client.CanJoinRoom(context.Background(), validUser, "not-a-uuid"))
}

func TestInternalAPIAuthClient_StartEviction(t *testing.T) {
	client := NewInternalAPIAuthClient("http://localhost", nil)
	client.StartEviction(context.Background())
}
