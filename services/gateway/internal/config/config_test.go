package config

import (
	"os"
	"testing"

	"github.com/stretchr/testify/assert"
)

func TestGetEnv_ReturnsDefaultWhenNotSet(t *testing.T) {
	key := "TEST_UNSET_VARIABLE_XYZ"
	_ = os.Unsetenv(key)

	result := getEnv(key, "default_value")

	assert.Equal(t, "default_value", result)
}

func TestGetEnv_ReturnsEnvValueWhenSet(t *testing.T) {
	key := "TEST_SET_VARIABLE_XYZ"
	expected := "custom_value"
	t.Setenv(key, expected)

	result := getEnv(key, "default_value")

	assert.Equal(t, expected, result)
}

func TestGetEnvInt_ReturnsDefaultWhenNotSet(t *testing.T) {
	key := "TEST_UNSET_INT_XYZ"
	_ = os.Unsetenv(key)

	result := getEnvInt(key, 42)

	assert.Equal(t, 42, result)
}

func TestGetEnvInt_ReturnsDefaultWhenEmpty(t *testing.T) {
	key := "TEST_EMPTY_INT_XYZ"
	t.Setenv(key, "")

	result := getEnvInt(key, 100)

	assert.Equal(t, 100, result)
}

func TestGetEnvInt_ParsesValidInteger(t *testing.T) {
	key := "TEST_VALID_INT_XYZ"
	t.Setenv(key, "200")

	result := getEnvInt(key, 0)

	assert.Equal(t, 200, result)
}

func TestGetEnvInt_ReturnsDefaultOnInvalidInteger(t *testing.T) {
	key := "TEST_INVALID_INT_XYZ"
	t.Setenv(key, "not_a_number")

	result := getEnvInt(key, 99)

	assert.Equal(t, 99, result)
}

func TestGetEnvInt_ParsesNegativeInteger(t *testing.T) {
	key := "TEST_NEGATIVE_INT_XYZ"
	t.Setenv(key, "-50")

	result := getEnvInt(key, 0)

	assert.Equal(t, -50, result)
}

func TestGetEnvInt_ParsesZero(t *testing.T) {
	key := "TEST_ZERO_INT_XYZ"
	t.Setenv(key, "0")

	result := getEnvInt(key, 999)

	assert.Equal(t, 0, result)
}

func TestLoad_ReturnsConfigWithValidEnv(t *testing.T) {
	// Save original env
	originalJWT := os.Getenv("JWT_SECRET")
	originalBackend := os.Getenv("BACKEND_URL")
	originalPort := os.Getenv("GATEWAY_PORT")
	originalRedis := os.Getenv("REDIS_URL")
	originalFileProc := os.Getenv("FILE_PROCESSOR_ADDR")
	originalRPS := os.Getenv("RATE_LIMIT_RPS")
	originalBurst := os.Getenv("RATE_LIMIT_BURST")

	defer func() {
		restoreEnv("JWT_SECRET", originalJWT)
		restoreEnv("BACKEND_URL", originalBackend)
		restoreEnv("GATEWAY_PORT", originalPort)
		restoreEnv("REDIS_URL", originalRedis)
		restoreEnv("FILE_PROCESSOR_ADDR", originalFileProc)
		restoreEnv("RATE_LIMIT_RPS", originalRPS)
		restoreEnv("RATE_LIMIT_BURST", originalBurst)
	}()

	os.Setenv("JWT_SECRET", "test-secret-key")
	os.Setenv("BACKEND_URL", "http://test-backend:8000")
	os.Setenv("GATEWAY_PORT", "9090")
	os.Setenv("REDIS_URL", "redis://test-redis:6379")
	os.Setenv("FILE_PROCESSOR_ADDR", "test-processor:50051")
	os.Setenv("RATE_LIMIT_RPS", "50")
	os.Setenv("RATE_LIMIT_BURST", "100")

	cfg, err := Load()
	assert.NoError(t, err)
	assert.NotNil(t, cfg)
	assert.Equal(t, "9090", cfg.Port)
	assert.Equal(t, "http://test-backend:8000", cfg.BackendURL)
	assert.Equal(t, "redis://test-redis:6379", cfg.RedisURL)
	assert.Equal(t, "test-secret-key", cfg.JWTSecret)
	assert.Equal(t, "test-processor:50051", cfg.FileProcessorAddr)
	assert.Equal(t, 50, cfg.RateLimitRPS)
	assert.Equal(t, 100, cfg.RateLimitBurst)
}

func TestLoad_UsesDefaultValuesWithJWTSet(t *testing.T) {
	originalJWT := os.Getenv("JWT_SECRET")
	originalBackend := os.Getenv("BACKEND_URL")
	originalPort := os.Getenv("GATEWAY_PORT")

	defer func() {
		restoreEnv("JWT_SECRET", originalJWT)
		restoreEnv("BACKEND_URL", originalBackend)
		restoreEnv("GATEWAY_PORT", originalPort)
	}()

	os.Setenv("JWT_SECRET", "required-secret")
	os.Unsetenv("GATEWAY_PORT")
	os.Unsetenv("BACKEND_URL")

	cfg, err := Load()
	assert.NoError(t, err)
	assert.Equal(t, "8080", cfg.Port)
	assert.Equal(t, "http://backend:8000", cfg.BackendURL)
	assert.Equal(t, 100, cfg.RateLimitRPS)
	assert.Equal(t, 200, cfg.RateLimitBurst)
}

func TestLoad_ReturnsErrorWhenJWTSecretMissing(t *testing.T) {
	originalJWT := os.Getenv("JWT_SECRET")
	os.Unsetenv("JWT_SECRET")
	defer restoreEnv("JWT_SECRET", originalJWT)

	cfg, err := Load()
	assert.Error(t, err)
	assert.Nil(t, cfg)
	assert.Contains(t, err.Error(), "JWT_SECRET")
}

func TestConfig_StructFields(t *testing.T) {
	cfg := Config{
		Port:              "8080",
		BackendURL:        "http://localhost:8000",
		RedisURL:          "redis://localhost:6379",
		JWTSecret:         "secret",
		FileProcessorAddr: "localhost:50051",
		RateLimitRPS:      100,
		RateLimitBurst:    200,
	}

	assert.Equal(t, "8080", cfg.Port)
	assert.Equal(t, "http://localhost:8000", cfg.BackendURL)
	assert.Equal(t, "redis://localhost:6379", cfg.RedisURL)
	assert.Equal(t, "secret", cfg.JWTSecret)
	assert.Equal(t, "localhost:50051", cfg.FileProcessorAddr)
	assert.Equal(t, 100, cfg.RateLimitRPS)
	assert.Equal(t, 200, cfg.RateLimitBurst)
}

func restoreEnv(key, value string) {
	if value == "" {
		os.Unsetenv(key)
	} else {
		os.Setenv(key, value)
	}
}
