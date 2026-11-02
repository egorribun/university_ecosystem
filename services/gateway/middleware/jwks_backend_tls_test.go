package middleware

import (
	"crypto/tls"
	"crypto/x509"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// AUD-373: JWKS refreshes against the internal backend origin must verify the
// backend with the SPIFFE trust bundle. Public endpoints keep default verification.
func TestJWKSHTTPClientUsesConfiguredBackendTLS(t *testing.T) {
	server := httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))
	t.Cleanup(server.Close)

	roots := x509.NewCertPool()
	roots.AddCert(server.Certificate())

	var configured JWTMiddleware
	configured.SetJWKSTLSConfig(&tls.Config{RootCAs: roots, MinVersion: tls.VersionTLS12})
	require.NotNil(t, configured.JWKSTLSConfig())

	resp, err := configured.newJWKSHTTPClient().Get(server.URL)
	require.NoError(t, err)
	if resp == nil {
		t.Fatal("TLS request returned no response")
	}
	assert.Equal(t, http.StatusOK, resp.StatusCode)
	require.NoError(t, resp.Body.Close())

	var defaults JWTMiddleware
	assert.Nil(t, defaults.JWKSTLSConfig())
	assert.Nil(t, defaults.newJWKSHTTPClient().Transport)
	rejected, err := defaults.newJWKSHTTPClient().Get(server.URL)
	if rejected != nil {
		require.NoError(t, rejected.Body.Close())
	}
	require.Error(t, err, "default verification must reject a certificate outside the system roots")
}
