package middleware

import (
	"crypto/tls"
	"crypto/x509"
	"net/http"
	"net/http/httptest"
	"sync/atomic"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// AUD-373: JWKS refreshes against the internal backend origin must verify the
// backend with the SPIFFE trust bundle. Public endpoints keep default verification.
func TestJWKSHTTPClientUsesConfiguredBackendTLS(t *testing.T) {
	var redirected atomic.Int32
	target := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		redirected.Add(1)
		w.WriteHeader(http.StatusOK)
	}))
	t.Cleanup(target.Close)
	server := httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/redirect" {
			http.Redirect(w, r, target.URL, http.StatusFound)
			return
		}
		w.WriteHeader(http.StatusOK)
	}))
	t.Cleanup(server.Close)

	roots := x509.NewCertPool()
	roots.AddCert(server.Certificate())

	var configured JWTMiddleware
	configured.SetJWKSTLSConfig(&tls.Config{RootCAs: roots, MinVersion: tls.VersionTLS12, ClientSessionCache: tls.NewLRUClientSessionCache(1)})
	original := configured.JWKSTLSConfig()
	require.NotNil(t, original)

	client := configured.newJWKSHTTPClient()
	transport, ok := client.Transport.(*http.Transport)
	require.True(t, ok, "internal JWKS client must carry a custom transport")
	require.NotNil(t, transport.TLSClientConfig, "internal JWKS client must carry the backend TLS configuration")
	assert.True(t, transport.DisableKeepAlives)
	assert.Nil(t, transport.TLSClientConfig.ClientSessionCache)
	assert.NotNil(t, original.ClientSessionCache)
	assert.NotSame(t, original, transport.TLSClientConfig)

	resp, err := client.Get(server.URL)
	require.NoError(t, err)
	require.NotNil(t, resp)
	assert.Equal(t, http.StatusOK, resp.StatusCode)
	require.NoError(t, resp.Body.Close())
	require.NotNil(t, client.CheckRedirect, "internal JWKS client must install the redirect guard")
	assert.ErrorIs(t, client.CheckRedirect(nil, nil), http.ErrUseLastResponse)
	redirectResponse, err := client.Get(server.URL + "/redirect")
	require.NoError(t, err)
	require.NotNil(t, redirectResponse)
	assert.Equal(t, http.StatusFound, redirectResponse.StatusCode)
	require.NoError(t, redirectResponse.Body.Close())
	assert.Zero(t, redirected.Load(), "internal JWKS must not downgrade or follow another origin")

	var defaults JWTMiddleware
	assert.Nil(t, defaults.JWKSTLSConfig())
	assert.Nil(t, defaults.newJWKSHTTPClient().Transport)
	rejected, err := defaults.newJWKSHTTPClient().Get(server.URL)
	if rejected != nil {
		// http.Client returns a response only alongside a nil error, so this close
		// is not expected to run; it keeps the body-close contract explicit for bodyclose.
		require.NoError(t, rejected.Body.Close())
	}
	require.Error(t, err, "default verification must reject a certificate outside the system roots")
}
