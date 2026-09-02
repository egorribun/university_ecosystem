package hub

import (
	"context"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/alicebob/miniredis/v2"
	goredis "github.com/redis/go-redis/v9"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"github.com/university-ecosystem/ws-hub/pkg/config"
)

const validWTTicket = "00112233445566778899aabbccddeeff00112233445566778899aabbccddeeff" // pragma: allowlist secret

func newWTTestHub() *Hub {
	logger := slog.New(slog.NewJSONHandler(io.Discard, nil))
	cfg := &config.Config{
		SendBufferSize:      256,
		BroadcastBufferSize: 4096,
		BroadcastWorkers:    2,
		ClientMsgRateLimit:  10,
		ClientMsgRateBurst:  20,
	}
	return trackTestHub(NewHub(nil, logger, &mockAuthClient{allowed: true}, cfg, nil))
}

func hubWithWTTicketRedis(t *testing.T, payload string) *Hub {
	mr := miniredis.RunT(t)
	rdb := goredis.NewClient(&goredis.Options{Addr: mr.Addr()})
	ctx := context.Background()
	require.NoError(t, rdb.Set(ctx, wsTicketKeyPrefix+validWTTicket, payload, 15*time.Second).Err())

	h := newWTTestHub()
	h.redisClient = rdb
	h.revocationRedisClient = rdb
	return h
}

func TestHandleWebTransport_ValidationErrors(t *testing.T) {
	cfg := &config.Config{
		MaxClients: 100,
	}

	t.Run("missing ticket", func(t *testing.T) {
		h := newWTTestHub()
		req := httptest.NewRequest("GET", "/wt", nil)
		rec := httptest.NewRecorder()
		h.HandleWebTransport(rec, req, cfg)
		assert.Equal(t, http.StatusUnauthorized, rec.Code)
	})

	t.Run("invalid ticket format", func(t *testing.T) {
		h := newWTTestHub()
		req := httptest.NewRequest("GET", "/wt?ticket=short", nil)
		rec := httptest.NewRecorder()
		h.HandleWebTransport(rec, req, cfg)
		assert.Equal(t, http.StatusUnauthorized, rec.Code)
	})

	t.Run("rate limit exceeded", func(t *testing.T) {
		h := newWTTestHub()
		req := httptest.NewRequest("GET", "/wt?ticket="+validWTTicket, nil)
		req.RemoteAddr = "10.0.0.1:1234"

		for i := 0; i < 100; i++ {
			h.UpgradeLimiter.Allow("10.0.0.1")
		}

		rec := httptest.NewRecorder()
		h.HandleWebTransport(rec, req, cfg)
		assert.Equal(t, http.StatusTooManyRequests, rec.Code)
	})

	t.Run("capacity limit exceeded", func(t *testing.T) {
		hCap := hubWithWTTicketRedis(t, "user-123:jti-abc")
		hCap.maxClients = 1
		hCap.Clients["c1"] = &Client{ID: "c1"}

		req := httptest.NewRequest("GET", "/wt?ticket="+validWTTicket, nil)
		rec := httptest.NewRecorder()
		hCap.HandleWebTransport(rec, req, cfg)
		assert.Equal(t, http.StatusServiceUnavailable, rec.Code)
	})
}

func TestHandleWebTransport_OriginAndUpgradeFailures(t *testing.T) {
	cfg := &config.Config{MaxClients: 100}

	t.Run("production origin is rejected before upgrade", func(t *testing.T) {
		t.Setenv("ENVIRONMENT", "production")
		SetAllowedOrigins([]string{"https://allowed.example"})
		t.Cleanup(func() { SetAllowedOrigins(nil) })

		h := hubWithWTTicketRedis(t, "user-origin:"+validSessionJTI)
		req := httptest.NewRequest("GET", "/wt?ticket="+validWTTicket, nil)
		req.Header.Set("Origin", "https://blocked.example")
		rec := httptest.NewRecorder()

		h.HandleWebTransport(rec, req, cfg)

		assert.Equal(t, http.StatusForbidden, rec.Code)
	})

	t.Run("ordinary HTTP writer rejects WebTransport upgrade", func(t *testing.T) {
		h := hubWithWTTicketRedis(t, "user-upgrade:"+validSessionJTI)
		req := httptest.NewRequest("GET", "/wt?ticket="+validWTTicket, nil)
		rec := httptest.NewRecorder()

		assert.NotPanics(t, func() {
			h.HandleWebTransport(rec, req, cfg)
		})

		h.mu.RLock()
		clientCount := len(h.Clients)
		h.mu.RUnlock()
		assert.Zero(t, clientCount)
	})

	t.Run("WebTransportSession SetPongHandler is no-op", func(t *testing.T) {
		session := NewWebTransportSession(nil)
		assert.NotNil(t, session)
		assert.NotPanics(t, func() {
			session.SetPongHandler(func(string) error { return nil })
		})
	})
}
