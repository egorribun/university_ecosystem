package hub

import (
	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"
)

// INF-02 (audit 2026-03-08 Wave 5): Prometheus metrics for ws-hub observability.
// Exported so that main.go and handlers.go can instrument events directly.
// All metrics are registered with the default registry via promauto.
var (
	// ActiveConnections tracks the number of currently connected WebSocket clients.
	// Incremented on Register, decremented on Unregister.
	ActiveConnections = promauto.NewGauge(prometheus.GaugeOpts{
		Name: "ws_hub_active_connections",
		Help: "Number of currently connected WebSocket clients.",
	})

	// AuthFailuresTotal counts authentication/authorisation rejections.
	// reason label values: invalid_token | jwks_error | origin_rejected |
	//                      max_clients | room_denied
	AuthFailuresTotal = promauto.NewCounterVec(prometheus.CounterOpts{
		Name: "ws_hub_auth_failures_total",
		Help: "Total number of authentication or authorisation failures, partitioned by reason.",
	}, []string{"reason"})

	// MessagesDeliveredTotal counts messages successfully fanned-out to at
	// least one client (incremented per recipient, not per message).
	MessagesDeliveredTotal = promauto.NewCounter(prometheus.CounterOpts{
		Name: "ws_hub_messages_delivered_total",
		Help: "Total number of WebSocket messages delivered to clients.",
	})

	// CacheInvalidationsTotal counts successful calls to the auth-cache
	// invalidation endpoint (/internal/cache/invalidate).
	CacheInvalidationsTotal = promauto.NewCounter(prometheus.CounterOpts{
		Name: "ws_hub_cache_invalidations_total",
		Help: "Total number of successful auth-cache invalidations.",
	})

	// PERF-W16-01: BroadcastDropsTotal counts messages dropped because the
	// broadcast worker pool or channel was full. Sustained non-zero values
	// indicate the hub cannot keep up with incoming message volume.
	BroadcastDropsTotal = promauto.NewCounter(prometheus.CounterOpts{
		Name: "ws_hub_broadcast_drops_total",
		Help: "Messages dropped due to full broadcast channel or worker pool.",
	})

	// PERF-W17-03: BroadcastQueueDepth exposes the current number of pending
	// messages in the broadcast worker channel. Operators can alert on
	// sustained high depth to detect approaching saturation BEFORE drops begin.
	BroadcastQueueDepth = promauto.NewGauge(prometheus.GaugeOpts{
		Name: "ws_hub_broadcast_queue_depth",
		Help: "Current number of pending messages in the broadcast worker channel.",
	})

	// RZ-23-07 (audit 2026-03-25 Wave 23): Track active goroutines managed by
	// the hub. Sustained growth indicates goroutine leaks; operators can alert
	// on active_goroutines > expected_workers + active_connections.
	ActiveGoroutines = promauto.NewGauge(prometheus.GaugeOpts{
		Name: "ws_hub_active_goroutines",
		Help: "Number of active goroutines managed by the hub (broadcast workers, NATS handlers).",
	})

	// RZ-27-02: Incoming messages dropped due to exceeding the size limit.
	IncomingDropsTotal = promauto.NewCounter(prometheus.CounterOpts{
		Name: "ws_hub_incoming_drops_total",
		Help: "Total incoming messages dropped due to size limit (RZ-27-02)",
	})

	// RZ-27-05: Unknown WS message types received — protocol drift detection.
	UnknownMsgTypeTotal = promauto.NewCounter(prometheus.CounterOpts{
		Name: "ws_hub_unknown_msg_type_total",
		Help: "Unknown WS message types received (RZ-27-05)",
	})

	// SessionsRevokedTotal counts user session evictions triggered by NATS control events.
	SessionsRevokedTotal = promauto.NewCounter(prometheus.CounterOpts{
		Name: "ws_hub_sessions_revoked_total",
		Help: "Total number of WebSocket sessions revoked via control events.",
	})

	// JetStreamAcksTotal tracks successful JetStream message ACKs.
	JetStreamAcksTotal = promauto.NewCounter(prometheus.CounterOpts{
		Name: "ws_hub_jetstream_acks_total",
		Help: "Total number of JetStream message ACKs.",
	})

	// JetStreamNaksTotal tracks JetStream message NAKs (backpressure redelivery delay).
	JetStreamNaksTotal = promauto.NewCounter(prometheus.CounterOpts{
		Name: "ws_hub_jetstream_naks_total",
		Help: "Total number of JetStream message NAKs.",
	})

	// JetStreamDedupHitsTotal tracks duplicate JetStream messages dropped via Nats-Msg-Id header.
	JetStreamDedupHitsTotal = promauto.NewCounter(prometheus.CounterOpts{
		Name: "ws_hub_jetstream_dedup_hits_total",
		Help: "Total number of duplicate JetStream messages dropped.",
	})

	// JetStreamReplayedTotal tracks offline JetStream messages replayed upon client room join.
	JetStreamReplayedTotal = promauto.NewCounter(prometheus.CounterOpts{
		Name: "ws_hub_jetstream_replayed_total",
		Help: "Total number of JetStream messages replayed to reconnecting clients.",
	})

	// ReplayJoinRateLimitedTotal tracks replay-bearing join requests rejected
	// before they can churn JetStream pull consumers.
	ReplayJoinRateLimitedTotal = promauto.NewCounter(prometheus.CounterOpts{
		Name: "ws_hub_replay_join_rate_limited_total",
		Help: "Total number of replay-bearing room joins rejected by the per-client limiter.",
	})
)
