package config

import (
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestInternalHTTPMTLSConfiguration(t *testing.T) {
	assert.Error(t, ValidateInternalHTTPMTLS(nil))
	assert.NoError(t, ValidateInternalHTTPMTLS(&Config{}))
	for _, endpoint := range []string{"", "http://backend/jwks", "https://", "https://:8000/jwks", "https://%zz", "https://backend/jwks?q=1", "https://backend/jwks#x", "https://name@backend/jwks", " https://backend/jwks", "https://backend/jwks\n"} {
		cfg := &Config{InternalHTTPMTLSEnabled: true, JWKSURL: endpoint}
		assert.ErrorContains(t, ValidateInternalHTTPMTLS(cfg), "FP_JWKS_URL", endpoint)
	}
	cfg := &Config{InternalHTTPMTLSEnabled: true, JWKSURL: "https://backend:8000/.well-known/jwks.json"}
	for _, identity := range []string{"", "https://backend", "spiffe://university.ecosystem/ns/../backend", "spiffe://university.ecosystem/*"} {
		cfg.BackendSpiffeID = identity
		assert.ErrorContains(t, ValidateInternalHTTPMTLS(cfg), "FP_BACKEND_SPIFFE_ID")
	}
	cfg.BackendSpiffeID = "spiffe://university.ecosystem/ns/default/sa/backend"
	assert.NoError(t, ValidateInternalHTTPMTLS(cfg))
	assert.False(t, cfg.SpiffeEnabled, "HTTP mTLS must not enable SPIFFE on the gRPC listener")
}

func TestLoadInternalHTTPMTLSEnvironment(t *testing.T) {
	t.Setenv("FP_INTERNAL_HTTP_MTLS_ENABLED", "true")
	t.Setenv("FP_SPIFFE_ENABLED", "false")
	t.Setenv("FP_JWKS_URL", "https://backend:8000/.well-known/jwks.json")
	t.Setenv("FP_BACKEND_SPIFFE_ID", "spiffe://university.ecosystem/ns/default/sa/backend")
	t.Setenv("FP_ENVIRONMENT", "development")
	cfg, err := Load()
	require.NoError(t, err)
	if cfg == nil {
		t.Fatal("configuration is missing")
	}
	assert.True(t, cfg.InternalHTTPMTLSEnabled)
	assert.False(t, cfg.SpiffeEnabled)
	assert.Equal(t, "spiffe://university.ecosystem/ns/default/sa/backend", cfg.BackendSpiffeID)
	t.Setenv("FP_BACKEND_SPIFFE_ID", "")
	_, err = Load()
	assert.ErrorContains(t, err, "FP_BACKEND_SPIFFE_ID")
	t.Setenv("FP_INTERNAL_HTTP_MTLS_ENABLED", "not-a-boolean")
	_, err = Load()
	assert.Error(t, err, "a misspelled flag must not silently disable mTLS")
}
