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

// TestGetEnvFloat64 covers getEnvFloat64: unset/empty → default, valid float
// parse, and the parse-error warn-path (previously uncovered). t.Setenv auto-
// restores via t.Cleanup, so there's no errcheck surface on os.Setenv.
func TestGetEnvFloat64(t *testing.T) {
	const key = "TEST_FLOAT64_XYZ"

	tests := []struct {
		name     string
		setEnv   bool
		envValue string
		def      float64
		want     float64
	}{
		{name: "unset returns default", setEnv: false, def: 1.0, want: 1.0},
		{name: "empty string returns default", setEnv: true, envValue: "", def: 0.5, want: 0.5},
		{name: "valid float is parsed", setEnv: true, envValue: "0.1", def: 1.0, want: 0.1},
		{name: "integer-looking float is parsed", setEnv: true, envValue: "2", def: 1.0, want: 2.0},
		{name: "negative float is parsed", setEnv: true, envValue: "-3.5", def: 1.0, want: -3.5},
		{name: "parse error returns default (warn path)", setEnv: true, envValue: "not_a_float", def: 0.25, want: 0.25},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			if tc.setEnv {
				t.Setenv(key, tc.envValue)
			} else if err := os.Unsetenv(key); err != nil {
				t.Fatalf("failed to unset env: %v", err)
			}

			got := getEnvFloat64(key, tc.def)

			assert.Equal(t, tc.want, got)
		})
	}
}

// TestGetEnvSlice covers getEnvSlice: unset/empty → default, comma-split with
// per-part TrimSpace + skip-empty, and the all-empty-after-trim fallback
// (previously uncovered). The "whitespace is NOT a separator" case pins the
// strings.Split(s, ",") contract (guards against a future strings.Fields swap).
func TestGetEnvSlice(t *testing.T) {
	const key = "TEST_SLICE_XYZ"

	tests := []struct {
		name     string
		setEnv   bool
		envValue string
		def      []string
		want     []string
	}{
		{name: "unset returns default", setEnv: false, def: []string{"a", "b"}, want: []string{"a", "b"}},
		{name: "empty string returns default", setEnv: true, envValue: "", def: []string{"x"}, want: []string{"x"}},
		{name: "single item is trimmed", setEnv: true, envValue: "  one  ", def: []string{"fallback"}, want: []string{"one"}},
		{name: "comma-separated items split and trimmed", setEnv: true, envValue: "a, b ,c", def: []string{"fallback"}, want: []string{"a", "b", "c"}},
		{name: "empty-after-trim parts are skipped", setEnv: true, envValue: "a,,  ,b", def: []string{"fallback"}, want: []string{"a", "b"}},
		{name: "all-empty-after-trim returns default", setEnv: true, envValue: " , ,  ", def: []string{"fallback-1", "fallback-2"}, want: []string{"fallback-1", "fallback-2"}},
		{name: "whitespace is not a separator (only comma)", setEnv: true, envValue: "alpha beta", def: []string{"fallback"}, want: []string{"alpha beta"}},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			if tc.setEnv {
				t.Setenv(key, tc.envValue)
			} else if err := os.Unsetenv(key); err != nil {
				t.Fatalf("failed to unset env: %v", err)
			}

			got := getEnvSlice(key, tc.def)

			assert.Equal(t, tc.want, got)
		})
	}
}

func TestLoad_JWKSRefreshIntervalFallback(t *testing.T) {
	originalJWT := os.Getenv("JWT_SECRET")
	originalBackend := os.Getenv("BACKEND_URL")
	originalJWKSEnd := os.Getenv("JWKS_ENDPOINT")
	originalJWKSRefresh := os.Getenv("JWKS_REFRESH_INTERVAL")
	defer func() {
		restoreEnv(t, "JWT_SECRET", originalJWT)
		restoreEnv(t, "BACKEND_URL", originalBackend)
		restoreEnv(t, "JWKS_ENDPOINT", originalJWKSEnd)
		restoreEnv(t, "JWKS_REFRESH_INTERVAL", originalJWKSRefresh)
	}()

	t.Setenv("JWT_SECRET", "secret")
	t.Setenv("JWKS_ENDPOINT", "http://auth/jwks")
	t.Setenv("JWKS_REFRESH_INTERVAL", "-10")

	cfg, err := Load()
	assert.NoError(t, err)
	assert.NotNil(t, cfg)
	assert.Equal(t, 300, cfg.JWKSRefreshInterval)
}

func TestGetEnvBool(t *testing.T) {
	const key = "TEST_BOOL_XYZ"

	tests := []struct {
		name     string
		setEnv   bool
		envValue string
		def      bool
		want     bool
	}{
		{name: "unset returns default true", setEnv: false, def: true, want: true},
		{name: "unset returns default false", setEnv: false, def: false, want: false},
		{name: "valid true string is parsed", setEnv: true, envValue: "true", def: false, want: true},
		{name: "valid false string is parsed", setEnv: true, envValue: "false", def: true, want: false},
		{name: "invalid boolean returns default", setEnv: true, envValue: "not_a_bool", def: true, want: true},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			if tc.setEnv {
				t.Setenv(key, tc.envValue)
			} else {
				_ = os.Unsetenv(key)
			}

			got := getEnvBool(key, tc.def)
			assert.Equal(t, tc.want, got)
		})
	}
}

func TestLoad_H3AndWebTransportDefaults(t *testing.T) {
	t.Setenv("JWT_SECRET", "test-secret-at-least-32-chars-long")

	cfg, err := Load()
	assert.NoError(t, err)
	assert.True(t, cfg.H3Enabled)
	assert.Equal(t, "8443", cfg.H3Port)
	assert.Equal(t, 2592000, cfg.H3AltSvcMaxAge)
	assert.Equal(t, "http://ws-hub:8081", cfg.WsHubURL)
}
