package config

import (
	"context"
	"fmt"
	"log/slog"
	"os"
	"strconv"
	"strings"
)

// getEnvFloat64 reads a float64 from the given environment variable, returning
// defaultValue if the variable is empty or unparseable.
func getEnvFloat64(key string, defaultValue float64) float64 {
	valStr := os.Getenv(key)
	if valStr == "" {
		return defaultValue
	}
	val, err := strconv.ParseFloat(valStr, 64)
	if err != nil {
		slog.WarnContext(context.Background(), "invalid float env var, using default",
			"key", key, "value", valStr, "default", defaultValue)
		return defaultValue
	}
	return val
}

// Config holds the gateway configuration.
type Config struct {
	Port       string
	BackendURL string
	RedisURL   string
	JWTSecret  string
	// JWKSPublicKeyPEM is the PEM-encoded RSA/EC public key used to verify RS256 tokens.
	// Optional. When empty, only HS256 tokens are accepted. Set JWKS_PUBLIC_KEY_PEM to
	// enable RS256 support without a round-trip to the Python JWKS endpoint at startup.
	JWKSPublicKeyPEM  string
	FileProcessorAddr string
	RateLimitRPS      int
	RateLimitBurst    int
	AllowedOrigins    []string
	SentryDSN         string
	Environment       string
	// MED-02 (audit 2026-03-11): Externalize hardcoded telemetry endpoints.
	OtelEndpoint string
	AppVersion   string
	// CRIT-02 (audit 2026-03-11): Toggle for gRPC TLS.
	GrpcUseTLS bool
	// InternalHMACSecret is the shared secret used to sign X-User-ID/X-Session-ID
	// headers set by this gateway (RZ-14-05). The backend verifies the resulting
	// X-Internal-Signature to reject requests that bypass the gateway.
	// Optional in dev; required in production for full zero-trust enforcement.
	InternalHMACSecret string
	// MOD-W17-03: JWKS hot-reload configuration.
	// When JWKSEndpoint is non-empty, the gateway periodically fetches the JWKS
	// from this URL and atomically swaps the RSA public key for RS256 verification.
	// JWKSPublicKeyPEM is still used as the initial/fallback key.
	JWKSEndpoint        string
	JWKSRefreshInterval int // seconds between JWKS fetches (default: 300 = 5 min)
	// SentryTracesSampleRate controls Sentry performance monitoring sample rate.
	// Default 1.0 (100%) for dev; recommend 0.1 (10%) for production.
	SentryTracesSampleRate float64
	// SPIFFE Workload API & mTLS configuration
	SpiffeEnabled         bool
	SpiffeEndpointSocket  string
	SpiffeTrustDomain     string
	SpiffeMyID            string
	FileProcessorSpiffeID string
	BackendSpiffeID       string
	// HTTP/3 QUIC & WebTransport Ingress Configuration
	H3Enabled      bool   // GATEWAY_H3_ENABLED (default: true)
	H3Port         string // GATEWAY_H3_PORT (default: "8443")
	H3AltSvcMaxAge int    // GATEWAY_H3_ALT_SVC_MAX_AGE (default: 2592000)
	TLSCertFile    string // TLS_CERT_FILE (optional in dev, required for prod H3)
	TLSKeyFile     string // TLS_KEY_FILE (optional in dev, required for prod H3)
	WsHubURL       string // WSHUB_URL (default: "http://ws-hub:8081")
}

// Load loads the configuration from environment variables
// It ensures critical secrets are present, enforcing a "Fail Secure" policy.
func Load() (*Config, error) {
	cfg := &Config{
		Port:              getEnv("GATEWAY_PORT", "8080"),
		BackendURL:        getEnv("BACKEND_URL", "http://backend:8000"),
		RedisURL:          getEnv("REDIS_URL", "redis://redis:6379/3"),
		JWTSecret:         os.Getenv("JWT_SECRET"),          // No default — fail secure
		JWKSPublicKeyPEM:  os.Getenv("JWKS_PUBLIC_KEY_PEM"), // Optional RS256 public key
		FileProcessorAddr: getEnv("FILE_PROCESSOR_ADDR", "file-processor:50051"),
		RateLimitRPS:      getEnvInt("RATE_LIMIT_RPS", 100),
		RateLimitBurst:    getEnvInt("RATE_LIMIT_BURST", 200),
		AllowedOrigins:    getEnvSlice("ALLOWED_ORIGINS", []string{"http://localhost:3000", "http://localhost:5173"}),
		SentryDSN:         getEnv("SENTRY_DSN", ""),
		Environment:       getEnv("VITE_ENVIRONMENT", "development"),
		OtelEndpoint:      getEnv("OTEL_EXPORTER_OTLP_ENDPOINT", "jaeger:4317"),
		AppVersion:        getEnv("APP_VERSION", "unknown"),
		// AUDIT-INFRA-05: Fail-closed — TLS on by default. Set GRPC_USE_TLS=false
		// ONLY for local dev (docker-compose.yml). Production/K8s inherit TLS=true.
		GrpcUseTLS: os.Getenv("GRPC_USE_TLS") != "false",
		// RZ-14-05: optional in dev, required in production.
		InternalHMACSecret: os.Getenv("INTERNAL_HMAC_SECRET"),
		// MOD-W17-03: JWKS hot-reload. Set JWKS_ENDPOINT to enable.
		JWKSEndpoint:        os.Getenv("JWKS_ENDPOINT"),
		JWKSRefreshInterval: getEnvInt("JWKS_REFRESH_INTERVAL", 300),
		// RZ-33-02: Configurable Sentry sample rate. Default 1.0 for dev;
		// recommend 0.1 for production (set SENTRY_TRACES_SAMPLE_RATE=0.1).
		SentryTracesSampleRate: getEnvFloat64("SENTRY_TRACES_SAMPLE_RATE", 1.0),
		SpiffeEnabled:         os.Getenv("SPIFFE_ENABLED") == "true",
		SpiffeEndpointSocket:  getEnv("SPIFFE_ENDPOINT_SOCKET", "unix:///run/spire/sockets/agent.sock"),
		SpiffeTrustDomain:     getEnv("SPIFFE_TRUST_DOMAIN", "university.ecosystem"),
		SpiffeMyID:            getEnv("SPIFFE_MY_ID", "spiffe://university.ecosystem/ns/default/sa/gateway"),
		FileProcessorSpiffeID: getEnv("FILE_PROCESSOR_SPIFFE_ID", "spiffe://university.ecosystem/ns/default/sa/file-processor"),
		BackendSpiffeID:       getEnv("BACKEND_SPIFFE_ID", "spiffe://university.ecosystem/ns/default/sa/app"),
		H3Enabled:             getEnvBool("GATEWAY_H3_ENABLED", true),
		H3Port:                getEnv("GATEWAY_H3_PORT", "8443"),
		H3AltSvcMaxAge:        getEnvInt("GATEWAY_H3_ALT_SVC_MAX_AGE", 2592000),
		TLSCertFile:           os.Getenv("TLS_CERT_FILE"),
		TLSKeyFile:            os.Getenv("TLS_KEY_FILE"),
		WsHubURL:              getEnv("WSHUB_URL", "http://ws-hub:8081"),
	}

	if cfg.JWTSecret == "" {
		// CRITICAL: Fail to start if no secret is provided.
		return nil, fmt.Errorf("JWT_SECRET environment variable is not set")
	}

	// RZ-33-02: If JWKS hot-reload is enabled but refresh interval is invalid,
	// fall back to the default (300s) to prevent tight-loop polling.
	if cfg.JWKSEndpoint != "" && cfg.JWKSRefreshInterval <= 0 {
		cfg.JWKSRefreshInterval = 300
	}

	return cfg, nil
}

func getEnv(key, defaultValue string) string {
	if value := os.Getenv(key); value != "" {
		return value
	}
	return defaultValue
}

func getEnvInt(key string, defaultValue int) int {
	valStr := os.Getenv(key)
	if valStr == "" {
		return defaultValue
	}
	val, err := strconv.Atoi(valStr)
	if err != nil {
		slog.WarnContext(context.Background(), "invalid integer env var, using default",
			"key", key, "value", valStr, "default", defaultValue)
		return defaultValue
	}
	return val
}

func getEnvSlice(key string, defaultValue []string) []string {
	valStr := os.Getenv(key)
	if valStr == "" {
		return defaultValue
	}
	// Split by comma
	parts := strings.Split(valStr, ",")
	var result []string
	for _, p := range parts {
		if trimmed := strings.TrimSpace(p); trimmed != "" {
			result = append(result, trimmed)
		}
	}
	if len(result) == 0 {
		return defaultValue
	}
	return result
}

func getEnvBool(key string, defaultValue bool) bool {
	valStr := os.Getenv(key)
	if valStr == "" {
		return defaultValue
	}
	val, err := strconv.ParseBool(valStr)
	if err != nil {
		slog.WarnContext(context.Background(), "invalid boolean env var, using default",
			"key", key, "value", valStr, "default", defaultValue)
		return defaultValue
	}
	return val
}
