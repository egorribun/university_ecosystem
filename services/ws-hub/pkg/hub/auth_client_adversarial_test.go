package hub

import (
	"net/http"
	"testing"

	"github.com/stretchr/testify/require"
	"github.com/university-ecosystem/services/pkg/spiffe"
)

func TestWithSPIFFESilentFallbackOnNilClient(t *testing.T) {
	client := NewInternalAPIAuthClient("http://localhost:8000", nil)

	// Call WithSPIFFE with a nil spiffe.Client
	client.WithSPIFFE(nil, "spiffe://university.ecosystem/ns/default/sa/app")

	// Verify that transport TLSClientConfig remains nil (plaintext HTTP)
	if tr, ok := client.httpClient.Transport.(*http.Transport); ok {
		if tr.TLSClientConfig != nil {
			t.Fatalf("expected TLSClientConfig to be nil when spiffeClient is nil")
		}
	}
}

func TestWithSPIFFEInvalidClientFailsClosed(t *testing.T) {
	client := NewInternalAPIAuthClient("http://localhost:8000", nil)

	require.Panics(t, func() {
		client.WithSPIFFE(&spiffe.Client{}, "spiffe://university.ecosystem/ns/default/sa/app")
	})
}

func TestWithSPIFFEEmptyBackendIDSkipsConfiguration(t *testing.T) {
	client := NewInternalAPIAuthClient("http://localhost:8000", nil)

	// An enabled SPIFFE client without a backend identity is deliberately a
	// no-op: there is no peer identity to validate and no TLS config to install.
	client.WithSPIFFE(&spiffe.Client{}, "")

	transport, ok := client.httpClient.Transport.(*http.Transport)
	require.True(t, ok)
	require.Nil(t, transport.TLSClientConfig)
}
