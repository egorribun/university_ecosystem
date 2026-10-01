// Hub ticket, presence, Redis, and shutdown runtime contracts.
package hub

import (
	"context"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/alicebob/miniredis/v2"
	"github.com/google/uuid"
	"github.com/redis/go-redis/v9"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"github.com/university-ecosystem/ws-hub/pkg/config"
)

// TestValidateUpgradeTicket_Errors verifies all validation failure paths in validateUpgradeTicket.
func TestValidateUpgradeTicketIdentity_Errors(t *testing.T) {
	logger := newTestLogger()

	t.Run("redis nil", func(t *testing.T) {
		h := trackTestHub(NewHub(nil, logger, nil, &configHubPlaceholder, nil))
		_, err := h.validateUpgradeTicketIdentity(context.Background(), strings.Repeat("a", 64))
		assert.Error(t, err)
		assert.Contains(t, err.Error(), "redis not available")
	})

	t.Run("invalid length", func(t *testing.T) {
		mr := miniredis.RunT(t)
		rClient := redis.NewClient(&redis.Options{Addr: mr.Addr()})
		defer func() { require.NoError(t, rClient.Close()) }()
		h := trackTestHub(NewHub(nil, logger, nil, &configHubPlaceholder, rClient))

		_, err := h.validateUpgradeTicketIdentity(context.Background(), "short")
		assert.Error(t, err)
		assert.Contains(t, err.Error(), "invalid ticket length")
	})

	t.Run("invalid charset", func(t *testing.T) {
		mr := miniredis.RunT(t)
		rClient := redis.NewClient(&redis.Options{Addr: mr.Addr()})
		defer func() { require.NoError(t, rClient.Close()) }()
		h := trackTestHub(NewHub(nil, logger, nil, &configHubPlaceholder, rClient))

		invalidTicket := strings.Repeat("a", 63) + "Z" // Z is not lowercase hex
		_, err := h.validateUpgradeTicketIdentity(context.Background(), invalidTicket)
		assert.Error(t, err)
		assert.Contains(t, err.Error(), "invalid ticket charset")
	})

	t.Run("ticket not found", func(t *testing.T) {
		mr := miniredis.RunT(t)
		rClient := redis.NewClient(&redis.Options{Addr: mr.Addr()})
		defer func() { require.NoError(t, rClient.Close()) }()
		h := trackTestHub(NewHub(nil, logger, nil, &configHubPlaceholder, rClient))

		validTicket := strings.Repeat("a", 64)
		_, err := h.validateUpgradeTicketIdentity(context.Background(), validTicket)
		assert.Error(t, err)
		assert.Contains(t, err.Error(), "ticket not found")
	})

	t.Run("redis error", func(t *testing.T) {
		mr := miniredis.RunT(t)
		rClient := redis.NewClient(&redis.Options{Addr: mr.Addr()})
		rClient.Close() //nolint:errcheck,gosec // G104: intentional close to trigger redis error in next call
		h := trackTestHub(NewHub(nil, logger, nil, &configHubPlaceholder, rClient))

		validTicket := strings.Repeat("a", 64)
		_, err := h.validateUpgradeTicketIdentity(context.Background(), validTicket)
		assert.Error(t, err)
		assert.Contains(t, err.Error(), "redis error")
	})

	t.Run("malformed ticket payload - no colon", func(t *testing.T) {
		mr := miniredis.RunT(t)
		rClient := redis.NewClient(&redis.Options{Addr: mr.Addr()})
		defer func() { require.NoError(t, rClient.Close()) }()
		h := trackTestHub(NewHub(nil, logger, nil, &configHubPlaceholder, rClient))

		ticket := strings.Repeat("a", 64)
		require.NoError(t, mr.Set("ott:ws:"+ticket, "nocolon"))

		_, err := h.validateUpgradeTicketIdentity(context.Background(), ticket)
		require.Error(t, err)
		assert.Contains(t, err.Error(), "malformed ticket payload")
	})

	t.Run("malformed ticket payload - colon at start", func(t *testing.T) {
		mr := miniredis.RunT(t)
		rClient := redis.NewClient(&redis.Options{Addr: mr.Addr()})
		defer func() { require.NoError(t, rClient.Close()) }()
		h := trackTestHub(NewHub(nil, logger, nil, &configHubPlaceholder, rClient))

		ticket := strings.Repeat("a", 64)
		require.NoError(t, mr.Set("ott:ws:"+ticket, ":jti"))

		_, err := h.validateUpgradeTicketIdentity(context.Background(), ticket)
		assert.Error(t, err)
		assert.Contains(t, err.Error(), "malformed ticket payload")
	})

	t.Run("malformed ticket payload - colon at end", func(t *testing.T) {
		mr := miniredis.RunT(t)
		rClient := redis.NewClient(&redis.Options{Addr: mr.Addr()})
		defer func() { require.NoError(t, rClient.Close()) }()
		h := trackTestHub(NewHub(nil, logger, nil, &configHubPlaceholder, rClient))

		ticket := strings.Repeat("a", 64)
		require.NoError(t, mr.Set("ott:ws:"+ticket, "user-id:"))

		_, err := h.validateUpgradeTicketIdentity(context.Background(), ticket)
		assert.Error(t, err)
		assert.Contains(t, err.Error(), "malformed ticket payload")
	})
}

// TestInternalAPIAuthClient_DoRequest_Errors verifies error branches in doRequest.
func TestInternalAPIAuthClient_DoRequest_Errors(t *testing.T) {
	t.Run("client request timeout", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			time.Sleep(2 * time.Second) // trigger httpClient timeout (3s client-level, but 1.5s call-level!)
			w.WriteHeader(http.StatusOK)
		}))
		defer server.Close()

		auth := NewInternalAPIAuthClientWithToken(server.URL, "", nil)
		allowed := auth.CanJoinRoom(context.Background(), uuid.NewString(), uuid.NewString())
		assert.False(t, allowed) // Should fail-closed on timeout error
	})

	t.Run("http 500 error", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			w.WriteHeader(http.StatusInternalServerError)
		}))
		defer server.Close()

		auth := NewInternalAPIAuthClientWithToken(server.URL, "", nil)
		allowed := auth.CanJoinRoom(context.Background(), uuid.NewString(), uuid.NewString())
		assert.False(t, allowed)
	})

	t.Run("invalid UUID validation fast path", func(t *testing.T) {
		auth := NewInternalAPIAuthClientWithToken("http://localhost", "", nil)
		allowed := auth.CanJoinRoom(context.Background(), "invalid-user-uuid", uuid.NewString())
		assert.False(t, allowed)

		allowed = auth.CanJoinRoom(context.Background(), uuid.NewString(), "invalid-room-uuid")
		assert.False(t, allowed)
	})
}

// TestInternalAPIAuthClientInvalidateEdgeCases verifies invalidation edge cases.
func TestInternalAPIAuthClientInvalidateEdgeCases(t *testing.T) {
	mr := miniredis.RunT(t)
	rClient := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	defer func() { require.NoError(t, rClient.Close()) }()

	auth := NewInternalAPIAuthClientWithToken("http://localhost", "", rClient)

	t.Run("invalid user UUID", func(t *testing.T) {
		assert.NotPanics(t, func() {
			auth.Invalidate("invalid-user-uuid", uuid.NewString())
		})
	})

	t.Run("invalid room UUID in single room mode", func(t *testing.T) {
		assert.NotPanics(t, func() {
			auth.Invalidate(uuid.NewString(), "invalid-room-uuid")
		})
	})

	t.Run("wildcard mode with miniredis", func(t *testing.T) {
		userID := uuid.NewString()
		auth.Invalidate(userID, "") // should scan and delete
	})
}

// Helper placeholders to satisfy hub package structs
var configHubPlaceholder = config.Config{
	MaxClients:          10,
	BroadcastBufferSize: 10,
	BroadcastWorkers:    1,
	ClientMsgRateLimit:  10,
	ClientMsgRateBurst:  10,
}

func newTestLogger() *slog.Logger {
	return slog.New(slog.NewTextHandler(io.Discard, nil))
}
