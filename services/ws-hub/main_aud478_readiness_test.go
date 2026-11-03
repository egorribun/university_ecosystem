package main

import (
	"context"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/nats-io/nats.go"
	goredis "github.com/redis/go-redis/v9"
	"github.com/stretchr/testify/require"
	"github.com/university-ecosystem/ws-hub/pkg/config"
	"github.com/university-ecosystem/ws-hub/pkg/hub"
)

// TestAUD478ReadinessFailsWhileRevocationReplayDrains: a replica whose cache.revoke
// replay has not drained is not ready, and becomes ready once the replay clears.
func TestAUD478ReadinessFailsWhileRevocationReplayDrains(t *testing.T) {
	logger := slog.New(slog.NewTextHandler(io.Discard, nil))
	h := mustNewTestHub(t, nil, logger, nil, &config.Config{}, nil, nil)

	oldNATS := healthNATSConnectedFunc
	oldRedisConfigured := healthRedisConfiguredFunc
	oldRedisPing := healthRedisPingFunc
	oldJWKS := healthJWKSReadyFunc
	oldDraining := healthRevocationCatchingUpFunc
	t.Cleanup(func() {
		healthNATSConnectedFunc = oldNATS
		healthRedisConfiguredFunc = oldRedisConfigured
		healthRedisPingFunc = oldRedisPing
		healthJWKSReadyFunc = oldJWKS
		healthRevocationCatchingUpFunc = oldDraining
	})
	healthNATSConnectedFunc = func(*nats.Conn) bool { return true }
	healthRedisConfiguredFunc = func(*goredis.Client) bool { return true }
	healthRedisPingFunc = func(context.Context, *goredis.Client) error { return nil }
	healthJWKSReadyFunc = func(*hub.Hub) bool { return true }
	handler := newReadinessHandler(h, logger, nil, nil, nil)

	healthRevocationCatchingUpFunc = func(*hub.Hub) bool { return true }
	draining := httptest.NewRecorder()
	handler.ServeHTTP(draining, httptest.NewRequest(http.MethodGet, "/health/ready", nil))
	require.Equal(t, http.StatusServiceUnavailable, draining.Code)
	require.Contains(t, draining.Body.String(), `"revocation_replay":"catching up"`)

	healthRevocationCatchingUpFunc = func(*hub.Hub) bool { return false }
	drained := httptest.NewRecorder()
	handler.ServeHTTP(drained, httptest.NewRequest(http.MethodGet, "/health/ready", nil))
	require.Equal(t, http.StatusOK, drained.Code)
	require.NotContains(t, drained.Body.String(), "revocation_replay")
}
