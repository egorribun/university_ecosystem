package hub

import (
	"log/slog"
	"testing"

	"github.com/nats-io/nats.go"
	goredis "github.com/redis/go-redis/v9"
	"github.com/stretchr/testify/require"
	"github.com/university-ecosystem/ws-hub/pkg/config"
)

// mustNewTestHub adapts the error-returning NewHub constructor for fixtures
// whose configuration is known valid. A construction failure fails the test.
func mustNewTestHub(
	tb testing.TB,
	nc *nats.Conn,
	logger *slog.Logger,
	authClient RoomAuthClient,
	cfg *config.Config,
	rdb *goredis.Client,
	revocationClients ...*goredis.Client,
) *Hub {
	tb.Helper()
	h, err := NewHub(nc, logger, authClient, cfg, rdb, revocationClients...)
	require.NoError(tb, err)
	return h
}

// mustNewTestAuthClient adapts NewInternalAPIAuthClientWithToken for fixtures.
func mustNewTestAuthClient(tb testing.TB, baseURL, internalAuthToken string, redisClient *goredis.Client) *InternalAPIAuthClient {
	tb.Helper()
	client, err := NewInternalAPIAuthClientWithToken(baseURL, internalAuthToken, redisClient)
	require.NoError(tb, err)
	return client
}

// mustNewFixtureHub is for fixtures without a testing.TB in scope. Its
// configurations are static and known valid, so a construction error is a
// broken fixture and aborts the test binary rather than being silently ignored.
func mustNewFixtureHub(
	nc *nats.Conn,
	logger *slog.Logger,
	authClient RoomAuthClient,
	cfg *config.Config,
	rdb *goredis.Client,
	revocationClients ...*goredis.Client,
) *Hub {
	h, err := NewHub(nc, logger, authClient, cfg, rdb, revocationClients...)
	if err != nil {
		panic("invalid static ws-hub test fixture: " + err.Error())
	}
	return h
}
