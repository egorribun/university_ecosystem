package config

import (
	"errors"
	"os"
	"strings"
	"testing"

	"github.com/stretchr/testify/assert"
)

// TD-33-12: Use FP_ prefix — SetEnvPrefix("FP") in Load() requires it.
func TestLoad_ReturnsDefaultValues(t *testing.T) {
	fpEnvVars := []string{
		"FP_GRPC_PORT", "FP_GRAPHQL_PORT", "FP_NATS_URL",
		"FP_TEMPORAL_HOST", "FP_MINIO_BUCKET", "FP_MINIO_ENDPOINT",
		"FP_MINIO_ACCESS_KEY", "FP_MINIO_SECRET_KEY", "FP_MINIO_SECURE",
		"FP_TEMPORAL_TLS_DISABLED", "FP_ENVIRONMENT",
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
	assert.True(t, cfg.TemporalTLSDisabled)
	assert.Equal(t, "development", cfg.Environment)
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
	t.Setenv("FP_RSA_PUBLIC_KEY_FILE", "")
	_, err := Load()
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "FP_RSA_PUBLIC_KEY_FILE")
}

func TestLoad_RejectsInsecureProductionDataPlanes(t *testing.T) {
	t.Setenv("FP_JWT_SECRET", "dummy-secret-value-for-testing-purposes-only")
	t.Setenv("FP_ENVIRONMENT", "production")
	t.Setenv("FP_MINIO_SECURE", "true")
	t.Setenv("FP_TEMPORAL_TLS_DISABLED", "false")
	t.Setenv("FP_OTLP_INSECURE", "false")
	t.Setenv("FP_GRPC_TLS_CERT_FILE", "/run/secrets/internal-grpc-mtls/tls.crt")
	t.Setenv("FP_GRPC_TLS_KEY_FILE", "/run/secrets/internal-grpc-mtls/tls.key")
	t.Setenv("FP_GRPC_CLIENT_CA_FILE", "/run/secrets/internal-grpc-mtls/ca.crt")
	t.Setenv("FP_GRPC_ALLOWED_CLIENT_URIS", "spiffe://university.ecosystem/ns/university-ecosystem/sa/gateway,spiffe://university.ecosystem/ns/university-ecosystem/sa/file-processor-probe")
	secureCfg, err := Load()
	assert.NoError(t, err)
	assert.Equal(t, "production", secureCfg.Environment)
	assert.True(t, secureCfg.MinioSecure)
	assert.False(t, secureCfg.TemporalTLSDisabled)

	t.Run("MinIO", func(t *testing.T) {
		t.Setenv("FP_MINIO_SECURE", "false")
		_, err := Load()
		assert.ErrorContains(t, err, "FP_MINIO_SECURE=true")
	})

	t.Run("Temporal", func(t *testing.T) {
		t.Setenv("FP_TEMPORAL_TLS_DISABLED", "true")
		_, err := Load()
		assert.ErrorContains(t, err, "FP_TEMPORAL_TLS_DISABLED=false")
	})

	t.Run("OTLP", func(t *testing.T) {
		t.Setenv("FP_OTLP_INSECURE", "true")
		_, err := Load()
		assert.ErrorContains(t, err, "FP_OTLP_INSECURE=false")
	})
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

func TestLoad_RSAPublicKeyFileSetOnly(t *testing.T) {
	t.Setenv("FP_JWT_SECRET", "")
	t.Setenv("FP_RSA_PUBLIC_KEY_PEM", "")
	t.Setenv("FP_RSA_PUBLIC_KEY_FILE", "/run/secrets/jwt_rs256.pub.pem")

	cfg, err := Load()
	assert.NoError(t, err)
	assert.NotNil(t, cfg)
	assert.Equal(t, "/run/secrets/jwt_rs256.pub.pem", cfg.RSAPublicKeyFile)
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

func TestLoad_ReleaseWithoutSPIFFERequiresConventionalMTLSFiles(t *testing.T) {
	required := map[string]string{
		"FP_GRPC_TLS_CERT_FILE":       "FP_GRPC_TLS_CERT_FILE",
		"FP_GRPC_TLS_KEY_FILE":        "FP_GRPC_TLS_KEY_FILE",
		"FP_GRPC_CLIENT_CA_FILE":      "FP_GRPC_CLIENT_CA_FILE",
		"FP_GRPC_ALLOWED_CLIENT_URIS": "FP_GRPC_ALLOWED_CLIENT_URIS",
	}
	for missing, expected := range required {
		t.Run(missing, func(t *testing.T) {
			t.Setenv("FP_JWT_SECRET", "dummy-secret-value-for-testing-purposes-only")
			t.Setenv("FP_ENVIRONMENT", "staging")
			t.Setenv("FP_MINIO_SECURE", "true")
			t.Setenv("FP_TEMPORAL_TLS_DISABLED", "false")
			t.Setenv("FP_OTLP_INSECURE", "false")
			t.Setenv("FP_SPIFFE_ENABLED", "false")
			for name := range required {
				t.Setenv(name, "/run/secrets/internal-grpc-mtls/value")
			}
			t.Setenv(missing, "")

			cfg, err := Load()

			assert.Nil(t, cfg)
			assert.ErrorContains(t, err, expected)
		})
	}
}

func TestValidateReleaseConfig_SPIFFEProvidesReleaseTransportIdentity(t *testing.T) {
	cfg := &Config{
		MinioSecure:         true,
		TemporalTLSDisabled: false,
		OTLPInsecure:        false,
		SpiffeEnabled:       true,
	}

	assert.NoError(t, validateReleaseConfig(cfg, "staging"))
}

func TestLoad_ReleaseValidatesAllowedClientURIs(t *testing.T) {
	setSecureRelease := func(t *testing.T, allowed string) {
		t.Helper()
		t.Setenv("FP_JWT_SECRET", "dummy-secret-value-for-testing-purposes-only")
		t.Setenv("FP_ENVIRONMENT", "staging")
		t.Setenv("FP_MINIO_SECURE", "true")
		t.Setenv("FP_TEMPORAL_TLS_DISABLED", "false")
		t.Setenv("FP_OTLP_INSECURE", "false")
		t.Setenv("FP_SPIFFE_ENABLED", "false")
		t.Setenv("FP_GRPC_TLS_CERT_FILE", "/run/secrets/internal-grpc-mtls-server/tls.crt")
		t.Setenv("FP_GRPC_TLS_KEY_FILE", "/run/secrets/internal-grpc-mtls-server/tls.key")
		t.Setenv("FP_GRPC_CLIENT_CA_FILE", "/run/secrets/internal-grpc-mtls-server/ca.crt")
		t.Setenv("FP_GRPC_ALLOWED_CLIENT_URIS", allowed)
	}

	t.Run("accepts exact absolute URI SAN allowlist", func(t *testing.T) {
		setSecureRelease(t, "spiffe://university.ecosystem/ns/university-ecosystem/sa/gateway,spiffe://university.ecosystem/ns/university-ecosystem/sa/file-processor-probe")
		cfg, err := Load()
		assert.NoError(t, err)
		assert.Equal(t, []string{
			"spiffe://university.ecosystem/ns/university-ecosystem/sa/gateway",
			"spiffe://university.ecosystem/ns/university-ecosystem/sa/file-processor-probe",
		}, cfg.GRPCAllowedClientURIs)
	})

	for name, value := range map[string]string{
		"relative":       "gateway",
		"missing host":   "spiffe:///ns/university-ecosystem/sa/gateway",
		"query alias":    "spiffe://university.ecosystem/ns/university-ecosystem/sa/gateway?alias=true",
		"fragment alias": "spiffe://university.ecosystem/ns/university-ecosystem/sa/gateway#alias",
		"whitespace":     " spiffe://university.ecosystem/ns/university-ecosystem/sa/gateway",
		"wrong scheme":   "https://university.ecosystem/ns/university-ecosystem/sa/gateway",
		"scheme case":    "SPIFFE://university.ecosystem/ns/university-ecosystem/sa/gateway",
		"host case":      "spiffe://UNIVERSITY.ecosystem/ns/university-ecosystem/sa/gateway",
		"port alias":     "spiffe://university.ecosystem:443/ns/university-ecosystem/sa/gateway",
		"dot segment":    "spiffe://university.ecosystem/ns/university-ecosystem/sa/../sa/gateway",
		"percent escape": "spiffe://university.ecosystem/ns/university-ecosystem/sa/gate%77ay",
		"long domain":    "spiffe://" + strings.Repeat("a", 254) + "/ns/gateway",
		"empty label":    "spiffe://university..ecosystem/ns/gateway",
		"invalid label":  "spiffe://university_ecosystem/ns/gateway",
		"duplicate":      "spiffe://university.ecosystem/ns/university-ecosystem/sa/gateway,spiffe://university.ecosystem/ns/university-ecosystem/sa/gateway",
	} {
		t.Run(name, func(t *testing.T) {
			setSecureRelease(t, value)
			cfg, err := Load()
			assert.Nil(t, cfg)
			assert.ErrorContains(t, err, "FP_GRPC_ALLOWED_CLIENT_URIS")
		})
	}
}

func TestLoad_DevelopmentAllowsPlaintextGRPCWithoutMTLSFiles(t *testing.T) {
	t.Setenv("FP_JWT_SECRET", "dummy-secret-value-for-testing-purposes-only")
	t.Setenv("FP_ENVIRONMENT", "development")
	t.Setenv("FP_SPIFFE_ENABLED", "false")
	for _, name := range []string{
		"FP_GRPC_TLS_CERT_FILE", "FP_GRPC_TLS_KEY_FILE", "FP_GRPC_CLIENT_CA_FILE",
	} {
		t.Setenv(name, "")
	}

	cfg, err := Load()

	assert.NoError(t, err)
	assert.NotNil(t, cfg)
}
