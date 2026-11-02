package config

import (
	"os"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// AUD-373: the gateway must not send token-bearing backend requests in
// plaintext once INTERNAL_HTTP_MTLS_ENABLED is set, and an unknown flag value
// must fail closed rather than read as disabled.
func TestParseInternalHTTPMTLSEnabled(t *testing.T) {
	cases := []struct {
		name    string
		raw     string
		want    bool
		wantErr bool
	}{
		{name: "unset", raw: "", want: false},
		{name: "blank", raw: "   ", want: false},
		{name: "false", raw: "false", want: false},
		{name: "zero", raw: "0", want: false},
		{name: "true", raw: " true ", want: true},
		{name: "one", raw: "1", want: true},
		{name: "typo", raw: "tru", wantErr: true},
		{name: "free text", raw: "yes please", wantErr: true},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			got, err := parseInternalHTTPMTLSEnabled(tc.raw)
			if tc.wantErr {
				require.ErrorContains(t, err, "INTERNAL_HTTP_MTLS_ENABLED")
				return
			}
			require.NoError(t, err)
			assert.Equal(t, tc.want, got)
		})
	}
}

// Both SPIFFE_ENABLED and INTERNAL_HTTP_MTLS_ENABLED switch the backend hop to
// mTLS, so each flag independently requires an https BACKEND_URL.
func TestValidateBackendTransportRequiresHTTPSWhenEnabled(t *testing.T) {
	const validSpiffeID = "spiffe://university.ecosystem/ns/default/sa/app"

	cases := []struct {
		name         string
		internalMTLS bool
		spiffe       bool
		backendURL   string
		spiffeID     string
		wantErr      string
	}{
		{name: "disabled ignores plaintext backend", backendURL: "http://backend:8000", spiffeID: validSpiffeID},
		{name: "internal enabled https backend", internalMTLS: true, backendURL: "https://backend:8000", spiffeID: validSpiffeID},
		{name: "internal enabled plaintext backend", internalMTLS: true, backendURL: "http://backend:8000", spiffeID: validSpiffeID, wantErr: "BACKEND_URL must be an https URL"},
		{name: "internal enabled empty backend", internalMTLS: true, backendURL: "", spiffeID: validSpiffeID, wantErr: "BACKEND_URL must be an https URL"},
		{name: "internal enabled https without host", internalMTLS: true, backendURL: "https://", spiffeID: validSpiffeID, wantErr: "BACKEND_URL must be an https URL"},
		{name: "internal enabled malformed backend", internalMTLS: true, backendURL: "://broken", spiffeID: validSpiffeID, wantErr: "BACKEND_URL must be an https URL"},
		{name: "internal enabled non canonical SPIFFE ID", internalMTLS: true, backendURL: "https://backend:8000", spiffeID: "spiffe:///no-trust-domain", wantErr: "BACKEND_SPIFFE_ID"},
		{name: "spiffe enabled https backend", spiffe: true, backendURL: "https://backend:8000", spiffeID: validSpiffeID},
		{name: "spiffe enabled plaintext backend", spiffe: true, backendURL: "http://backend:8000", spiffeID: validSpiffeID, wantErr: "BACKEND_URL must be an https URL"},
		{name: "spiffe enabled empty backend", spiffe: true, backendURL: "", spiffeID: validSpiffeID, wantErr: "BACKEND_URL must be an https URL"},
		{name: "spiffe enabled malformed backend", spiffe: true, backendURL: "://broken", spiffeID: validSpiffeID, wantErr: "BACKEND_URL must be an https URL"},
		{name: "spiffe enabled non canonical SPIFFE ID", spiffe: true, backendURL: "https://backend:8000", spiffeID: "spiffe:///no-trust-domain", wantErr: "BACKEND_SPIFFE_ID"},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			cfg := &Config{
				SpiffeEnabled:           tc.spiffe,
				InternalHTTPMTLSEnabled: tc.internalMTLS,
				BackendURL:              tc.backendURL,
				BackendSpiffeID:         tc.spiffeID,
			}
			err := validateBackendTransport(cfg)
			if tc.wantErr != "" {
				require.ErrorContains(t, err, tc.wantErr)
				return
			}
			require.NoError(t, err)
		})
	}
}

func TestBackendMTLSEnabledCombinesSpiffeAndInternalFlag(t *testing.T) {
	assert.False(t, (&Config{}).BackendMTLSEnabled())
	assert.True(t, (&Config{SpiffeEnabled: true}).BackendMTLSEnabled())
	assert.True(t, (&Config{InternalHTTPMTLSEnabled: true}).BackendMTLSEnabled())
}

// unsetEnvForTest removes key for the duration of the test and restores its
// previous state afterwards. t.Setenv cannot express "unset": an empty *_FILE
// value is still a configured secret file and fails closed.
func unsetEnvForTest(t *testing.T, key string) {
	t.Helper()
	previous, existed := os.LookupEnv(key)
	require.NoError(t, os.Unsetenv(key))
	t.Cleanup(func() {
		if existed {
			if err := os.Setenv(key, previous); err != nil {
				t.Errorf("failed to restore env %s: %v", key, err)
			}
			return
		}
		if err := os.Unsetenv(key); err != nil {
			t.Errorf("failed to restore (unset) env %s: %v", key, err)
		}
	})
}

func TestLoadRejectsInvalidInternalHTTPMTLSFlag(t *testing.T) {
	for _, key := range []string{"REVOCATION_REDIS_URL", "JWT_SECRET", "REDIS_URL", "INTERNAL_HMAC_SECRET", "FILE_PROCESSING_CAPABILITY_SECRET"} {
		unsetEnvForTest(t, key+"_FILE")
	}
	t.Setenv("INTERNAL_HTTP_MTLS_ENABLED", "not-a-boolean")

	cfg, err := loadFromEnvironmentChecked()

	require.ErrorContains(t, err, "INTERNAL_HTTP_MTLS_ENABLED must be a boolean")
	assert.Nil(t, cfg)
}

func TestValidateConfigPropagatesBackendTransportRefusal(t *testing.T) {
	cfg := &Config{
		Environment:             "development",
		JWTSecret:               randomStrongTestValue(t),
		JWTAudience:             "university-ecosystem-api",
		RevocationRedisURL:      "redis://redis:6379/0",
		RateLimitRPS:            100,
		RateLimitBurst:          200,
		InternalHTTPMTLSEnabled: true,
		BackendURL:              "http://backend:8000",
		BackendSpiffeID:         "spiffe://university.ecosystem/ns/default/sa/app",
	}

	require.ErrorContains(t, validateConfig(cfg), "BACKEND_URL must be an https URL")
	cfg.BackendURL = "https://backend:8000"
	require.NoError(t, validateConfig(cfg))
}

func TestValidateConfigPropagatesSpiffeBackendTransportRefusal(t *testing.T) {
	cfg := &Config{
		Environment:        "development",
		JWTSecret:          randomStrongTestValue(t),
		JWTAudience:        "university-ecosystem-api",
		RevocationRedisURL: "redis://redis:6379/0",
		RateLimitRPS:       100,
		RateLimitBurst:     200,
		SpiffeEnabled:      true,
		BackendURL:         "http://backend:8000",
		BackendSpiffeID:    "spiffe://university.ecosystem/ns/default/sa/app",
	}

	require.ErrorContains(t, validateConfig(cfg), "BACKEND_URL must be an https URL")
	cfg.BackendURL = "https://backend:8000"
	require.NoError(t, validateConfig(cfg))
}
