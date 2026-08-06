package hub

// Coverage tests (testing session 16) for the NATS-handler branches the existing
// hub_nats_test.go leaves out: the appCtx.Done() early-return in
// handleNotifications + handleCacheInvalidation, and the broadcast-full drop in
// handleNotifications. Mirrors the handleChat cancelled/full tests.

import (
	"context"
	"errors"
	"testing"

	"github.com/nats-io/nats.go"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

type scriptedJetStream struct {
	nats.JetStreamContext
	subscribe func(string, nats.MsgHandler, ...nats.SubOpt) (*nats.Subscription, error)
}

func (s *scriptedJetStream) Subscribe(subject string, handler nats.MsgHandler, opts ...nats.SubOpt) (*nats.Subscription, error) {
	return s.subscribe(subject, handler, opts...)
}

func TestHandleNotifications_CancelledContextReturnsEarly(t *testing.T) {
	h := newNatsTestHub(&mockAuthClient{allowed: true}, "", 10)
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	handler := h.handleNotifications(ctx)

	handler(&nats.Msg{Subject: "notifications.user-1", Data: []byte(`{"to":"user-1"}`)})

	select {
	case msg := <-h.Broadcast:
		t.Fatalf("expected no broadcast after context cancel, got %+v", msg)
	default:
	}
}

func TestHandleNotifications_FullChannelDrops(t *testing.T) {
	h := newNatsTestHub(&mockAuthClient{allowed: true}, "", 1)
	handler := h.handleNotifications(context.Background())

	handler(&nats.Msg{Subject: "notifications.u", Data: []byte(`{"to":"u","payload":{"n":1}}`)})
	handler(&nats.Msg{Subject: "notifications.u", Data: []byte(`{"to":"u","payload":{"n":2}}`)})

	first := recvBroadcast(t, h)
	assert.Equal(t, "notification", first.Type)
	select {
	case msg := <-h.Broadcast:
		t.Fatalf("second notification should have been dropped, got %+v", msg)
	default:
	}
}

func TestHandleCacheInvalidation_CancelledContextReturnsEarly(t *testing.T) {
	auth := &recordingAuthClient{}
	h := newNatsTestHub(auth, "secret", 10)
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	handler := h.handleCacheInvalidation(ctx)

	payload := signedInvalidationPayload(t, "secret", invalidationData{
		RoomID: "11111111-1111-1111-1111-111111111111",
		UserID: "22222222-2222-2222-2222-222222222222",
	})
	handler(&nats.Msg{Subject: "cache.invalidate", Data: payload})

	assert.Empty(t, auth.calls(), "cancelled context must short-circuit before any Invalidate")
}

func TestSubscribeToNATS_RejectsMissingConnection(t *testing.T) {
	h := newNatsTestHub(&mockAuthClient{allowed: true}, "", 10)
	h.Nats = nil

	err := h.SubscribeToNATS(context.Background())

	assert.EqualError(t, err, "NATS connection is not configured")
	assert.Empty(t, h.subs)
}

func TestSubscribeToNATS_ChatSubscriptionFailure(t *testing.T) {
	server := newMockNatsServer(t)
	nc, err := nats.Connect(server.Addr())
	require.NoError(t, err)
	h := setupTestHub()
	h.Nats = nc
	nc.Close()

	err = h.SubscribeToNATS(context.Background())
	require.Error(t, err)
	assert.Contains(t, err.Error(), "connection")
	assert.Empty(t, h.subs)
}

func TestSubscribeToNATS_JetStreamFallbacksToCoreNATS(t *testing.T) {
	server := newMockNatsServer(t)
	nc, err := nats.Connect(server.Addr())
	require.NoError(t, err)
	t.Cleanup(nc.Close)

	h := setupTestHub()
	h.Nats = nc
	h.enableJetStream = true
	calledSubjects := make([]string, 0, 2)
	h.js = &scriptedJetStream{
		subscribe: func(subject string, _ nats.MsgHandler, _ ...nats.SubOpt) (*nats.Subscription, error) {
			calledSubjects = append(calledSubjects, subject)
			return nil, errors.New("scripted JetStream subscription failure")
		},
	}
	t.Cleanup(h.Stop)

	require.NoError(t, h.SubscribeToNATS(context.Background()))
	assert.Equal(t, []string{"chat.*", "notifications.*"}, calledSubjects)
	assert.Len(t, h.subs, 5, "core fallback must still register all subscriptions")
}
