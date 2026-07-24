package hub

import (
	"net/http"
	"testing"
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
