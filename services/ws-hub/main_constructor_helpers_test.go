package main

import (
	"log/slog"
	"testing"

	"github.com/nats-io/nats.go"
	"github.com/redis/go-redis/v9"
	"github.com/stretchr/testify/require"
	"github.com/university-ecosystem/ws-hub/pkg/config"
	"github.com/university-ecosystem/ws-hub/pkg/hub"
)

// mustNewTestHub adapts the error-returning hub.NewHub constructor for fixtures
// whose configuration is known valid. A construction failure fails the test.
func mustNewTestHub(
	tb testing.TB,
	nc *nats.Conn,
	logger *slog.Logger,
	authClient hub.RoomAuthClient,
	cfg *config.Config,
	rdb *redis.Client,
	revocationClients ...*redis.Client,
) *hub.Hub {
	tb.Helper()
	h, err := hub.NewHub(nc, logger, authClient, cfg, rdb, revocationClients...)
	require.NoError(tb, err)
	return h
}

// mustNewTestAuthClient adapts hub.NewInternalAPIAuthClientWithToken for fixtures.
func mustNewTestAuthClient(tb testing.TB, baseURL, internalAuthToken string, redisClient *redis.Client) *hub.InternalAPIAuthClient {
	tb.Helper()
	client, err := hub.NewInternalAPIAuthClientWithToken(baseURL, internalAuthToken, redisClient)
	require.NoError(tb, err)
	return client
}
