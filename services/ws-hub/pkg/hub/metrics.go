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
)
