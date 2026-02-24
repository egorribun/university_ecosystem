package config

import (
	"fmt"
	"os"
	"strings"
)

type Config struct {
	Port           string
	NatsURL        string
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
	// TrustedProxies is a list of IP addresses or ranges (CIDR) that are allowed
	// to provide the real client IP via X-Forwarded-For. (RZ-5)
	TrustedProxies []string
	// SendBufferSize is the size of the per-client outgoing message channel.
	// 256 slots * ~10 KB/msg ≈ 2.5 MB per concurrent connection. (TD-5)
	SendBufferSize int
	// BroadcastBufferSize is the size of the global message channel.
	// sized for NATS burst peaks (default 4096). (TD-5)
	BroadcastBufferSize int
}

func LoadConfig() *Config {
	return &Config{
		Port:           getEnv("WS_HUB_PORT", "8081"),
		NatsURL:        getEnv("NATS_URL", "nats://nats:4222"),
		JWTSecrets:     loadJWTSecrets(),
		SentryDSN:            getEnv("SENTRY_DSN", ""),
		Environment:          getEnv("VITE_ENVIRONMENT", "development"),
		AllowedOrigins:       getEnvSlice("ALLOWED_ORIGINS", []string{"http://localhost:3000", "http://localhost:5173"}),
		TrustedProxies:       getEnvSlice("TRUSTED_PROXIES", []string{"127.0.0.1", "::1"}),
		BackendURL:           getEnv("BACKEND_INTERNAL_URL", "http://backend:8000"),
		JWKSURL:              getEnv("JWKS_URL", "http://backend:8000/.well-known/jwks.json"),
		SendBufferSize:       getEnvInt("WS_SEND_BUFFER_SIZE", 256),
		BroadcastBufferSize:  getEnvInt("WS_BROADCAST_BUFFER_SIZE", 4096),
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

func getEnvInt(key string, defaultValue int) int {
	valStr := os.Getenv(key)
	if valStr == "" {
		return defaultValue
	}
	var val int
	if _, err := fmt.Sscan(valStr, &val); err != nil {
		return defaultValue
	}
	return val
}
