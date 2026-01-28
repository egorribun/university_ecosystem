package config

import (
	"fmt"
	"os"
	"strconv"
	"strings"
)

// Config holds the gateway configuration
type Config struct {
	Port              string
	BackendURL        string
	RedisURL          string
	JWTSecret         string
	FileProcessorAddr string
	RateLimitRPS      int
	RateLimitBurst    int
	AllowedOrigins    []string
	SentryDSN         string
	Environment       string
}

// Load loads the configuration from environment variables
// It ensures critical secrets are present, enforcing a "Fail Secure" policy.
func Load() (*Config, error) {
	cfg := &Config{
		Port:              getEnv("GATEWAY_PORT", "8080"),
		BackendURL:        getEnv("BACKEND_URL", "http://backend:8000"),
		RedisURL:          getEnv("REDIS_URL", "redis://redis:6379/3"),
		JWTSecret:         os.Getenv("JWT_SECRET"), // No default value for security
		FileProcessorAddr: getEnv("FILE_PROCESSOR_ADDR", "file-processor:50051"),
		RateLimitRPS:      getEnvInt("RATE_LIMIT_RPS", 100),
		RateLimitBurst:    getEnvInt("RATE_LIMIT_BURST", 200),
		AllowedOrigins:    getEnvSlice("ALLOWED_ORIGINS", []string{"http://localhost:3000", "http://localhost:5173"}),
		SentryDSN:         getEnv("SENTRY_DSN", ""),
		Environment:       getEnv("VITE_ENVIRONMENT", "development"),
	}

	if cfg.JWTSecret == "" {
		// CRITICAL: Fail to start if no secret is provided.
		return nil, fmt.Errorf("JWT_SECRET environment variable is not set")
	}

	if cfg.BackendURL == "" {
		return nil, fmt.Errorf("BACKEND_URL must be set")
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
		fmt.Printf("Warning: Invalid integer for %s: %s. Using default: %d\n", key, valStr, defaultValue)
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
