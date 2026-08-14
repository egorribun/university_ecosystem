package config

import (
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// TestEmpirical_FP_EnvPrefixEnforcement verifies that viper.SetEnvPrefix("FP")
// enforces the FP_ prefix requirement. Un-prefixed environment variables are IGNORED,
// while FP_-prefixed environment variables are correctly parsed.
func TestEmpirical_FP_EnvPrefixEnforcement(t *testing.T) {
	t.Run("Unprefixed env vars are ignored by viper", func(t *testing.T) {
		// Set un-prefixed variables
		t.Setenv("GRPC_PORT", "7777")
		t.Setenv("MINIO_BUCKET", "unprefixed-bucket")
		t.Setenv("JWT_SECRET", "unprefixed-secret-value-for-testing-only")

		// Ensure FP_ prefixed overrides are NOT set
		t.Setenv("FP_GRPC_PORT", "")
		t.Setenv("FP_MINIO_BUCKET", "")
		t.Setenv("FP_JWT_SECRET", "")
		t.Setenv("FP_RSA_PUBLIC_KEY_PEM", "")
		t.Setenv("FP_RSA_PUBLIC_KEY_FILE", "")
		t.Setenv("FP_MINIO_ACCESS_KEY", "minioadmin")
		t.Setenv("FP_MINIO_SECRET_KEY", "minioadmin")

		// Load config. Since FP_JWT_SECRET is unset, Load should fail with missing secret error.
		cfg, err := Load()
		require.Error(t, err, "Load must fail because unprefixed JWT_SECRET is ignored and FP_JWT_SECRET is missing")
		assert.Contains(t, err.Error(), "FP_RSA_PUBLIC_KEY_FILE")
		assert.Nil(t, cfg)
	})

	t.Run("FP_ prefixed env vars are properly bound", func(t *testing.T) {
		t.Setenv("FP_GRPC_PORT", "8888")
		t.Setenv("FP_MINIO_BUCKET", "prefixed-bucket")
		t.Setenv("FP_JWT_SECRET", "valid-fp-jwt-secret-value-for-testing-only")
		t.Setenv("FP_MINIO_ACCESS_KEY", "minioadmin")
		t.Setenv("FP_MINIO_SECRET_KEY", "minioadmin")

		cfg, err := Load()
		require.NoError(t, err, "Load should succeed when FP_ prefixed vars are set")
		require.NotNil(t, cfg)
		assert.Equal(t, "8888", cfg.GRPCPort, "GRPCPort must equal FP_GRPC_PORT value")
		assert.Equal(t, "prefixed-bucket", cfg.MinioBucket, "MinioBucket must equal FP_MINIO_BUCKET value")
		assert.Equal(t, "valid-fp-jwt-secret-value-for-testing-only", cfg.JWTSecret)
	})

	t.Run("FP_ prefixed env var overrides unprefixed env var when both exist", func(t *testing.T) {
		t.Setenv("GRPC_PORT", "1111")
		t.Setenv("FP_GRPC_PORT", "2222")
		t.Setenv("FP_JWT_SECRET", "valid-fp-jwt-secret-value-for-testing-only")
		t.Setenv("FP_MINIO_ACCESS_KEY", "minioadmin")
		t.Setenv("FP_MINIO_SECRET_KEY", "minioadmin")

		cfg, err := Load()
		require.NoError(t, err)
		require.NotNil(t, cfg)
		assert.Equal(t, "2222", cfg.GRPCPort, "FP_GRPC_PORT must take precedence over GRPC_PORT")
	})
}
