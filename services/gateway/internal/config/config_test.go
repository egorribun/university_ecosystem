package config

import (
	"os"
	"testing"

	"github.com/stretchr/testify/assert"
)

func TestGetEnv_ReturnsDefaultWhenNotSet(t *testing.T) {
	key := "TEST_UNSET_VARIABLE_XYZ"
	if err := os.Unsetenv(key); err != nil {
		t.Fatalf("failed to unset env: %v", err)
	}

	result := getEnv(key, "default_value")

	assert.Equal(t, "default_value", result)
}

func TestGetEnv_ReturnsEnvValueWhenSet(t *testing.T) {
	key := "TEST_SET_VARIABLE_XYZ"
	expected := "custom_value"
	if err := os.Setenv(key, expected); err != nil {
		t.Fatalf("failed to set env: %v", err)
	}
	defer func() {
		if err := os.Unsetenv(key); err != nil {
			t.Errorf("failed to unset env: %v", err)
		}
	}()

	result := getEnv(key, "default_value")

	assert.Equal(t, expected, result)
}

func TestGetEnvInt_ReturnsDefaultWhenNotSet(t *testing.T) {
	key := "TEST_UNSET_INT_XYZ"
	if err := os.Unsetenv(key); err != nil {
		t.Fatalf("failed to unset env: %v", err)
	}

	result := getEnvInt(key, 42)

	assert.Equal(t, 42, result)
}

func TestGetEnvInt_ReturnsDefaultWhenEmpty(t *testing.T) {
	key := "TEST_EMPTY_INT_XYZ"
	if err := os.Setenv(key, ""); err != nil {
		t.Fatalf("failed to set env: %v", err)
	}
	defer func() {
		if err := os.Unsetenv(key); err != nil {
			t.Errorf("failed to unset env: %v", err)
		}
	}()

	result := getEnvInt(key, 100)

	assert.Equal(t, 100, result)
}

func TestGetEnvInt_ParsesValidInteger(t *testing.T) {
	key := "TEST_VALID_INT_XYZ"
	if err := os.Setenv(key, "200"); err != nil {
		t.Fatalf("failed to set env: %v", err)
	}
	defer func() {
		if err := os.Unsetenv(key); err != nil {
			t.Errorf("failed to unset env: %v", err)
		}
	}()

	result := getEnvInt(key, 0)

	assert.Equal(t, 200, result)
}

func TestGetEnvInt_ReturnsDefaultOnInvalidInteger(t *testing.T) {
	key := "TEST_INVALID_INT_XYZ"
	if err := os.Setenv(key, "not_a_number"); err != nil {
		t.Fatalf("failed to set env: %v", err)
	}
	defer func() {
		if err := os.Unsetenv(key); err != nil {
			t.Errorf("failed to unset env: %v", err)
		}
	}()

	result := getEnvInt(key, 99)

	assert.Equal(t, 99, result)
}

func TestGetEnvInt_ParsesNegativeInteger(t *testing.T) {
	key := "TEST_NEGATIVE_INT_XYZ"
	if err := os.Setenv(key, "-50"); err != nil {
		t.Fatalf("failed to set env: %v", err)
	}
	defer func() {
		if err := os.Unsetenv(key); err != nil {
			t.Errorf("failed to unset env: %v", err)
		}
	}()

	result := getEnvInt(key, 0)

	assert.Equal(t, -50, result)
}

func TestGetEnvInt_ParsesZero(t *testing.T) {
	key := "TEST_ZERO_INT_XYZ"
	if err := os.Setenv(key, "0"); err != nil {
		t.Fatalf("failed to set env: %v", err)
	}
	defer func() {
		if err := os.Unsetenv(key); err != nil {
			t.Errorf("failed to unset env: %v", err)
		}
	}()

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
		restoreEnv(t, "JWT_SECRET", originalJWT)
		restoreEnv(t, "BACKEND_URL", originalBackend)
		restoreEnv(t, "GATEWAY_PORT", originalPort)
		restoreEnv(t, "REDIS_URL", originalRedis)
		restoreEnv(t, "FILE_PROCESSOR_ADDR", originalFileProc)
		restoreEnv(t, "RATE_LIMIT_RPS", originalRPS)
		restoreEnv(t, "RATE_LIMIT_BURST", originalBurst)
	}()

	if err := os.Setenv("JWT_SECRET", "test-secret-key"); err != nil {
		t.Fatalf("failed to set env: %v", err)
	}
	if err := os.Setenv("BACKEND_URL", "http://test-backend:8000"); err != nil {
		t.Fatalf("failed to set env: %v", err)
	}
	if err := os.Setenv("GATEWAY_PORT", "9090"); err != nil {
		t.Fatalf("failed to set env: %v", err)
	}
	if err := os.Setenv("REDIS_URL", "redis://test-redis:6379"); err != nil {
		t.Fatalf("failed to set env: %v", err)
	}
	if err := os.Setenv("FILE_PROCESSOR_ADDR", "test-processor:50051"); err != nil {
		t.Fatalf("failed to set env: %v", err)
	}
	if err := os.Setenv("RATE_LIMIT_RPS", "50"); err != nil {
		t.Fatalf("failed to set env: %v", err)
	}
	if err := os.Setenv("RATE_LIMIT_BURST", "100"); err != nil {
		t.Fatalf("failed to set env: %v", err)
	}

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
		restoreEnv(t, "JWT_SECRET", originalJWT)
		restoreEnv(t, "BACKEND_URL", originalBackend)
		restoreEnv(t, "GATEWAY_PORT", originalPort)
	}()

	if err := os.Setenv("JWT_SECRET", "required-secret"); err != nil {
		t.Fatalf("failed to set env: %v", err)
	}
	if err := os.Unsetenv("GATEWAY_PORT"); err != nil {
		t.Fatalf("failed to unset env: %v", err)
	}
	if err := os.Unsetenv("BACKEND_URL"); err != nil {
		t.Fatalf("failed to unset env: %v", err)
	}

	cfg, err := Load()
	assert.NoError(t, err)
	assert.Equal(t, "8080", cfg.Port)
	assert.Equal(t, "http://backend:8000", cfg.BackendURL)
	assert.Equal(t, 100, cfg.RateLimitRPS)
	assert.Equal(t, 200, cfg.RateLimitBurst)
}

func TestLoad_ReturnsErrorWhenJWTSecretMissing(t *testing.T) {
	originalJWT := os.Getenv("JWT_SECRET")
	if err := os.Unsetenv("JWT_SECRET"); err != nil {
		t.Fatalf("failed to unset env: %v", err)
	}
	defer restoreEnv(t, "JWT_SECRET", originalJWT)

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

func restoreEnv(t *testing.T, key, value string) {
	t.Helper()
	if value == "" {
		if err := os.Unsetenv(key); err != nil {
			t.Errorf("failed to restore (unset) env %s: %v", key, err)
		}
	} else {
		if err := os.Setenv(key, value); err != nil {
			t.Errorf("failed to restore (set) env %s: %v", key, err)
		}
	}
}
