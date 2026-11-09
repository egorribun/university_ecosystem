package hub

import (
	"context"
	"errors"
	"io"
	"log/slog"
	"testing"
	"time"

	"github.com/nats-io/nats.go"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestRevocationCatchUpPreservesAdmissionUntilConsumerDrains(t *testing.T) {
	cases := []struct {
		name        string
		connected   bool
		catchingUp  bool
		pending     uint64
		ackPending  int
		consumerErr error
		wantClosed  bool
		wantPoll    bool
		wantCalls   int
		wantReason  string
	}{
		{name: "disconnected closes admission", catchingUp: false, wantClosed: true, wantPoll: true, wantReason: "the NATS connection is down"},
		{name: "consumer error closes admission", connected: true, consumerErr: errors.New("position unavailable"), wantClosed: true, wantPoll: true, wantCalls: 1, wantReason: "the cache.revoke consumer position is unavailable"},
		{name: "drained opens closed barrier", connected: true, catchingUp: true, wantCalls: 1},
		{name: "drained keeps open barrier", connected: true, wantCalls: 1},
		{name: "pending keeps closed barrier", connected: true, catchingUp: true, pending: 1, wantClosed: true, wantPoll: true, wantCalls: 1, wantReason: "previous state"},
		{name: "unacknowledged keeps closed barrier", connected: true, catchingUp: true, ackPending: 1, wantClosed: true, wantPoll: true, wantCalls: 1, wantReason: "previous state"},
		{name: "live pending keeps open barrier", connected: true, pending: 1, wantCalls: 1, wantReason: "previous state"},
		{name: "live unacknowledged keeps open barrier", connected: true, ackPending: 1, wantCalls: 1, wantReason: "previous state"},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			previous := revocationConsumerInfoFunc
			t.Cleanup(func() { revocationConsumerInfoFunc = previous })
			calls := 0
			revocationConsumerInfoFunc = func(*nats.Subscription) (*nats.ConsumerInfo, error) {
				calls++
				return &nats.ConsumerInfo{NumPending: tc.pending, NumAckPending: tc.ackPending}, tc.consumerErr
			}
			h := &Hub{
				Logger:                     slog.New(slog.NewTextHandler(io.Discard, nil)),
				revocationWatchdogInterval: 3 * time.Second,
				revocationConnected:        func(*nats.Conn) bool { return tc.connected },
			}
			h.revocationCatchingUp.Store(tc.catchingUp)
			reason := "previous state"

			delay := h.checkRevocationCatchUp(context.Background(), nil, &reason)

			assert.Equal(t, tc.wantClosed, h.RevocationCatchingUp())
			assert.Equal(t, tc.wantCalls, calls)
			assert.Equal(t, tc.wantReason, reason)
			if tc.wantPoll {
				require.Equal(t, revocationCatchUpPollInterval, delay)
			} else {
				require.Equal(t, h.revocationWatchdogInterval, delay)
			}
		})
	}
}
