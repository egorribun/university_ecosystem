package hub

import (
	"bytes"
	"context"
	"crypto/rand"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log/slog"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/nats-io/nats.go"
	"github.com/stretchr/testify/require"
	"github.com/university-ecosystem/ws-hub/pkg/config"
)

// AUD-478: CACHE_INVALIDATIONS retains seven days of events. Pure cache
// invalidations are live-only: a replica starts with empty authorization state,
// so it must not replay the backlog or claim a durable identity shared by
// stateless pods. Room revocations travel on their own subject, cache.revoke, and
// a replica that starts while a revoked token can still be used must learn of the
// revocation. Their consumer therefore replays only the revocation replay window.
func TestAUD478CacheInvalidationConsumersReplayOnlyRevocationsWithinWindow(t *testing.T) {
	server := newMockNatsServer(t)
	var mu sync.Mutex
	var consumerConfigs []map[string]any
	server.jetStreamResponder = func(subject string, payload []byte) []byte {
		switch {
		case subject == "$JS.API.STREAM.NAMES":
			return []byte(`{"type":"io.nats.jetstream.api.v1.stream_names_response","total":1,"offset":0,"limit":1024,"streams":["CACHE_INVALIDATIONS"]}`)
		case strings.HasPrefix(subject, "$JS.API.CONSUMER.CREATE.CACHE_INVALIDATIONS"):
			consumerConfig, response := aud478AcceptConsumer(subject, payload)
			mu.Lock()
			consumerConfigs = append(consumerConfigs, consumerConfig)
			mu.Unlock()
			return response
		default:
			return []byte(`{"type":"io.nats.jetstream.api.v1.consumer_create_response","error":{"code":404,"err_code":10059,"description":"unexpected JetStream request"}}`)
		}
	}
	nc, err := nats.Connect(server.Addr())
	require.NoError(t, err)
	t.Cleanup(nc.Close)

	h := setupTestHub()
	h.Nats = nc
	// Core chat and notification subscriptions keep the JetStream requests limited
	// to the two cache-invalidation consumers under test.
	h.enableJetStream = false
	h.subscribeCacheInvalidations = nil
	h.revocationReplayWindow = 90 * time.Second

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	before := time.Now()
	require.NoError(t, h.SubscribeToNATS(ctx))
	after := time.Now()

	mu.Lock()
	configs := consumerConfigs
	mu.Unlock()
	require.Len(t, configs, 2, "pure invalidations and room revocations must use separate ephemeral consumers")
	byFilter := make(map[string]map[string]any, len(configs))
	for _, consumer := range configs {
		require.NotContains(t, consumer, "durable_name", "invalidation consumers must not claim a durable identity")
		require.Equal(t, "explicit", consumer["ack_policy"])
		byFilter[fmt.Sprint(consumer["filter_subject"])] = consumer
	}

	live, ok := byFilter["cache.invalidate"]
	require.True(t, ok, "pure invalidations must be consumed from cache.invalidate")
	require.Equal(t, "new", live["deliver_policy"], "pure invalidations must start at new messages")
	require.NotContains(t, live, "opt_start_seq", "pure invalidations must not replay the backlog")
	require.NotContains(t, live, "opt_start_time", "pure invalidations must not replay the backlog")

	revocation, ok := byFilter["cache.revoke"]
	require.True(t, ok, "room revocations must be consumed from cache.revoke")
	require.Equal(t, "by_start_time", revocation["deliver_policy"], "room revocations must replay from the bounded window start")
	startText, ok := revocation["opt_start_time"].(string)
	require.True(t, ok, "the revocation consumer must name its window start")
	start, err := time.Parse(time.RFC3339Nano, startText)
	require.NoError(t, err)
	require.False(t, start.Before(before.Add(-h.revocationReplayWindow)),
		"the replay window must not reach beyond the configured revocation window")
	require.False(t, start.After(after.Add(-h.revocationReplayWindow)),
		"the replay window must cover the configured revocation window")
}

// aud478AcceptConsumer accepts a consumer-create request by echoing its
// configuration, which is how a server confirms the consumer. It returns the
// requested configuration for assertions and the JetStream API reply.
func aud478AcceptConsumer(subject string, payload []byte) (map[string]any, []byte) {
	var request struct {
		Config map[string]any `json:"config"`
	}
	if err := json.Unmarshal(payload, &request); err != nil {
		return nil, []byte(`{"type":"io.nats.jetstream.api.v1.consumer_create_response","error":{"code":400,"err_code":10025,"description":"malformed consumer request"}}`)
	}
	name := "ephemeral"
	if parts := strings.Split(subject, "."); len(parts) > 5 {
		name = parts[5]
	}
	response, err := json.Marshal(map[string]any{
		"type":            "io.nats.jetstream.api.v1.consumer_create_response",
		"stream_name":     "CACHE_INVALIDATIONS",
		"name":            name,
		"created":         time.Now().UTC().Format(time.RFC3339Nano),
		"config":          request.Config,
		"delivered":       map[string]any{"consumer_seq": 0, "stream_seq": 0},
		"ack_floor":       map[string]any{"consumer_seq": 0, "stream_seq": 0},
		"num_ack_pending": 0,
		"num_redelivered": 0,
		"num_waiting":     0,
		"num_pending":     0,
	})
	if err != nil {
		return request.Config, []byte(`{"type":"io.nats.jetstream.api.v1.consumer_create_response","error":{"code":500,"err_code":10000,"description":"response encoding failed"}}`)
	}
	return request.Config, response
}

// aud478SubjectAuthClient records authorization-cache work so each applied event
// can be observed: pure invalidations call Invalidate, and revocations call
// RefreshRoomAuthorization.
type aud478SubjectAuthClient struct {
	mu            sync.Mutex
	invalidations [][2]string
	refreshes     [][2]string
}

func (a *aud478SubjectAuthClient) CanJoinRoom(context.Context, string, string) bool { return false }

func (a *aud478SubjectAuthClient) Invalidate(userID, roomID string) {
	a.mu.Lock()
	defer a.mu.Unlock()
	a.invalidations = append(a.invalidations, [2]string{userID, roomID})
}

func (a *aud478SubjectAuthClient) RefreshRoomAuthorization(_ context.Context, userID, roomID string) (bool, error) {
	a.mu.Lock()
	defer a.mu.Unlock()
	a.refreshes = append(a.refreshes, [2]string{userID, roomID})
	return false, nil
}

func (a *aud478SubjectAuthClient) counts() (int, int) {
	a.mu.Lock()
	defer a.mu.Unlock()
	return len(a.invalidations), len(a.refreshes)
}

// AUD-478 subject contract: each verified event is applied by the consumer that
// receives it, and the subject must match the event class. A room revocation on
// cache.invalidate, or a pure invalidation on cache.revoke, is a publisher contract
// violation. It is still applied, because dropping a revocation would leave a removed
// member connected, and it is logged so the publisher bug is visible.
func TestAUD478CacheInvalidationSubjectContract(t *testing.T) {
	secret := rand.Text()
	const user = "11111111-1111-1111-1111-111111111111"
	const room = "22222222-2222-2222-2222-222222222222"
	pure := signedInvalidationPayload(t, secret, invalidationData{RoomID: room, Timestamp: 1, UserID: user})
	revocation := signedInvalidationPayload(t, secret, invalidationData{
		EvictRoom: true, RoomID: room, Timestamp: 2, UserID: user,
	})

	oldAck, oldTerm := jetStreamAckFunc, jetStreamTermFunc
	t.Cleanup(func() { jetStreamAckFunc, jetStreamTermFunc = oldAck, oldTerm })

	cases := []struct {
		name           string
		subject        string
		data           []byte
		wantInvalidate int
		wantRefreshes  int
		wantViolation  bool
	}{
		{name: "pure invalidation on its subject", subject: "cache.invalidate", data: pure, wantInvalidate: 1},
		{name: "revocation on its subject", subject: "cache.revoke", data: revocation, wantRefreshes: 1},
		{name: "revocation on the invalidation subject is applied and flagged", subject: "cache.invalidate", data: revocation, wantRefreshes: 1, wantViolation: true},
		{name: "pure invalidation on the revocation subject is applied and flagged", subject: "cache.revoke", data: pure, wantInvalidate: 1, wantViolation: true},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			auth := &aud478SubjectAuthClient{}
			h := newNatsTestHub(auth, secret, 10)
			var logs bytes.Buffer
			h.Logger = slog.New(slog.NewTextHandler(&logs, nil))
			acks, terms := 0, 0
			jetStreamAckFunc = func(*nats.Msg) error { acks++; return nil }
			jetStreamTermFunc = func(*nats.Msg) error { terms++; return nil }

			h.handleCacheInvalidation(context.Background())(&nats.Msg{Subject: tc.subject, Data: tc.data})

			invalidations, refreshes := auth.counts()
			require.Equal(t, tc.wantInvalidate, invalidations)
			require.Equal(t, tc.wantRefreshes, refreshes)
			require.Equal(t, 1, acks, "the verified event is acknowledged")
			require.Zero(t, terms)
			if tc.wantViolation {
				require.Contains(t, logs.String(), "contract violation")
				require.Contains(t, logs.String(), "subject="+tc.subject)
			} else {
				require.NotContains(t, logs.String(), "contract violation")
			}
		})
	}
}

// TestAUD478RevocationReplayWindowComesFromConfig pins the window the revocation
// consumer uses: the configured token-lifetime bound, or the access-token default
// when the setting is absent or zero.
func TestAUD478RevocationReplayWindowComesFromConfig(t *testing.T) {
	logger := slog.New(slog.NewTextHandler(io.Discard, nil))
	cases := []struct {
		name string
		cfg  *config.Config
		want time.Duration
	}{
		{name: "nil config uses the access-token default", cfg: nil, want: defaultRevocationReplayWindow},
		{name: "unset window uses the access-token default", cfg: &config.Config{}, want: defaultRevocationReplayWindow},
		{name: "configured window is used", cfg: &config.Config{RevocationReplayWindowSeconds: 90}, want: 90 * time.Second},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			h := trackTestHub(NewHub(nil, logger, nil, tc.cfg, nil))
			require.Equal(t, tc.want, h.revocationReplayWindow)
		})
	}
}

// AUD-478: when the revocation consumer cannot be created, the subscription fails
// closed instead of reporting a replica that would miss replayed revocations.
func TestAUD478RevocationConsumerFailureFailsSubscriptionClosed(t *testing.T) {
	server := newMockNatsServer(t)
	nc, err := nats.Connect(server.Addr())
	require.NoError(t, err)
	t.Cleanup(nc.Close)

	h := setupTestHub()
	h.Nats = nc
	h.enableJetStream = false
	wantErr := errors.New("revocation consumer rejected")
	calls := 0
	h.subscribeCacheInvalidations = func(nats.MsgHandler, ...nats.SubOpt) (*nats.Subscription, error) {
		calls++
		if calls == 2 {
			return nil, wantErr
		}
		return nil, nil
	}

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	require.ErrorIs(t, h.SubscribeToNATS(ctx), wantErr)
	require.Equal(t, 2, calls, "the revocation consumer is created after the live consumer")
}
