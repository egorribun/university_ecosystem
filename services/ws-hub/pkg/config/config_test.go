package config

import (
	"os"
	"testing"

	"github.com/stretchr/testify/require"
)

func TestLoadConfig_DefaultsAndOverrides(t *testing.T) {
	// W188 polish-v2 — use t.Setenv (Go 1.17+) for auto-restore at test end,
	// eliminating manual backup/restore boilerplate + errcheck violations on
	// the prior `os.Setenv` pattern (.golangci.yml errcheck.check-blank: true
	// per MOD-05 Wave 10 audit). t.Setenv saves the original value (or unset
	// state) before setting, and restores it via t.Cleanup automatically.
	//
	// For env vars that we want to start UNSET (not preserved), we still need
	// to clear them; use `t.Setenv` with empty string then `os.Unsetenv` via
	// `require.NoError`. The test still verifies defaults (section 1) so a
	// non-empty value bleeding from the developer's shell would be caught.
	envVars := []string{
		"WS_HUB_PORT", "NATS_URL", "NATS_USER", "NATS_PASSWORD",
		"JWT_SECRETS", "JWT_SECRET", "SENTRY_DSN", "VITE_ENVIRONMENT",
		"ALLOWED_ORIGINS", "TRUSTED_PROXIES", "BACKEND_INTERNAL_URL",
		"JWKS_URL", "WS_SEND_BUFFER_SIZE", "WS_BROADCAST_BUFFER_SIZE",
		"WS_BROADCAST_WORKERS", "WS_HUB_INTERNAL_SECRET", "WS_HUB_MAX_CLIENTS",
		"WS_CLIENT_MSG_RATE_LIMIT", "WS_CLIENT_MSG_BURST", "WS_TICKET_TTL_SECONDS",
		"REDIS_URL", "REDIS_PASSWORD", "REDIS_DB",
	}
	// Clear env at test start (each Unsetenv is benign if var already unset).
	for _, env := range envVars {
		require.NoError(t, os.Unsetenv(env))
	}

	// 1. Test defaults
	cfg := LoadConfig()
	require.Equal(t, "8081", cfg.Port)
	require.Equal(t, "nats://nats:4222", cfg.NatsURL)
	require.Equal(t, "", cfg.NatsUser)
	require.Equal(t, "", cfg.NatsPassword)
	require.Nil(t, cfg.JWTSecrets)
	require.Equal(t, "", cfg.SentryDSN)
	require.Equal(t, "development", cfg.Environment)
	require.Equal(t, []string{"http://localhost:3000", "http://localhost:5173"}, cfg.AllowedOrigins)
	require.Equal(t, []string{"127.0.0.1", "::1"}, cfg.TrustedProxies)
	require.Contains(t, cfg.TrustedProxiesSet, "127.0.0.1")
	require.Contains(t, cfg.TrustedProxiesSet, "::1")
	require.Empty(t, cfg.TrustedCIDRs)
	require.Equal(t, "http://backend:8000", cfg.BackendURL)
	require.Equal(t, "http://backend:8000/.well-known/jwks.json", cfg.JWKSURL)
	require.Equal(t, 256, cfg.SendBufferSize)
	require.Equal(t, 4096, cfg.BroadcastBufferSize)
	require.Equal(t, "", cfg.InternalSecret)
	require.Equal(t, 10000, cfg.MaxClients)
	require.Equal(t, 10.0, cfg.ClientMsgRateLimit)
	require.Equal(t, 20, cfg.ClientMsgRateBurst)
	require.Equal(t, 15, cfg.TicketTTLSeconds)
	require.Equal(t, "redis:6379", cfg.RedisURL)
	require.Equal(t, "", cfg.RedisPassword)
	require.Equal(t, 0, cfg.RedisDB)

	// 2. Test overrides and CIDR parsing (t.Setenv auto-restores at cleanup)
	t.Setenv("WS_HUB_PORT", "9090")
	t.Setenv("NATS_URL", "nats://localhost:4222")
	t.Setenv("NATS_USER", "testuser")
	t.Setenv("NATS_PASSWORD", "testpass")
	t.Setenv("JWT_SECRETS", "secret-a, secret-b")
	t.Setenv("SENTRY_DSN", "https://sentry")
	t.Setenv("VITE_ENVIRONMENT", "production")
	t.Setenv("ALLOWED_ORIGINS", "https://app.example.com")
	t.Setenv("TRUSTED_PROXIES", "10.0.0.1, 192.168.1.0/24, invalid-cidr/abc")
	t.Setenv("BACKEND_INTERNAL_URL", "http://backend-prod:8000")
	t.Setenv("JWKS_URL", "http://backend-prod:8000/jwks")
	t.Setenv("WS_SEND_BUFFER_SIZE", "512")
	t.Setenv("WS_BROADCAST_BUFFER_SIZE", "8192")
	t.Setenv("WS_BROADCAST_WORKERS", "6")
	t.Setenv("WS_HUB_INTERNAL_SECRET", "supersecret")
	t.Setenv("WS_HUB_MAX_CLIENTS", "500")
	t.Setenv("WS_CLIENT_MSG_RATE_LIMIT", "25.5")
	t.Setenv("WS_CLIENT_MSG_BURST", "50")
	t.Setenv("WS_TICKET_TTL_SECONDS", "30")
	t.Setenv("REDIS_URL", "redis-prod:6379")
	t.Setenv("REDIS_PASSWORD", "redissecret")
	t.Setenv("REDIS_DB", "2")

	cfg = LoadConfig()
	require.Equal(t, "9090", cfg.Port)
	require.Equal(t, "nats://localhost:4222", cfg.NatsURL)
	require.Equal(t, "testuser", cfg.NatsUser)
	require.Equal(t, "testpass", cfg.NatsPassword)
	require.Equal(t, []string{"secret-a", "secret-b"}, cfg.JWTSecrets)
	require.Equal(t, "https://sentry", cfg.SentryDSN)
	require.Equal(t, "production", cfg.Environment)
	require.Equal(t, []string{"https://app.example.com"}, cfg.AllowedOrigins)
	require.Equal(t, []string{"10.0.0.1", "192.168.1.0/24", "invalid-cidr/abc"}, cfg.TrustedProxies)
	require.Contains(t, cfg.TrustedProxiesSet, "10.0.0.1")
	require.Len(t, cfg.TrustedCIDRs, 1)
	require.Equal(t, "192.168.1.0/24", cfg.TrustedCIDRs[0].String())
	require.Equal(t, "http://backend-prod:8000", cfg.BackendURL)
	require.Equal(t, "http://backend-prod:8000/jwks", cfg.JWKSURL)
	require.Equal(t, 512, cfg.SendBufferSize)
	require.Equal(t, 8192, cfg.BroadcastBufferSize)
	require.Equal(t, 6, cfg.BroadcastWorkers)
	require.Equal(t, "supersecret", cfg.InternalSecret)
	require.Equal(t, 500, cfg.MaxClients)
	require.Equal(t, 25.5, cfg.ClientMsgRateLimit)
	require.Equal(t, 50, cfg.ClientMsgRateBurst)
	require.Equal(t, 30, cfg.TicketTTLSeconds)
	require.Equal(t, "redis-prod:6379", cfg.RedisURL)
	require.Equal(t, "redissecret", cfg.RedisPassword)
	require.Equal(t, 2, cfg.RedisDB)

	// 3. Test legacy single JWT_SECRET fallback
	require.NoError(t, os.Unsetenv("JWT_SECRETS"))
	t.Setenv("JWT_SECRET", "single-secret")
	cfg = LoadConfig()
	require.Equal(t, []string{"single-secret"}, cfg.JWTSecrets)

	// 4. Test invalid float, int, and bool inputs to verify fallback to default
	t.Setenv("WS_SEND_BUFFER_SIZE", "invalid-int")
	t.Setenv("WS_BROADCAST_BUFFER_SIZE", "invalid-int")
	t.Setenv("WS_BROADCAST_WORKERS", "invalid-int")
	t.Setenv("WS_HUB_MAX_CLIENTS", "invalid-int")
	t.Setenv("WS_CLIENT_MSG_RATE_LIMIT", "invalid-float")
	t.Setenv("WS_CLIENT_MSG_BURST", "invalid-int")
	t.Setenv("WS_TICKET_TTL_SECONDS", "invalid-int")
	t.Setenv("REDIS_DB", "invalid-int")
	t.Setenv("ENABLE_JETSTREAM", "invalid-bool")

	cfg = LoadConfig()
	require.Equal(t, 256, cfg.SendBufferSize)
	require.Equal(t, 4096, cfg.BroadcastBufferSize)
	require.Equal(t, 10000, cfg.MaxClients)
	require.Equal(t, 10.0, cfg.ClientMsgRateLimit)
	require.Equal(t, 20, cfg.ClientMsgRateBurst)
	require.Equal(t, 15, cfg.TicketTTLSeconds)
	require.Equal(t, 0, cfg.RedisDB)
	require.True(t, cfg.EnableJetStream)

	t.Setenv("ENABLE_JETSTREAM", "false")
	cfg = LoadConfig()
	require.False(t, cfg.EnableJetStream)
}
