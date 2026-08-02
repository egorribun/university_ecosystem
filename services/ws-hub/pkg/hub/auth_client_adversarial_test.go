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
