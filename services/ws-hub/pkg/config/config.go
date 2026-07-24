package config

import (
	"net"
	"os"
	"runtime"
	"strconv"
	"strings"
)

// Config holds application configuration.
type Config struct {
	Port    string
	NatsURL string
	// NatsUser / NatsPassword pass credentials via nats.UserInfo() so they do
	// not appear in the connection URL string (which may be written to logs or
	// visible in /proc/<pid>/environ).  If set, NatsURL must be credential-free:
	//   NATS_URL=nats://nats:4222  +  NATS_USER=...  NATS_PASSWORD=...
	// MOD-W10-04 (audit 2026-03-16)
	NatsUser     string
	NatsPassword string
	// JWTSecrets holds one or more HMAC signing secrets in priority order.
	// Multiple secrets allow zero-downtime key rotation: new tokens are signed
	// with the first secret; old tokens signed with any remaining secret are
	// still accepted until they expire. (RZ-3: audit 2026-02-24)
	JWTSecrets     []string
	AllowedOrigins []string
	SentryDSN      string
	Environment    string
	// BackendURL is the internal base URL of the Python FastAPI service.
	// Used by the hub to authorize room-join requests via InternalAPIAuthClient.
	BackendURL string
	// JWKSURL points to the Python backend's /.well-known/jwks.json endpoint.
	// If provided, the hub prefers RS256 token verification via JWKS. (MOD-1)
	JWKSURL string
	// TrustedProxies is a list of IP addresses or CIDR ranges that are allowed
	// to provide the real client IP via X-Forwarded-For. (RZ-5)
	TrustedProxies []string
	// TrustedProxiesSet is the O(1)-lookup equivalent for exact IP matches.
	// P-03 (audit 2026-03-08): built once at load time so RealIP() does a
	// map lookup per request instead of an O(N) linear scan of the slice.
	TrustedProxiesSet map[string]struct{}
	// TrustedCIDRs holds parsed CIDR blocks from TrustedProxies entries that
	// contain a "/" (i.e. are CIDR notation).
	// PERF-04 (audit Wave 11): enables proper multi-hop XFF chain traversal
	// for CDN → Cloudflare → ingress → pod deployments.
	TrustedCIDRs []*net.IPNet
	// SendBufferSize is the size of the per-client outgoing message channel.
	// 256 slots * ~10 KB/msg ≈ 2.5 MB per concurrent connection. (TD-5)
	SendBufferSize int
	// BroadcastBufferSize is the size of the global message channel.
	// sized for NATS burst peaks (default 4096). (TD-5)
	BroadcastBufferSize int
	// BroadcastWorkers is the number of goroutines in the broadcast worker pool.
	// PERF-W14-02 (audit 2026-03-23 Wave 14): previously hard-coded to 4.
	// Default: 2 × GOMAXPROCS, capped to a reasonable max via WS_BROADCAST_WORKERS.
	BroadcastWorkers int
	// InternalSecret is the shared secret used to authenticate internal API calls
	// from the Python backend (e.g. cache invalidation). Must be set in production.
	// TD-NEW-07 (audit 2026-03-07)
	InternalSecret string
	// MaxClients is the maximum number of concurrently connected WebSocket clients.
	// 0 means unlimited (not recommended in production).
	// RZ-F-07 (audit 2026-03-07): without a cap, Hub.Clients grows without bound
	// allowing a single source to exhaust file descriptors and goroutine stacks.
	MaxClients int
	// TD-W16-03: Configurable per-client message rate limit (previously hardcoded 10/s, burst 20).
	ClientMsgRateLimit float64
	ClientMsgRateBurst int
	// MOD-W17-06: Configurable WS upgrade ticket TTL (default 15s).
	// Must match the Python backend's WS_TICKET_TTL_SECONDS.
	TicketTTLSeconds int
	// Redis connection parameters for L2 caching (PERF-006).
	RedisURL      string
	RedisPassword string
	RedisDB       int
	// SPIFFE Workload API & mTLS configuration
	SpiffeEnabled        bool
	SpiffeEndpointSocket string
	SpiffeTrustDomain    string
	SpiffeMyID           string
	BackendSpiffeID      string
}

// LoadConfig initializes Config from environment variables.
func LoadConfig() *Config {
	trustedProxies := getEnvSlice("TRUSTED_PROXIES", []string{"127.0.0.1", "::1"})
	// P-03 (audit 2026-03-08): Pre-build map for O(1) lookup in RealIP().
	// PERF-04 (audit Wave 11): also parse CIDR blocks for multi-hop chain traversal.
	trustedProxiesSet := make(map[string]struct{}, len(trustedProxies))
	var trustedCIDRs []*net.IPNet
	for _, entry := range trustedProxies {
		if strings.Contains(entry, "/") {
			if _, cidr, err := net.ParseCIDR(entry); err == nil {
				trustedCIDRs = append(trustedCIDRs, cidr)
			}
		} else {
			trustedProxiesSet[entry] = struct{}{}
		}
	}
	return &Config{
		Port:                getEnv("WS_HUB_PORT", "8081"),
		NatsURL:             getEnv("NATS_URL", "nats://nats:4222"),
		NatsUser:            os.Getenv("NATS_USER"),     // empty means no auth override
		NatsPassword:        os.Getenv("NATS_PASSWORD"), // empty means no auth override
		JWTSecrets:          loadJWTSecrets(),
		SentryDSN:           getEnv("SENTRY_DSN", ""),
		Environment:         getEnv("VITE_ENVIRONMENT", "development"),
		AllowedOrigins:      getEnvSlice("ALLOWED_ORIGINS", []string{"http://localhost:3000", "http://localhost:5173"}),
		TrustedProxies:      trustedProxies,
		TrustedProxiesSet:   trustedProxiesSet,
		TrustedCIDRs:        trustedCIDRs,
		BackendURL:          getEnv("BACKEND_INTERNAL_URL", "http://backend:8000"),
		JWKSURL:             getEnv("JWKS_URL", "http://backend:8000/.well-known/jwks.json"),
		SendBufferSize:      getEnvInt("WS_SEND_BUFFER_SIZE", 256),
		BroadcastBufferSize: getEnvInt("WS_BROADCAST_BUFFER_SIZE", 4096),
		// PERF-21-04 (audit 2026-03-25 Wave 21): Cap at 12 to prevent NATS
		// connection saturation on high-core nodes. Backpressure (drop + Nak)
		// provides a safety net for bursts beyond worker capacity.
		BroadcastWorkers:   min(getEnvInt("WS_BROADCAST_WORKERS", runtime.GOMAXPROCS(0)*2), 12),
		InternalSecret:     os.Getenv("WS_HUB_INTERNAL_SECRET"), // no default — empty secret allows HMAC forgery
		MaxClients:         getEnvInt("WS_HUB_MAX_CLIENTS", 10000),
		ClientMsgRateLimit: getEnvFloat("WS_CLIENT_MSG_RATE_LIMIT", 10),
		ClientMsgRateBurst: getEnvInt("WS_CLIENT_MSG_BURST", 20),
		TicketTTLSeconds:   getEnvInt("WS_TICKET_TTL_SECONDS", 15),
		RedisURL:           getEnv("REDIS_URL", "redis:6379"),
		RedisPassword:      getEnv("REDIS_PASSWORD", ""),
		RedisDB:            getEnvInt("REDIS_DB", 0),
		SpiffeEnabled:        os.Getenv("SPIFFE_ENABLED") == "true",
		SpiffeEndpointSocket: getEnv("SPIFFE_ENDPOINT_SOCKET", "unix:///run/spire/sockets/agent.sock"),
		SpiffeTrustDomain:    getEnv("SPIFFE_TRUST_DOMAIN", "university.ecosystem"),
		SpiffeMyID:           getEnv("SPIFFE_MY_ID", "spiffe://university.ecosystem/ns/default/sa/ws-hub"),
		BackendSpiffeID:      getEnv("BACKEND_SPIFFE_ID", "spiffe://university.ecosystem/ns/default/sa/app"),
	}
}

// loadJWTSecrets reads JWT signing secrets from env vars.
// Prefers JWT_SECRETS (comma-separated list for rotation support);
// falls back to the legacy JWT_SECRET single-value env var.
func loadJWTSecrets() []string {
	if multi := os.Getenv("JWT_SECRETS"); multi != "" {
		return getEnvSlice("JWT_SECRETS", nil)
	}
	if single := os.Getenv("JWT_SECRET"); single != "" {
		return []string{single}
	}
	return nil
}

func getEnvSlice(key string, defaultValue []string) []string {
	valStr := os.Getenv(key)
	if valStr == "" {
		return defaultValue
	}
	parts := strings.Split(valStr, ",")
	var result []string
	for _, p := range parts {
		if trimmed := strings.TrimSpace(p); trimmed != "" {
			result = append(result, trimmed)
		}
	}
	return result
}

func getEnv(key, defaultValue string) string {
	if value := os.Getenv(key); value != "" {
		return value
	}
	return defaultValue
}

func getEnvFloat(key string, defaultValue float64) float64 {
	// LOW-W19: use strconv.ParseFloat instead of fmt.Sscan — ParseFloat is
	// purpose-built for this use-case and rejects trailing garbage (e.g. "1.5x")
	// that Sscan would silently accept by stopping at the first non-numeric char.
	valStr := os.Getenv(key)
	if valStr == "" {
		return defaultValue
	}
	val, err := strconv.ParseFloat(valStr, 64)
	if err != nil {
		return defaultValue
	}
	return val
}

func getEnvInt(key string, defaultValue int) int {
	valStr := os.Getenv(key)
	if valStr == "" {
		return defaultValue
	}
	val, err := strconv.Atoi(valStr)
	if err != nil {
		return defaultValue
	}
	return val
}
