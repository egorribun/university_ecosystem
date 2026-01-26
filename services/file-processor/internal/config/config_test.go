package config

import (
	"testing"

	"github.com/stretchr/testify/assert"
)

func TestLoad_ReturnsDefaultValues(t *testing.T) {
	// t.Setenv automatically isolates env vars per test
	// Unset all to test defaults
	envVars := []string{
		"GRPC_PORT", "GRAPHQL_PORT", "NATS_URL", "TEMPORAL_HOST",
		"MINIO_BUCKET", "MINIO_ENDPOINT", "MINIO_ACCESS_KEY",
		"MINIO_SECRET_KEY", "MINIO_SECURE",
	}
	for _, key := range envVars {
		t.Setenv(key, "")
	}

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

func TestLoad_ReadsEnvironmentVariables(t *testing.T) {
	t.Setenv("GRPC_PORT", "9999")
	t.Setenv("NATS_URL", "nats://custom:4222")

	cfg, err := Load()
	assert.NoError(t, err)

	assert.Equal(t, "9999", cfg.GRPCPort)
	assert.Equal(t, "nats://custom:4222", cfg.NatsURL)
}
