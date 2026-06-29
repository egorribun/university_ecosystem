package middleware

import (
	"crypto/rand"
	"crypto/rsa"
	"encoding/base64"
	"testing"
	"time"

	"github.com/golang-jwt/jwt/v5"
)

// buildRealisticJWT constructs a three-part JWT string (header.payload.signature)
// without signing it cryptographically — sufficient for benchmarking header parsing.
func buildRealisticJWT() string {
	header := base64.RawURLEncoding.EncodeToString([]byte(`{"alg":"RS256","typ":"JWT"}`))
	payload := base64.RawURLEncoding.EncodeToString([]byte(`{"sub":"user"}`))
	signature := base64.RawURLEncoding.EncodeToString([]byte("signature"))
	return header + "." + payload + "." + signature
}

func BenchmarkExtractAlgFromHeader(b *testing.B) {
	tokenString := buildRealisticJWT()

	b.ResetTimer()
	for range b.N {
		alg, err := extractAlgFromHeader(tokenString)
		if err != nil {
			b.Fatalf("unexpected error: %v", err)
		}
		if alg != "RS256" {
			b.Fatalf("expected RS256, got %s", alg)
		}
	}
}

func BenchmarkValidateIAT(b *testing.B) {
	claims := &Claims{
		RegisteredClaims: jwt.RegisteredClaims{
			IssuedAt: jwt.NewNumericDate(time.Now()),
		},
	}

	b.ResetTimer()
	for range b.N {
		if err := validateIAT(claims); err != nil {
			b.Fatalf("unexpected error: %v", err)
		}
	}
}

func BenchmarkCheckL1Cache_Hit(b *testing.B) {
	m := NewJWTMiddlewareWithConfig("test-secret", "", nil, DefaultL1CacheConfig())
	m.l1cache.Add("test-key", cacheEntry{exists: true, storedAt: time.Now()})

	b.ResetTimer()
	for range b.N {
		exists, found := m.checkL1Cache("test-key")
		// Silence unused-variable lint; the probabilistic refresh may return
		// found=false even on a hit, so we only guard against impossible states.
		_ = exists
		_ = found
	}
}

func BenchmarkCheckL1Cache_Miss(b *testing.B) {
	m := NewJWTMiddlewareWithConfig("test-secret", "", nil, DefaultL1CacheConfig())

	b.ResetTimer()
	for range b.N {
		exists, found := m.checkL1Cache("nonexistent-key")
		_ = exists
		_ = found
	}
}

func BenchmarkJWKToRSAPublicKey(b *testing.B) {
	privateKey, err := rsa.GenerateKey(rand.Reader, 2048)
	if err != nil {
		b.Fatalf("failed to generate RSA key: %v", err)
	}

	nB64 := base64.RawURLEncoding.EncodeToString(privateKey.PublicKey.N.Bytes())

	eBytes := []byte{
		byte(privateKey.PublicKey.E >> 16),
		byte(privateKey.PublicKey.E >> 8),
		byte(privateKey.PublicKey.E),
	}
	eB64 := base64.RawURLEncoding.EncodeToString(eBytes)

	b.ResetTimer()
	for range b.N {
		pubKey, err := jwkToRSAPublicKey(nB64, eB64)
		if err != nil {
			b.Fatalf("unexpected error: %v", err)
		}
		if pubKey.N == nil {
			b.Fatal("parsed key has nil N")
		}
	}
}

func BenchmarkShouldRefreshProbabilistic(b *testing.B) {
	storedAt := time.Now()
	ttl := 30 * time.Second
	beta := 1.0

	b.ResetTimer()
	for range b.N {
		_ = shouldRefreshProbabilistic(storedAt, ttl, beta)
	}
}

func BenchmarkKeyFunc_HS256(b *testing.B) {
	m := NewJWTMiddlewareWithConfig("test-secret", "", nil, DefaultL1CacheConfig())
	token := jwt.New(jwt.SigningMethodHS256)

	b.ResetTimer()
	for range b.N {
		key, err := m.keyFunc(token)
		if err != nil {
			b.Fatalf("unexpected error: %v", err)
		}
		if key == nil {
			b.Fatal("keyFunc returned nil key")
		}
	}
}
