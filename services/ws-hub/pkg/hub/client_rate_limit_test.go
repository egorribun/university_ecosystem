package hub

import (
	"testing"

	"github.com/prometheus/client_golang/prometheus/testutil"
	"github.com/stretchr/testify/assert"
)

func TestAllowIncomingMessage_BurstThenThrottle(t *testing.T) {
	h := setupTestHub()
	h.clientMsgRateLimit = 0.001 // effectively no refill during the test
	h.clientMsgRateBurst = 3
	srv, _ := newConnPair(t)
	c := newClientOn(h, srv, "c-rate", "u-rate")

	for i := 0; i < 3; i++ {
		assert.True(t, c.allowIncomingMessage(), "burst token %d", i)
	}
	assert.False(t, c.allowIncomingMessage(), "bucket exhausted")
}

func TestAllowIncomingMessage_BucketsAreIndependentPerClient(t *testing.T) {
	h := setupTestHub()
	h.clientMsgRateLimit = 0.001
	h.clientMsgRateBurst = 1
	srvA, _ := newConnPair(t)
	srvB, _ := newConnPair(t)
	a := newClientOn(h, srvA, "c-a", "u-a")
	b := newClientOn(h, srvB, "c-b", "u-b")

	assert.True(t, a.allowIncomingMessage())
	assert.False(t, a.allowIncomingMessage())
	assert.True(t, b.allowIncomingMessage(), "another client keeps its own budget")
}

func TestAllowIncomingMessage_DisabledWhenUnconfigured(t *testing.T) {
	h := setupTestHub()
	srv, _ := newConnPair(t)
	c := newClientOn(h, srv, "c-off", "u-off")

	for _, tc := range []struct {
		name  string
		limit float64
		burst int
	}{{"no rate", 0, 5}, {"no burst", 5, 0}} {
		h.clientMsgRateLimit, h.clientMsgRateBurst = tc.limit, tc.burst
		for i := 0; i < 100; i++ {
			if !c.allowIncomingMessage() {
				t.Fatalf("%s: message %d must not be throttled", tc.name, i)
			}
		}
	}

	orphan := &Client{ID: "no-hub"}
	assert.True(t, orphan.allowIncomingMessage(), "a client without a hub is never throttled")
}

func TestRejectRateLimitedMessage_NotifiesClientAndCounts(t *testing.T) {
	h := setupTestHub()
	h.clientMsgRateLimit = 0.001
	h.clientMsgRateBurst = 1
	srv, _ := newConnPair(t)
	c := newClientOn(h, srv, "c-notice", "u-notice")

	assert.False(t, c.rejectRateLimitedMessage(), "first frame is within budget")

	before := testutil.ToFloat64(IncomingDropsTotal)
	assert.True(t, c.rejectRateLimitedMessage())
	assert.Equal(t, before+1, testutil.ToFloat64(IncomingDropsTotal))
	select {
	case notice := <-c.Send:
		assert.JSONEq(t, `{"type":"rate_limit_exceeded"}`, string(notice))
	default:
		t.Fatal("expected a rate_limit_exceeded notice on Send")
	}
}

func TestRejectRateLimitedMessage_DropsNoticeWhenSendFull(t *testing.T) {
	h := setupTestHub()
	h.clientMsgRateLimit = 0.001
	h.clientMsgRateBurst = 1
	srv, _ := newConnPair(t)
	c := newClientOn(h, srv, "c-full", "u-full")
	assert.False(t, c.rejectRateLimitedMessage())
	for i := 0; i < cap(c.Send); i++ {
		c.Send <- []byte("filler")
	}

	before := testutil.ToFloat64(IncomingDropsTotal)
	assert.True(t, c.rejectRateLimitedMessage())
	assert.Equal(t, before+1, testutil.ToFloat64(IncomingDropsTotal),
		"the drop is counted even when the notice cannot be queued")
}
