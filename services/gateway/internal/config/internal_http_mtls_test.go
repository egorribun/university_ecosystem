package config

import (
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

func TestValidateBackendTransportRequiresHTTPSWhenEnabled(t *testing.T) {
	const validSpiffeID = "spiffe://university.ecosystem/ns/default/sa/app"

	cases := []struct {
		name       string
		enabled    bool
		backendURL string
		spiffeID   string
		wantErr    string
	}{
		{name: "disabled ignores plaintext backend", enabled: false, backendURL: "http://backend:8000", spiffeID: validSpiffeID},
		{name: "enabled https backend", enabled: true, backendURL: "https://backend:8000", spiffeID: validSpiffeID},
		{name: "enabled plaintext backend", enabled: true, backendURL: "http://backend:8000", spiffeID: validSpiffeID, wantErr: "BACKEND_URL must be an https URL"},
		{name: "enabled empty backend", enabled: true, backendURL: "", spiffeID: validSpiffeID, wantErr: "BACKEND_URL must be an https URL"},
		{name: "enabled https without host", enabled: true, backendURL: "https://", spiffeID: validSpiffeID, wantErr: "BACKEND_URL must be an https URL"},
		{name: "enabled malformed backend", enabled: true, backendURL: "://broken", spiffeID: validSpiffeID, wantErr: "BACKEND_URL must be an https URL"},
		{name: "enabled non canonical SPIFFE ID", enabled: true, backendURL: "https://backend:8000", spiffeID: "spiffe:///no-trust-domain", wantErr: "BACKEND_SPIFFE_ID"},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			cfg := &Config{
				InternalHTTPMTLSEnabled: tc.enabled,
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
