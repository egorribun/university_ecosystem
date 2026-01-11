package config

import (
	"os"
	"testing"

	"github.com/stretchr/testify/assert"
)

func TestLoad_ReturnsDefaultValues(t *testing.T) {
	originalEnvVars := map[string]string{
		"GRPC_PORT":        os.Getenv("GRPC_PORT"),
		"GRAPHQL_PORT":     os.Getenv("GRAPHQL_PORT"),
		"NATS_URL":         os.Getenv("NATS_URL"),
		"TEMPORAL_HOST":    os.Getenv("TEMPORAL_HOST"),
		"MINIO_BUCKET":     os.Getenv("MINIO_BUCKET"),
		"MINIO_ENDPOINT":   os.Getenv("MINIO_ENDPOINT"),
		"MINIO_ACCESS_KEY": os.Getenv("MINIO_ACCESS_KEY"),
		"MINIO_SECRET_KEY": os.Getenv("MINIO_SECRET_KEY"),
		"MINIO_SECURE":     os.Getenv("MINIO_SECURE"),
	}
	defer func() {
		for key, value := range originalEnvVars {
			if value == "" {
				os.Unsetenv(key)
			} else {
				os.Setenv(key, value)
			}
		}
	}()

	for key := range originalEnvVars {
		os.Unsetenv(key)
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
	originalGRPCPort := os.Getenv("GRPC_PORT")
	originalNatsURL := os.Getenv("NATS_URL")
	defer func() {
		if originalGRPCPort == "" {
			os.Unsetenv("GRPC_PORT")
		} else {
			os.Setenv("GRPC_PORT", originalGRPCPort)
		}
		if originalNatsURL == "" {
			os.Unsetenv("NATS_URL")
		} else {
			os.Setenv("NATS_URL", originalNatsURL)
		}
	}()

	os.Setenv("GRPC_PORT", "9999")
	os.Setenv("NATS_URL", "nats://custom:4222")

	cfg, err := Load()
	assert.NoError(t, err)

	assert.Equal(t, "9999", cfg.GRPCPort)
	assert.Equal(t, "nats://custom:4222", cfg.NatsURL)
}
