package hub

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	"github.com/nats-io/nats.go"
	"github.com/stretchr/testify/require"
	"github.com/university-ecosystem/ws-hub/pkg/config"
)

// aud478ReplayPosition is the cache.revoke consumer position served by the mock
// JetStream server. pending counts window revocations not yet delivered, and
// ackPending counts delivered revocations not yet acknowledged, the same counters a
// real consumer reports.
type aud478ReplayPosition struct {
	pending    atomic.Int64
	ackPending atomic.Int64
	unreadable atomic.Bool
	reads      atomic.Int64
}

// newAUD478BarrierNATS connects a hub-side client to a mock JetStream server that
// accepts the revocation consumer and reports the position controlled by the test.
func newAUD478BarrierNATS(t *testing.T) (*nats.Conn, *aud478ReplayPosition) {
	t.Helper()
	position := &aud478ReplayPosition{}
	server := newMockNatsServer(t)
	server.jetStreamResponder = func(subject string, payload []byte) []byte {
		switch {
		case subject == "$JS.API.STREAM.NAMES":
			return []byte(`{"type":"io.nats.jetstream.api.v1.stream_names_response","total":1,"offset":0,"limit":1024,"streams":["CACHE_INVALIDATIONS"]}`)
		case strings.HasPrefix(subject, "$JS.API.CONSUMER.CREATE.CACHE_INVALIDATIONS"):
			_, response := aud478AcceptConsumer(subject, payload)
			return response
		case strings.HasPrefix(subject, "$JS.API.CONSUMER.INFO.CACHE_INVALIDATIONS."):
			position.reads.Add(1)
			if position.unreadable.Load() {
				return []byte(`{"type":"io.nats.jetstream.api.v1.consumer_info_response","error":{"code":500,"err_code":10000,"description":"consumer position unavailable"}}`)
			}
			return aud478ConsumerInfoResponse(position)
		default:
			return []byte(`{"type":"io.nats.jetstream.api.v1.consumer_create_response","error":{"code":404,"err_code":10059,"description":"unexpected JetStream request"}}`)
		}
	}
	nc, err := nats.Connect(server.Addr())
	require.NoError(t, err)
	t.Cleanup(nc.Close)
	return nc, position
}

func aud478ConsumerInfoResponse(position *aud478ReplayPosition) []byte {
	response, err := json.Marshal(map[string]any{
		"type":            "io.nats.jetstream.api.v1.consumer_info_response",
		"stream_name":     "CACHE_INVALIDATIONS",
		"name":            "ephemeral",
		"created":         time.Now().UTC().Format(time.RFC3339Nano),
		"config":          map[string]any{"filter_subject": "cache.revoke", "ack_policy": "explicit"},
		"delivered":       map[string]any{"consumer_seq": 0, "stream_seq": 0},
		"ack_floor":       map[string]any{"consumer_seq": 0, "stream_seq": 0},
		"num_ack_pending": position.ackPending.Load(),
		"num_redelivered": 0,
		"num_waiting":     0,
		"num_pending":     position.pending.Load(),
	})
	if err != nil {
		return []byte(`{"type":"io.nats.jetstream.api.v1.consumer_info_response","error":{"code":500,"err_code":10000,"description":"response encoding failed"}}`)
	}
	return response
}

// aud478BarrierHub returns a hub subscribed through the JetStream consumer path.
// Core chat keeps the mock limited to the revocation consumer under test.
func aud478BarrierHub(t *testing.T, nc *nats.Conn) (*Hub, context.Context) {
	t.Helper()
	h := setupTestHub()
	h.Nats = nc
	h.enableJetStream = false
	h.subscribeCacheInvalidations = nil
	h.revocationReplayWindow = time.Minute
	h.revocationWatchdogInterval = 10 * time.Millisecond
	ctx, cancel := context.WithCancel(context.Background())
	t.Cleanup(cancel)
	return h, ctx
}

// TestAUD478AdmissionBarrierOpensOnlyAfterReplayDrains is the startup barrier: a
// replica with undelivered window revocations keeps admission closed and opens it
// only after the cache.revoke consumer has drained.
func TestAUD478AdmissionBarrierOpensOnlyAfterReplayDrains(t *testing.T) {
	nc, position := newAUD478BarrierNATS(t)
	position.pending.Store(2)
	h, ctx := aud478BarrierHub(t, nc)

	require.NoError(t, h.SubscribeToNATS(ctx))
	require.True(t, h.RevocationCatchingUp(), "admission must stay closed while the replay window is undelivered")
	require.Never(t, func() bool { return !h.RevocationCatchingUp() }, 200*time.Millisecond, 10*time.Millisecond)

	position.pending.Store(0)
	require.Eventually(t, func() bool { return !h.RevocationCatchingUp() }, 5*time.Second, 10*time.Millisecond,
		"admission must open once the replay window has drained")
}

// TestAUD478AdmissionBarrierWaitsForAcknowledgedReplay requires processing, not only
// delivery: a revocation that is delivered but not yet acknowledged keeps admission
// closed, because its eviction has not been applied.
func TestAUD478AdmissionBarrierWaitsForAcknowledgedReplay(t *testing.T) {
	nc, position := newAUD478BarrierNATS(t)
	position.ackPending.Store(1)
	h, ctx := aud478BarrierHub(t, nc)

	require.NoError(t, h.SubscribeToNATS(ctx))
	require.Never(t, func() bool { return !h.RevocationCatchingUp() }, 200*time.Millisecond, 10*time.Millisecond,
		"an unacknowledged revocation must keep admission closed")

	position.ackPending.Store(0)
	require.Eventually(t, func() bool { return !h.RevocationCatchingUp() }, 5*time.Second, 10*time.Millisecond)
}

// TestAUD478BarrierStaysClosedWhenReplayPositionUnreadable is the fail-closed rule:
// a consumer position that cannot be read never opens admission, and the watcher
// keeps re-reading it until the position is available.
func TestAUD478BarrierStaysClosedWhenReplayPositionUnreadable(t *testing.T) {
	nc, position := newAUD478BarrierNATS(t)
	position.unreadable.Store(true)
	h, ctx := aud478BarrierHub(t, nc)

	require.NoError(t, h.SubscribeToNATS(ctx))
	require.Eventually(t, func() bool { return position.reads.Load() >= 3 }, 5*time.Second, 10*time.Millisecond,
		"the watcher must keep polling an unreadable position")
	require.True(t, h.RevocationCatchingUp(), "an unreadable replay position must keep admission closed")

	position.unreadable.Store(false)
	require.Eventually(t, func() bool { return !h.RevocationCatchingUp() }, 5*time.Second, 10*time.Millisecond)
}

// TestAUD478BarrierStaysClosedWithoutRevocationConsumer covers a subscription
// function that returns no subscription: there is no replay to observe, so the
// barrier stays closed.
func TestAUD478BarrierStaysClosedWithoutRevocationConsumer(t *testing.T) {
	nc, _ := newAUD478BarrierNATS(t)
	h, ctx := aud478BarrierHub(t, nc)
	h.subscribeCacheInvalidations = func(nats.MsgHandler, ...nats.SubOpt) (*nats.Subscription, error) {
		return nil, nil
	}

	require.NoError(t, h.SubscribeToNATS(ctx))
	require.True(t, h.RevocationCatchingUp(), "without a revocation consumer admission must stay closed")
}

// TestAUD478AdmissionBarrierGatesUpgradeBeforeTicketUse checks both upgrade paths.
// While the replay drains they refuse with 503 before the one-time ticket is
// consumed. Once the barrier is clear the same request reaches ticket validation.
func TestAUD478AdmissionBarrierGatesUpgradeBeforeTicketUse(t *testing.T) {
	cases := []struct {
		name         string
		draining     bool
		wantCode     int
		wantConsumed int
	}{
		{name: "replay draining refuses before ticket use", draining: true, wantCode: http.StatusServiceUnavailable, wantConsumed: 0},
		{name: "drained replay reaches ticket validation", draining: false, wantCode: http.StatusUnauthorized, wantConsumed: 1},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			h := setupTestHub()
			h.revocationCatchingUp.Store(tc.draining)
			consumed := 0
			oldValidate := validateUpgradeTicketIdentityFunc
			t.Cleanup(func() { validateUpgradeTicketIdentityFunc = oldValidate })
			validateUpgradeTicketIdentityFunc = func(*Hub, context.Context, string) (upgradeTicketIdentity, error) {
				consumed++
				return upgradeTicketIdentity{}, http.ErrNoCookie
			}
			cfg := &config.Config{MaxClients: 100}

			wsRec := httptest.NewRecorder()
			h.HandleWebSocket(wsRec, httptest.NewRequest(http.MethodGet, "/ws?ticket="+validWTTicket, nil), cfg)
			require.Equal(t, tc.wantCode, wsRec.Code, "WebSocket admission")
			require.Equal(t, tc.wantConsumed, consumed, "WebSocket ticket consumption")

			wtRec := httptest.NewRecorder()
			h.HandleWebTransport(wtRec, httptest.NewRequest(http.MethodGet, "/wt?ticket="+validWTTicket, nil), cfg)
			require.Equal(t, tc.wantCode, wtRec.Code, "WebTransport admission")
			require.Equal(t, 2*tc.wantConsumed, consumed, "WebTransport ticket consumption")
		})
	}
}

// TestAUD478BarrierReclosesWhenReplayPositionIsLost covers a consumer lost while the
// replica is serving. The barrier closes as soon as the position is unreadable, and
// it reopens only after the consumer has drained again, not when the position
// becomes readable again.
func TestAUD478BarrierReclosesWhenReplayPositionIsLost(t *testing.T) {
	nc, position := newAUD478BarrierNATS(t)
	h, ctx := aud478BarrierHub(t, nc)
	require.NoError(t, h.SubscribeToNATS(ctx))
	require.Eventually(t, func() bool { return !h.RevocationCatchingUp() }, 5*time.Second, 5*time.Millisecond)

	position.unreadable.Store(true)
	require.Eventually(t, func() bool { return h.RevocationCatchingUp() }, 5*time.Second, 5*time.Millisecond,
		"an unreadable replay position must close admission while the replica serves")

	position.unreadable.Store(false)
	position.pending.Store(2)
	require.Never(t, func() bool { return !h.RevocationCatchingUp() }, 200*time.Millisecond, 10*time.Millisecond,
		"a readable but undrained position must keep admission closed")

	position.pending.Store(0)
	require.Eventually(t, func() bool { return !h.RevocationCatchingUp() }, 5*time.Second, 5*time.Millisecond,
		"admission may reopen only after the consumer has drained again")
}

// TestAUD478BarrierReclosesWhenNATSConnectionDropsAndReopensOnlyAfterDrain covers a
// NATS disconnect and reconnect. The barrier closes while disconnected, and after the
// reconnect it reopens only once the consumer has drained.
func TestAUD478BarrierReclosesWhenNATSConnectionDropsAndReopensOnlyAfterDrain(t *testing.T) {
	nc, position := newAUD478BarrierNATS(t)
	h, ctx := aud478BarrierHub(t, nc)
	var connected atomic.Bool
	connected.Store(true)
	h.revocationConnected = func(*nats.Conn) bool { return connected.Load() }
	require.NoError(t, h.SubscribeToNATS(ctx))
	require.Eventually(t, func() bool { return !h.RevocationCatchingUp() }, 5*time.Second, 5*time.Millisecond)

	connected.Store(false)
	require.Eventually(t, func() bool { return h.RevocationCatchingUp() }, 5*time.Second, 5*time.Millisecond,
		"a dropped NATS connection must close admission")

	position.pending.Store(1)
	connected.Store(true)
	require.Never(t, func() bool { return !h.RevocationCatchingUp() }, 200*time.Millisecond, 10*time.Millisecond,
		"a reconnected but undrained consumer must keep admission closed")

	position.pending.Store(0)
	require.Eventually(t, func() bool { return !h.RevocationCatchingUp() }, 5*time.Second, 5*time.Millisecond)
}

// TestAUD478BarrierReclosesWhenNATSConnectionCloses covers the connection being closed
// for good. The subscription becomes invalid, so the barrier closes and stays closed.
func TestAUD478BarrierReclosesWhenNATSConnectionCloses(t *testing.T) {
	nc, _ := newAUD478BarrierNATS(t)
	h, ctx := aud478BarrierHub(t, nc)
	require.NoError(t, h.SubscribeToNATS(ctx))
	require.Eventually(t, func() bool { return !h.RevocationCatchingUp() }, 5*time.Second, 5*time.Millisecond)

	nc.Close()
	require.Eventually(t, func() bool { return h.RevocationCatchingUp() }, 5*time.Second, 5*time.Millisecond,
		"a closed NATS connection must close admission")
	require.Never(t, func() bool { return !h.RevocationCatchingUp() }, 200*time.Millisecond, 10*time.Millisecond,
		"a closed connection can never reopen admission")
}
