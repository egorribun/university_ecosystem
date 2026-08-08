package config

import (
	"errors"
	"os"
	"testing"

	"github.com/stretchr/testify/assert"
)

// TD-33-12: Use FP_ prefix — SetEnvPrefix("FP") in Load() requires it.
func TestLoad_ReturnsDefaultValues(t *testing.T) {
	fpEnvVars := []string{
		"FP_GRPC_PORT", "FP_GRAPHQL_PORT", "FP_NATS_URL",
		"FP_TEMPORAL_HOST", "FP_MINIO_BUCKET", "FP_MINIO_ENDPOINT",
		"FP_MINIO_ACCESS_KEY", "FP_MINIO_SECRET_KEY", "FP_MINIO_SECURE",
	}
	originalEnvVars := make(map[string]string, len(fpEnvVars))
	for _, key := range fpEnvVars {
		originalEnvVars[key] = os.Getenv(key)
	}
	defer func() {
		for key, value := range originalEnvVars {
			if value == "" {
				assert.NoError(t, os.Unsetenv(key))
			} else {
				assert.NoError(t, os.Setenv(key, value))
			}
		}
	}()

	for key := range originalEnvVars {
		assert.NoError(t, os.Unsetenv(key))
	}

	t.Setenv("FP_JWT_SECRET", "dummy-secret-value-for-testing-purposes-only")
	cfg, err := Load()
	assert.NoError(t, err)

	assert.Equal(t, "50051", cfg.GRPCPort)
	assert.Equal(t, "8080", cfg.GraphQLPort)
	assert.Equal(t, "nats://nats:4222", cfg.NatsURL)
	assert.Equal(t, "temporal:7233", cfg.TemporalHost)
	assert.Equal(t, "uploads", cfg.MinioBucket)
	assert.Equal(t, "minio:9000", cfg.MinioEndpoint)
	assert.Equal(t, "minioadmin", cfg.MinioAccessKey)
	assert.Equal(t, "minioadmin", cfg.MinioSecretKey)
	assert.False(t, cfg.MinioSecure)
}

// TD-33-12: Use FP_ prefix — SetEnvPrefix("FP") in Load() requires it.
func TestLoad_ReadsEnvironmentVariables(t *testing.T) {
	t.Setenv("FP_GRPC_PORT", "9999")
	t.Setenv("FP_NATS_URL", "nats://custom:4222")
	t.Setenv("FP_JWT_SECRET", "dummy-secret-value-for-testing-purposes-only")

	cfg, err := Load()
	assert.NoError(t, err)

	assert.Equal(t, "9999", cfg.GRPCPort)
	assert.Equal(t, "nats://custom:4222", cfg.NatsURL)
}

func TestLoad_MissingCredentials(t *testing.T) {
	t.Setenv("FP_MINIO_ACCESS_KEY", "")
	_, err := Load()
	assert.Error(t, err)

	t.Setenv("FP_MINIO_ACCESS_KEY", "access")
	t.Setenv("FP_MINIO_SECRET_KEY", "")
	_, err = Load()
	assert.Error(t, err)
}

func TestLoad_MissingJWTSecretAndRSAPublicKey(t *testing.T) {
	t.Setenv("FP_JWT_SECRET", "")
	t.Setenv("FP_RSA_PUBLIC_KEY_PEM", "")
	_, err := Load()
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "either FP_JWT_SECRET or FP_RSA_PUBLIC_KEY_PEM must be set")
}

func TestLoad_RSAPublicKeySetOnly(t *testing.T) {
	t.Setenv("FP_JWT_SECRET", "")
	t.Setenv("FP_RSA_PUBLIC_KEY_PEM", "dummy-rsa-key-pem")
	cfg, err := Load()
	assert.NoError(t, err)
	assert.NotNil(t, cfg)
	assert.Equal(t, "dummy-rsa-key-pem", cfg.RSAPublicKeyPEM)
	assert.Empty(t, cfg.JWTSecret)
}

func TestLoad_BindEnvErrorIsReturned(t *testing.T) {
	oldBindEnv := bindEnvFunc
	t.Cleanup(func() { bindEnvFunc = oldBindEnv })
	bindEnvFunc = func(...string) error {
		return errors.New("synthetic bind failure")
	}

	_, err := Load()
	assert.ErrorContains(t, err, "failed to bind env")
	assert.ErrorContains(t, err, "synthetic bind failure")
}

func TestLoad_UnmarshalErrorIsReturned(t *testing.T) {
	oldUnmarshal := unmarshalConfigFunc
	t.Cleanup(func() { unmarshalConfigFunc = oldUnmarshal })
	unmarshalConfigFunc = func(any) error {
		return errors.New("synthetic unmarshal failure")
	}

	_, err := Load()
	assert.EqualError(t, err, "synthetic unmarshal failure")
}
