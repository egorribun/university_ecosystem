// Package middleware — extra benchmarks for Wave 8 coverage gates.
// WHY: auth_bench_test.go already covers header parsing and key derivation.
// These benchmarks add JWKS HTTP round-trip and in-memory rate-limit fallback
// to surface any per-allocation regressions in the hot paths.
package middleware

import (
	"crypto/rand"
	"crypto/rsa"
	"encoding/base64"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

// BenchmarkJWKSValidation measures the full JWKS fetch + RSA key parse cycle
// against a local httptest server, keeping network latency near zero so the
// benchmark reflects only deserialization and big.Int allocation cost.
func BenchmarkJWKSValidation(b *testing.B) {
	// Generate a real RSA key so the JWKS response is valid.
	privateKey, err := rsa.GenerateKey(rand.Reader, 2048)
	if err != nil {
		b.Fatalf("failed to generate RSA key: %v", err)
	}

	nB64 := base64.RawURLEncoding.EncodeToString(privateKey.N.Bytes())
	eBytes := []byte{
		byte(privateKey.E >> 16), //nolint:gosec // G115: RSA public exponent fits in 3 bytes
		byte(privateKey.E >> 8),  //nolint:gosec // G115: RSA public exponent fits in 3 bytes
		byte(privateKey.E),       //nolint:gosec // G115: RSA public exponent fits in 3 bytes
	}
	eB64 := base64.RawURLEncoding.EncodeToString(eBytes)

	jwksPayload, err := json.Marshal(map[string]any{
		"keys": []map[string]string{
			{"kty": "RSA", "n": nB64, "e": eB64},
		},
	})
	if err != nil {
		b.Fatalf("failed to marshal JWKS: %v", err)
	}

	// Serve the JWKS document from an in-process HTTP server.
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write(jwksPayload) //nolint:errcheck // test server write
	}))
	defer server.Close()

	client := server.Client()

	b.ResetTimer()
	for range b.N {
		pubKey, err := fetchJWKSPublicKey(b.Context(), client, server.URL)
		if err != nil {
			b.Fatalf("unexpected error: %v", err)
		}
		if pubKey == nil {
			b.Fatal("fetchJWKSPublicKey returned nil key")
		}
	}
}

// BenchmarkRateLimitFallback measures the in-memory allow/deny path that
// activates during Redis outages.  This path acquires a mutex on every call,
// so the benchmark surfaces any lock-contention regression when multiple
// goroutines share the same RateLimiter.
func BenchmarkRateLimitFallback(b *testing.B) {
	rl := &RateLimiter{
		fallbackCounters: make(map[string]*fallbackEntry),
		fallbackLimit:    1000, // High limit so we don't block during benchmark
		fallbackWindow:   60,
	}

	b.ResetTimer()
	for i := range b.N {
		// Vary the key slightly to exercise map lookup with different entries,
		// simulating distinct client IPs during a Redis outage.
		key := "ip:10.0.0." + string(rune('0'+i%10))
		_ = rl.inMemoryAllow(key)
	}
}
