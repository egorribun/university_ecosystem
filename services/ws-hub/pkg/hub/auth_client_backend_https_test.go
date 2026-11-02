package hub

import (
	"crypto/tls"
	"fmt"
	"net/http"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"github.com/university-ecosystem/services/pkg/spiffe"
)

// AUD-373: SPIFFE mTLS on the backend hop is only effective over https. An
// http base URL must fail closed instead of sending the internal token in clear.
func TestWithSPIFFERejectsNonHTTPSBackendURL(t *testing.T) {
	previous := authClientTLSConfigFunc
	t.Cleanup(func() { authClientTLSConfigFunc = previous })
	authClientTLSConfigFunc = func(*spiffe.Client, string) (*tls.Config, error) {
		return &tls.Config{MinVersion: tls.VersionTLS13}, nil
	}

	for _, baseURL := range []string{"http://backend:8000", "ftp://backend:8000", "https://", "://broken"} {
		client := NewInternalAPIAuthClientWithToken(baseURL, "", nil)
		require.PanicsWithValue(t,
			fmt.Sprintf("auth client base URL %q must use https when SPIFFE mTLS is configured", baseURL),
			func() { client.WithSPIFFE(&spiffe.Client{}, "spiffe://university.ecosystem/ns/default/sa/app") },
		)
		transport, ok := client.httpClient.Transport.(*http.Transport)
		require.True(t, ok)
		assert.Nil(t, transport.TLSClientConfig)
	}
}

func TestWithSPIFFEInstallsTLSOnHTTPSBackendURL(t *testing.T) {
	previous := authClientTLSConfigFunc
	t.Cleanup(func() { authClientTLSConfigFunc = previous })
	configured := &tls.Config{MinVersion: tls.VersionTLS13}
	authClientTLSConfigFunc = func(*spiffe.Client, string) (*tls.Config, error) {
		return configured, nil
	}

	client := NewInternalAPIAuthClientWithToken("HTTPS://backend.internal:8000", "", nil)

	assert.Same(t, client, client.WithSPIFFE(&spiffe.Client{}, "spiffe://university.ecosystem/ns/default/sa/app"))
	transport, ok := client.httpClient.Transport.(*http.Transport)
	require.True(t, ok)
	assert.Same(t, configured, transport.TLSClientConfig)
}

func TestIsHTTPSBaseURL(t *testing.T) {
	for _, raw := range []string{"", "/relative", "https://", "http://backend:8000", "https://%zz", "://broken"} {
		t.Run(raw, func(t *testing.T) {
			assert.False(t, isHTTPSBaseURL(raw))
		})
	}
	for _, raw := range []string{"https://backend:8000", "HTTPS://backend.internal:8000"} {
		t.Run(raw, func(t *testing.T) {
			assert.True(t, isHTTPSBaseURL(raw))
		})
	}
}
