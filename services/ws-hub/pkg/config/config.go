package config

import (
	"os"
	"strings"
)

type Config struct {
	Port           string
	NatsURL        string
	JWTSecret      string
	AllowedOrigins []string
	SentryDSN      string
	Environment    string
	// BackendURL is the internal base URL of the Python FastAPI service.
	// Used by the hub to authorize room-join requests via InternalAPIAuthClient.
	BackendURL string
}

func LoadConfig() *Config {
	return &Config{
		Port:           getEnv("WS_HUB_PORT", "8081"),
		NatsURL:        getEnv("NATS_URL", "nats://nats:4222"),
		JWTSecret:      getEnv("JWT_SECRET", ""),
		AllowedOrigins: getEnvSlice("ALLOWED_ORIGINS", []string{"http://localhost:3000", "http://localhost:5173"}),
		SentryDSN:      getEnv("SENTRY_DSN", ""),
		Environment:    getEnv("VITE_ENVIRONMENT", "development"),
		BackendURL:     getEnv("BACKEND_INTERNAL_URL", "http://backend:8000"),
	}
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
