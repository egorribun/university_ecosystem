package hub

import (
	"context"
	"errors"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"github.com/nats-io/nats.go"
	"github.com/stretchr/testify/require"
	"github.com/university-ecosystem/ws-hub/pkg/config"
)

// aud478EventLog records the order of consumer creations and cache resets across the
// NATS mock and the reset client, so tests can assert sequencing.
type aud478EventLog struct {
	mu      sync.Mutex
	entries []string
}

func (l *aud478EventLog) add(entry string) {
	l.mu.Lock()
	defer l.mu.Unlock()
	l.entries = append(l.entries, entry)
}

func (l *aud478EventLog) snapshot() []string {
	l.mu.Lock()
	defer l.mu.Unlock()
	return append([]string(nil), l.entries...)
}

// aud478ConsumerRecorder captures every consumer creation and deletion the hub makes.
type aud478ConsumerRecorder struct {
	mu      sync.Mutex
	creates []map[string]any
	deletes int
	events  *aud478EventLog
}

func (r *aud478ConsumerRecorder) recordCreate(consumer map[string]any) {
	r.mu.Lock()
	r.creates = append(r.creates, consumer)
	r.mu.Unlock()
	r.events.add("subscribe:" + consumerFilter(consumer))
}

func (r *aud478ConsumerRecorder) recordDelete() {
	r.mu.Lock()
	r.deletes++
	r.mu.Unlock()
}

// invalidateCreates returns the creation requests for the pure-invalidation consumer.
func (r *aud478ConsumerRecorder) invalidateCreates() []map[string]any {
	r.mu.Lock()
	defer r.mu.Unlock()
	var matched []map[string]any
	for _, consumer := range r.creates {
		if consumerFilter(consumer) == "cache.invalidate" {
			matched = append(matched, consumer)
		}
	}
	return matched
}

func consumerFilter(consumer map[string]any) string {
	filter, _ := consumer["filter_subject"].(string)
	return filter
}

// newAUD478ConsumerNATS connects to a mock JetStream server that accepts both
// invalidation consumers, reports a drained revocation position, and records every
// creation and deletion.
func newAUD478ConsumerNATS(t *testing.T, recorder *aud478ConsumerRecorder) *nats.Conn {
	t.Helper()
	server := newMockNatsServer(t)
	position := &aud478ReplayPosition{}
	server.jetStreamResponder = func(subject string, payload []byte) []byte {
		switch {
		case subject == "$JS.API.STREAM.NAMES":
			return []byte(`{"type":"io.nats.jetstream.api.v1.stream_names_response","total":1,"offset":0,"limit":1024,"streams":["CACHE_INVALIDATIONS"]}`)
		case strings.HasPrefix(subject, "$JS.API.CONSUMER.CREATE.CACHE_INVALIDATIONS"):
			consumerConfig, response := aud478AcceptConsumer(subject, payload)
			recorder.recordCreate(consumerConfig)
			return response
		case strings.HasPrefix(subject, "$JS.API.CONSUMER.DELETE.CACHE_INVALIDATIONS."):
			recorder.recordDelete()
			return []byte(`{"type":"io.nats.jetstream.api.v1.consumer_delete_response","success":true}`)
		case strings.HasPrefix(subject, "$JS.API.CONSUMER.INFO.CACHE_INVALIDATIONS."):
			return aud478ConsumerInfoResponse(position)
		default:
			return []byte(`{"type":"io.nats.jetstream.api.v1.consumer_create_response","error":{"code":404,"err_code":10059,"description":"unexpected JetStream request"}}`)
		}
	}
	nc, err := nats.Connect(server.Addr())
	require.NoError(t, err)
	t.Cleanup(nc.Close)
	return nc
}

// aud478ResetClient is a RoomAuthClient whose cache reset is observable. attempts
// counts every reset call, resets counts only the successful ones, failures makes the
// next calls fail, and hold blocks a reset until it is released.
type aud478ResetClient struct {
	attempts atomic.Int32
	resets   atomic.Int32
	failures atomic.Int32
	events   *aud478EventLog

	mu   sync.Mutex
	hold chan struct{}
}

func (c *aud478ResetClient) CanJoinRoom(context.Context, string, string) bool { return false }

func (c *aud478ResetClient) Invalidate(string, string) {}

func (c *aud478ResetClient) ResetAuthorizationCache(ctx context.Context) error {
	c.attempts.Add(1)
	c.events.add("reset")
	c.mu.Lock()
	hold := c.hold
	c.mu.Unlock()
	if hold != nil {
		select {
		case <-hold:
		case <-ctx.Done():
			return ctx.Err()
		}
	}
	if c.failures.Load() > 0 {
		c.failures.Add(-1)
		return errors.New("synthetic authorization cache reset failure")
	}
	c.resets.Add(1)
	return nil
}

func (c *aud478ResetClient) setHold(hold chan struct{}) {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.hold = hold
}

// aud478AdmissionHub returns a hub whose JetStream consumers run against the recorder,
// with the reconnect count and connection state controlled by the test.
func aud478AdmissionHub(t *testing.T, recorder *aud478ConsumerRecorder, client RoomAuthClient) (*Hub, *atomic.Uint64, context.Context) {
	t.Helper()
	nc := newAUD478ConsumerNATS(t, recorder)
	h := setupTestHub()
	h.Nats = nc
	h.authClient = client
	h.enableJetStream = false
	h.subscribeCacheInvalidations = nil
	h.revocationReplayWindow = time.Minute
	h.revocationWatchdogInterval = 10 * time.Millisecond
	var connected atomic.Bool
	connected.Store(true)
	h.revocationConnected = func(*nats.Conn) bool { return connected.Load() }
	var reconnects atomic.Uint64
	h.natsReconnectCount = func(*nats.Conn) uint64 { return reconnects.Load() }
	ctx, cancel := context.WithCancel(context.Background())
	t.Cleanup(cancel)
	return h, &reconnects, ctx
}

// aud478AdmitUpgrade drives both upgrade paths with a valid-looking ticket and reports
// the WebSocket status and whether the one-time ticket was consumed.
func aud478AdmitUpgrade(t *testing.T, h *Hub) (int, int) {
	t.Helper()
	consumed := 0
	oldValidate := validateUpgradeTicketIdentityFunc
	t.Cleanup(func() { validateUpgradeTicketIdentityFunc = oldValidate })
	validateUpgradeTicketIdentityFunc = func(*Hub, context.Context, string) (upgradeTicketIdentity, error) {
		consumed++
		return upgradeTicketIdentity{}, http.ErrNoCookie
	}
	rec := httptest.NewRecorder()
	h.HandleWebSocket(rec, httptest.NewRequest(http.MethodGet, "/ws?ticket="+validWTTicket, nil), &config.Config{MaxClients: 100})
	return rec.Code, consumed
}

// TestAUD478StartupResetPrecedesFirstAdmission is the startup barrier. The cache
// invalidation consumer exists before the first reset, admission stays refused until a
// reset succeeds, and a failed reset is retried rather than bypassed.
func TestAUD478StartupResetPrecedesFirstAdmission(t *testing.T) {
	cases := []struct {
		name     string
		failures int32
	}{
		{name: "successful first reset admits immediately", failures: 0},
		{name: "failed first reset keeps admission closed until a retry succeeds", failures: 2},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			events := &aud478EventLog{}
			recorder := &aud478ConsumerRecorder{events: events}
			client := &aud478ResetClient{events: events}
			client.failures.Store(tc.failures)
			h, _, ctx := aud478AdmissionHub(t, recorder, client)

			require.NoError(t, h.SubscribeToNATS(ctx))
			if tc.failures == 0 {
				// The revocation watcher opens its own barrier on a short poll, so the
				// admitted path waits for both barriers before asserting on admission.
				require.Eventually(t, func() bool { return !h.AdmissionClosed() }, 5*time.Second, 5*time.Millisecond,
					"a successful startup reset must admit once the revocation replay is current")
				code, consumed := aud478AdmitUpgrade(t, h)
				require.Equal(t, http.StatusUnauthorized, code, "admitted upgrade reaches ticket validation")
				require.Equal(t, 1, consumed)
			} else {
				require.True(t, h.AdmissionClosed(), "a failed startup reset must keep admission closed")
				code, consumed := aud478AdmitUpgrade(t, h)
				require.Equal(t, http.StatusServiceUnavailable, code, "admission is refused before the ticket is consumed")
				require.Zero(t, consumed)
				require.Eventually(t, func() bool { return !h.AdmissionClosed() }, 10*time.Second, 10*time.Millisecond,
					"admission must open once a retried reset succeeds")
				require.Equal(t, tc.failures+1, client.attempts.Load(), "each failed reset is retried, not skipped")
			}

			order := events.snapshot()
			require.NotEmpty(t, order)
			require.Less(t, indexOf(order, "subscribe:cache.invalidate"), indexOf(order, "reset"),
				"the live invalidation consumer must exist before the first reset")
			for _, creation := range recorder.invalidateCreates() {
				require.Equal(t, "new", creation["deliver_policy"], "startup must not replay the backlog")
			}
		})
	}
}

func indexOf(order []string, entry string) int {
	for i, value := range order {
		if value == entry {
			return i
		}
	}
	return -1
}

// TestAUD478ReconnectClosesAdmissionResetsAndResubscribesFromNow covers the reconnect
// contract. The barrier closes at once when the reconnect count changes, the live
// invalidation consumer is replaced with one that starts at new messages, and admission
// reopens only after the reset completes. In-flight reset work keeps it closed.
func TestAUD478ReconnectClosesAdmissionResetsAndResubscribesFromNow(t *testing.T) {
	events := &aud478EventLog{}
	recorder := &aud478ConsumerRecorder{events: events}
	client := &aud478ResetClient{events: events}
	h, reconnects, ctx := aud478AdmissionHub(t, recorder, client)

	require.NoError(t, h.SubscribeToNATS(ctx))
	require.Eventually(t, func() bool { return !h.AdmissionClosed() }, 5*time.Second, 5*time.Millisecond)
	require.Len(t, recorder.invalidateCreates(), 1)

	hold := make(chan struct{})
	client.setHold(hold)
	reconnects.Add(1)
	require.True(t, h.AdmissionClosed(), "a reconnect must close admission synchronously")

	require.Eventually(t, func() bool { return len(recorder.invalidateCreates()) == 2 }, 5*time.Second, 5*time.Millisecond,
		"the live invalidation consumer must be recreated after a reconnect")
	require.Never(t, func() bool { return !h.AdmissionClosed() }, 200*time.Millisecond, 10*time.Millisecond,
		"admission must stay closed while the reset is still in flight")

	client.setHold(nil)
	close(hold)
	require.Eventually(t, func() bool { return !h.AdmissionClosed() }, 5*time.Second, 10*time.Millisecond,
		"admission must reopen once the reset completes")
	require.Equal(t, int32(2), client.resets.Load(), "one reset at startup and one after the reconnect")

	order := events.snapshot()
	require.Equal(t, []string{
		"subscribe:cache.invalidate", "reset",
		"subscribe:cache.invalidate", "reset",
	}, filterOrder(order, "subscribe:cache.invalidate", "reset"),
		"each reset must follow the consumer that was current when it ran")

	for _, creation := range recorder.invalidateCreates() {
		require.Equal(t, "new", creation["deliver_policy"], "a reconnect must not replay the backlog")
		require.NotContains(t, creation, "opt_start_seq")
		require.NotContains(t, creation, "opt_start_time")
	}
}

// filterOrder keeps only the entries named in keep, in their recorded order.
func filterOrder(order []string, keep ...string) []string {
	var filtered []string
	for _, entry := range order {
		for _, want := range keep {
			if entry == want {
				filtered = append(filtered, entry)
				break
			}
		}
	}
	return filtered
}

// TestAUD478ReconnectRetriesAFailedResetWithoutBypass checks that a reset that fails
// after a reconnect keeps admission closed, and that only a later successful reset
// opens it.
func TestAUD478ReconnectRetriesAFailedResetWithoutBypass(t *testing.T) {
	events := &aud478EventLog{}
	recorder := &aud478ConsumerRecorder{events: events}
	client := &aud478ResetClient{events: events}
	h, reconnects, ctx := aud478AdmissionHub(t, recorder, client)
	require.NoError(t, h.SubscribeToNATS(ctx))
	require.Eventually(t, func() bool { return !h.AdmissionClosed() }, 5*time.Second, 10*time.Millisecond)

	client.failures.Store(2)
	reconnects.Add(1)
	require.True(t, h.AdmissionClosed())
	require.Eventually(t, func() bool { return client.failures.Load() == 0 && client.resets.Load() == 2 }, 10*time.Second,
		10*time.Millisecond, "the reset must be retried until it succeeds")
	require.Eventually(t, func() bool { return !h.AdmissionClosed() }, 5*time.Second, 10*time.Millisecond)
	require.Equal(t, int32(4), client.attempts.Load(), "one startup reset, then two failed and one successful reset after the reconnect")
}

// TestAUD478ConsumerSettingsReachBothInvalidationConsumers checks that the configured
// durable contract is what the NATS consumer requests carry, for both consumers.
func TestAUD478ConsumerSettingsReachBothInvalidationConsumers(t *testing.T) {
	cases := []struct {
		name     string
		settings config.NATSConsumerSettings
	}{
		{name: "configured values are applied", settings: config.NATSConsumerSettings{
			AckPolicy: "explicit", AckWaitSeconds: 120, MaxDeliver: 7, InactiveThresholdSeconds: 900,
		}},
		{name: "unset values resolve to the chart defaults", settings: config.NATSConsumerSettings{}},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			events := &aud478EventLog{}
			recorder := &aud478ConsumerRecorder{events: events}
			nc := newAUD478ConsumerNATS(t, recorder)
			logger := slog.New(slog.NewTextHandler(io.Discard, nil))
			h, err := NewHub(nc, logger, &aud478ResetClient{events: events}, &config.Config{
				MaxClients:                    10,
				RevocationReplayWindowSeconds: 60,
				NATSConsumer:                  tc.settings,
			}, nil)
			require.NoError(t, err)
			t.Cleanup(h.Stop)
			h.revocationWatchdogInterval = 10 * time.Millisecond
			ctx, cancel := context.WithCancel(context.Background())
			t.Cleanup(cancel)
			require.NoError(t, h.SubscribeToNATS(ctx))

			want, err := resolveNATSConsumerSettings(tc.settings)
			require.NoError(t, err)
			require.Len(t, recorder.invalidateCreates(), 1)
			for _, filter := range []string{"cache.invalidate", "cache.revoke"} {
				consumer := findConsumer(t, recorder, filter)
				require.Equal(t, "explicit", consumer["ack_policy"], filter)
				require.Equal(t, float64(want.AckWaitSeconds)*float64(time.Second), consumer["ack_wait"], filter)
				require.Equal(t, float64(want.MaxDeliver), consumer["max_deliver"], filter)
				require.Equal(t, float64(want.InactiveThresholdSeconds)*float64(time.Second), consumer["inactive_threshold"], filter)
				require.NotContains(t, consumer, "durable_name", filter)
			}
		})
	}
}

func findConsumer(t *testing.T, recorder *aud478ConsumerRecorder, filter string) map[string]any {
	t.Helper()
	recorder.mu.Lock()
	defer recorder.mu.Unlock()
	for _, consumer := range recorder.creates {
		if consumerFilter(consumer) == filter {
			return consumer
		}
	}
	require.Failf(t, "consumer not created", "no consumer for %s", filter)
	return nil
}

// TestAUD478NewHubRejectsUnsafeConsumerSettings checks that a hub never starts with a
// durable contract outside the supported range.
func TestAUD478NewHubRejectsUnsafeConsumerSettings(t *testing.T) {
	cases := []struct {
		name     string
		settings config.NATSConsumerSettings
	}{
		{name: "one delivery attempt drops a transiently failed invalidation", settings: config.NATSConsumerSettings{MaxDeliver: 1}},
		{name: "unlimited deliveries are rejected", settings: config.NATSConsumerSettings{MaxDeliver: -1}},
		{name: "ack wait under the callback timeout is rejected", settings: config.NATSConsumerSettings{AckWaitSeconds: 10}},
		{name: "unsupported ack policy is rejected", settings: config.NATSConsumerSettings{AckPolicy: "none"}},
		{name: "inactive threshold under one minute is rejected", settings: config.NATSConsumerSettings{InactiveThresholdSeconds: 5}},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			h, err := NewHub(nil, slog.New(slog.NewTextHandler(io.Discard, nil)), nil, &config.Config{
				NATSConsumer: tc.settings,
			}, nil)
			require.Error(t, err)
			require.Nil(t, h)
		})
	}
}

// TestAUD478ResolveNATSConsumerSettingsFillsOnlyUnsetFields checks that zero fields take
// the chart default while explicit values are preserved.
func TestAUD478ResolveNATSConsumerSettingsFillsOnlyUnsetFields(t *testing.T) {
	defaults := config.DefaultNATSConsumerSettings()
	got, err := resolveNATSConsumerSettings(config.NATSConsumerSettings{MaxDeliver: 9})
	require.NoError(t, err)
	require.Equal(t, defaults.AckPolicy, got.AckPolicy)
	require.Equal(t, defaults.AckWaitSeconds, got.AckWaitSeconds)
	require.Equal(t, 9, got.MaxDeliver)
	require.Equal(t, defaults.InactiveThresholdSeconds, got.InactiveThresholdSeconds)
}

// TestAUD478NATSReconnectCountReadsTheLiveConnection covers the reconnect counter used
// by the admission barrier: a hub without a connection reports zero, and a live
// connection reports its own statistics.
func TestAUD478NATSReconnectCountReadsTheLiveConnection(t *testing.T) {
	h := setupTestHub()
	h.Nats = nil
	require.Zero(t, h.natsReconnects(), "without a connection there is no reconnect to observe")

	recorder := &aud478ConsumerRecorder{events: &aud478EventLog{}}
	h.Nats = newAUD478ConsumerNATS(t, recorder)
	require.Equal(t, h.Nats.Stats().Reconnects, h.natsReconnects())
}

// TestAUD478LifecycleFallsBackToOneSecondPoll covers a hub whose watchdog interval is
// unset. The lifecycle still runs on the default poll interval and exits with its context.
func TestAUD478LifecycleFallsBackToOneSecondPoll(t *testing.T) {
	events := &aud478EventLog{}
	recorder := &aud478ConsumerRecorder{events: events}
	h, _, _ := aud478AdmissionHub(t, recorder, &aud478ResetClient{events: events})
	h.revocationWatchdogInterval = 0
	ctx, cancel := context.WithCancel(context.Background())
	done := make(chan struct{})
	go func() {
		h.runAuthCacheAdmission(ctx, true)
		close(done)
	}()
	time.Sleep(10 * time.Millisecond)
	cancel()
	select {
	case <-done:
	case <-time.After(5 * time.Second):
		require.FailNow(t, "the lifecycle must exit when its context ends")
	}
}

// TestAUD478LifecycleRetriesAFailedResubscription covers a consumer that cannot be
// recreated after a reconnect. Admission stays closed and the lifecycle retries until the
// consumer exists again, then resets and reopens.
func TestAUD478LifecycleRetriesAFailedResubscription(t *testing.T) {
	events := &aud478EventLog{}
	recorder := &aud478ConsumerRecorder{events: events}
	client := &aud478ResetClient{events: events}
	nc := newAUD478ConsumerNATS(t, recorder)
	js, err := nc.JetStream()
	require.NoError(t, err)

	var subscribes atomic.Int32
	h := setupTestHub()
	h.Nats = nc
	h.authClient = client
	h.enableJetStream = false
	h.revocationReplayWindow = time.Minute
	h.revocationWatchdogInterval = 10 * time.Millisecond
	h.revocationConnected = func(*nats.Conn) bool { return true }
	var reconnects atomic.Uint64
	h.natsReconnectCount = func(*nats.Conn) uint64 { return reconnects.Load() }
	h.subscribeCacheInvalidations = func(handler nats.MsgHandler, opts ...nats.SubOpt) (*nats.Subscription, error) {
		switch subscribes.Add(1) {
		case 1:
			return js.Subscribe("cache.invalidate", handler, opts...)
		case 2:
			return js.Subscribe("cache.revoke", handler, opts...)
		case 3:
			return nil, errors.New("synthetic consumer creation failure")
		default:
			return js.Subscribe("cache.invalidate", handler, opts...)
		}
	}
	ctx, cancel := context.WithCancel(context.Background())
	t.Cleanup(cancel)

	require.NoError(t, h.SubscribeToNATS(ctx))
	require.Eventually(t, func() bool { return !h.AdmissionClosed() }, 5*time.Second, 5*time.Millisecond)

	reconnects.Add(1)
	require.Eventually(t, func() bool { return subscribes.Load() >= 4 && !h.AdmissionClosed() }, 10*time.Second,
		10*time.Millisecond, "the lifecycle must retry the consumer and reopen admission once it exists")
	require.Equal(t, int32(2), client.resets.Load(), "one reset at startup and one after the reconnect succeeds")
}

// TestAUD478ResubscribeDuringShutdownDiscardsTheNewConsumer covers a consumer opened
// while the hub is stopping. It is never registered, and the caller is told why.
func TestAUD478ResubscribeDuringShutdownDiscardsTheNewConsumer(t *testing.T) {
	recorder := &aud478ConsumerRecorder{events: &aud478EventLog{}}
	h, _, ctx := aud478AdmissionHub(t, recorder, nil)
	nc := h.Nats
	js, err := nc.JetStream()
	require.NoError(t, err)
	h.subscribeCacheInvalidations = func(handler nats.MsgHandler, opts ...nats.SubOpt) (*nats.Subscription, error) {
		sub, subErr := js.Subscribe("cache.invalidate", handler, opts...)
		// The connection drops while the consumer is opened, so its removal fails. The
		// failure must be logged and must not hide the shutdown reason.
		require.NoError(t, nc.Drain())
		return sub, subErr
	}
	h.stopped.Store(true)

	err = h.resubscribeCacheInvalidation(ctx)
	require.ErrorContains(t, err, "hub is stopping")
	h.subsMu.Lock()
	defer h.subsMu.Unlock()
	require.Nil(t, h.invalidationSub, "a consumer opened during shutdown must never be registered")
	require.Empty(t, h.subs)
}

// TestAUD478ResubscribeReplacesThePreviousConsumerEvenWhenItCannotBeRemoved covers a
// previous consumer whose removal fails. The failure is logged, and the replacement is
// still registered.
func TestAUD478ResubscribeReplacesThePreviousConsumerEvenWhenItCannotBeRemoved(t *testing.T) {
	recorder := &aud478ConsumerRecorder{events: &aud478EventLog{}}
	h, _, ctx := aud478AdmissionHub(t, recorder, nil)
	nc := h.Nats
	js, err := nc.JetStream()
	require.NoError(t, err)
	previous, err := js.Subscribe("cache.invalidate", func(*nats.Msg) {}, nats.DeliverNew(), nats.ManualAck())
	require.NoError(t, err)
	h.subsMu.Lock()
	h.invalidationSub = previous
	h.subs = []*nats.Subscription{previous}
	h.subsMu.Unlock()
	h.subscribeCacheInvalidations = func(nats.MsgHandler, ...nats.SubOpt) (*nats.Subscription, error) {
		return nil, nil
	}
	require.NoError(t, nc.Drain())

	require.NoError(t, h.resubscribeCacheInvalidation(ctx))
	h.subsMu.Lock()
	defer h.subsMu.Unlock()
	require.Nil(t, h.invalidationSub)
	require.Empty(t, h.subs, "the previous consumer must leave the drain list")
}

// TestAUD478SessionTransitionsCloseAdmissionAtEveryObservablePoint records the barrier
// at the instant each session transition sits between closing admission and recording
// the new count. That point is the only place the order can be observed, so the test
// asserts that the barrier reads closed there, at startup and across a reconnect.
func TestAUD478SessionTransitionsCloseAdmissionAtEveryObservablePoint(t *testing.T) {
	events := &aud478EventLog{}
	recorder := &aud478ConsumerRecorder{events: events}
	client := &aud478ResetClient{events: events}
	h, reconnects, ctx := aud478AdmissionHub(t, recorder, client)

	var mu sync.Mutex
	var flagClosed, admissionClosed []bool
	h.reconnectTransitionHook = func() {
		mu.Lock()
		defer mu.Unlock()
		flagClosed = append(flagClosed, h.authCacheAdmissionClosed.Load())
		admissionClosed = append(admissionClosed, h.AdmissionClosed())
	}
	snapshot := func() ([]bool, []bool) {
		mu.Lock()
		defer mu.Unlock()
		return append([]bool(nil), flagClosed...), append([]bool(nil), admissionClosed...)
	}

	require.NoError(t, h.SubscribeToNATS(ctx))
	flags, admissions := snapshot()
	require.Len(t, flags, 1, "startup records the session once, synchronously")
	require.True(t, flags[0], "the barrier must be closed before the startup session is recorded")
	require.True(t, admissions[0])
	require.Eventually(t, func() bool { return !h.AdmissionClosed() }, 5*time.Second, 5*time.Millisecond)

	reconnects.Add(1)
	require.Eventually(t, func() bool {
		flags, _ := snapshot()
		return len(flags) == 2
	}, 5*time.Second, time.Millisecond, "the reconnect transition must be observed")
	require.Eventually(t, func() bool { return !h.AdmissionClosed() }, 5*time.Second, 5*time.Millisecond)

	flags, admissions = snapshot()
	require.Len(t, flags, 2)
	for i := range flags {
		require.True(t, flags[i], "transition %d: the closed flag must be set before the count is recorded", i)
		require.True(t, admissions[i], "transition %d: admission must read closed at the recording point", i)
	}
}
