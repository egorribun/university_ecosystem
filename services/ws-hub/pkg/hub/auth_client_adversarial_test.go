package hub

import (
	"net/http"
	"testing"

	"github.com/stretchr/testify/require"
	"github.com/university-ecosystem/services/pkg/spiffe"
)

func TestWithSPIFFESilentFallbackOnNilClient(t *testing.T) {
	client := mustNewTestAuthClient(t, "http://localhost:8000", "", nil)

	// A nil spiffe.Client is not a configuration error: the transport stays plaintext.
	require.NoError(t, client.WithSPIFFE(nil, "spiffe://university.ecosystem/ns/default/sa/app"))

	transport, ok := client.httpClient.Transport.(*http.Transport)
	require.True(t, ok)
	require.Nil(t, transport.TLSClientConfig)
}

func TestWithSPIFFEInvalidClientFailsClosed(t *testing.T) {
	client := mustNewTestAuthClient(t, "http://localhost:8000", "", nil)

	// The refusal is returned, not panicked, so startup reports it through main().
	require.ErrorContains(t, client.WithSPIFFE(&spiffe.Client{}, "spiffe://university.ecosystem/ns/default/sa/app"),
		"must use https when SPIFFE mTLS is configured")

	transport, ok := client.httpClient.Transport.(*http.Transport)
	require.True(t, ok)
	require.Nil(t, transport.TLSClientConfig)
}

func TestWithSPIFFEEmptyBackendIDSkipsConfiguration(t *testing.T) {
	client := mustNewTestAuthClient(t, "http://localhost:8000", "", nil)

	// An enabled SPIFFE client without a backend identity is deliberately a
	// no-op: there is no peer identity to validate and no TLS config to install.
	require.NoError(t, client.WithSPIFFE(&spiffe.Client{}, ""))

	transport, ok := client.httpClient.Transport.(*http.Transport)
	require.True(t, ok)
	require.Nil(t, transport.TLSClientConfig)
}
