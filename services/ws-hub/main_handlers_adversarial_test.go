package main

import (
	"context"
	"errors"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"sync"
	"testing"
	"time"

	"github.com/alicebob/miniredis/v2"
	"github.com/nats-io/nats.go"
	goredis "github.com/redis/go-redis/v9"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"github.com/university-ecosystem/ws-hub/pkg/config"
	"github.com/university-ecosystem/ws-hub/pkg/hub"
)

func TestAdversarial_ReadinessHandler_StressAndFailureModes(t *testing.T) {
	mr := miniredis.RunT(t)
	rdb := goredis.NewClient(&goredis.Options{Addr: mr.Addr()})
	t.Cleanup(func() {
		require.NoError(t, rdb.Close())
	})

	revMr := miniredis.RunT(t)
	revRdb := goredis.NewClient(&goredis.Options{Addr: revMr.Addr()})
	t.Cleanup(func() {
		require.NoError(t, revRdb.Close())
	})

	logger := slog.New(slog.NewTextHandler(io.Discard, nil))
	h := hub.NewHub(nil, logger, nil, &config.Config{}, rdb, revRdb)

	oldNats := healthNATSConnectedFunc
	oldJWKS := healthJWKSReadyFunc
	t.Cleanup(func() {
		healthNATSConnectedFunc = oldNats
		healthJWKSReadyFunc = oldJWKS
	})
	healthNATSConnectedFunc = func(*nats.Conn) bool { return true }
	healthJWKSReadyFunc = func(*hub.Hub) bool { return true }

	handler := newReadinessHandler(h, logger, nil, rdb, revRdb)

	// 1. Healthy state under concurrent load
	concurrency := 40
	var wg sync.WaitGroup
	wg.Add(concurrency)

	for i := 0; i < concurrency; i++ {
		go func() {
			defer wg.Done()
			req := httptest.NewRequest(http.MethodGet, "/health/ready", nil)
			rec := httptest.NewRecorder()
			handler.ServeHTTP(rec, req)
			assert.Equal(t, http.StatusOK, rec.Code)
			assert.Contains(t, rec.Body.String(), `"status":"ready"`)
		}()
	}
	wg.Wait()

	// 2. Unhealthy state when primary Redis fails
	mr.Close()
	// Create fresh handler to bypass cache
	unhealthyHandler := newReadinessHandler(h, logger, nil, rdb, revRdb)
	req2 := httptest.NewRequest(http.MethodGet, "/health/ready", nil)
	rec2 := httptest.NewRecorder()
	unhealthyHandler.ServeHTTP(rec2, req2)
	assert.Equal(t, http.StatusServiceUnavailable, rec2.Code)
	assert.Contains(t, rec2.Body.String(), `"status":"degraded"`)
}

func TestAdversarial_RedisPingCache_TTLAndConcurrency(t *testing.T) {
	mr := miniredis.RunT(t)
	rdb := goredis.NewClient(&goredis.Options{Addr: mr.Addr()})
	t.Cleanup(func() {
		require.NoError(t, rdb.Close())
	})

	var cache redisPingCache
	ttl := 100 * time.Millisecond
	ctx := context.Background()

	// Initial ping
	status := cache.ping(ctx, rdb, ttl)
	require.Empty(t, status)

	// Mock ping function to simulate failure
	oldPing := healthRedisPingFunc
	t.Cleanup(func() { healthRedisPingFunc = oldPing })

	healthRedisPingFunc = func(context.Context, *goredis.Client) error {
		return errors.New("simulated network outage")
	}

	// Cached ping should still return "" within TTL window
	statusCached := cache.ping(ctx, rdb, ttl)
	assert.Empty(t, statusCached, "Cached ping must return cached empty status within TTL")

	// Wait for TTL expiry
	time.Sleep(150 * time.Millisecond) // bound: wait for redis ping cache TTL expiry

	// Post-TTL ping must now fail with simulated network outage
	statusExpired := cache.ping(ctx, rdb, ttl)
	assert.Equal(t, "simulated network outage", statusExpired, "Expired cache must re-query and return error")
}
