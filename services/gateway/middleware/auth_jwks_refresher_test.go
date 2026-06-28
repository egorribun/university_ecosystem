package middleware

import (
	"context"
	"crypto/rand"
	"crypto/rsa"
	"encoding/base64"
	"encoding/json"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"sync/atomic"
	"testing"
	"time"

	"github.com/prometheus/client_golang/prometheus/testutil"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestJWKSRefresher_FailuresAndRetries(t *testing.T) {
	privateKey1, err := rsa.GenerateKey(rand.Reader, 2048)
	require.NoError(t, err)

	nB64_1 := base64.RawURLEncoding.EncodeToString(privateKey1.N.Bytes())
	eB64_1 := base64.RawURLEncoding.EncodeToString([]byte{1, 0, 1})

	jwks1 := struct {
		Keys []map[string]string `json:"keys"`
	}{
		Keys: []map[string]string{
			{
				"kty": "RSA",
				"n":   nB64_1,
				"e":   eB64_1,
			},
		},
	}

	jwksBytes1, err := json.Marshal(jwks1)
	require.NoError(t, err)

	var requestCount int32

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		count := atomic.AddInt32(&requestCount, 1)
		w.Header().Set("Content-Type", "application/json")
		if count == 1 {
			// First request fails with 500
			w.WriteHeader(http.StatusInternalServerError)
			_, err := w.Write([]byte("internal error"))
			require.NoError(t, err)
		} else {
			// Subsequent requests succeed
			w.WriteHeader(http.StatusOK)
			_, err := w.Write(jwksBytes1)
			require.NoError(t, err)
		}
	}))
	defer server.Close()

	m := NewJWTMiddleware("secret", nil)
	assert.Nil(t, m.rsaPublicKey.Load())

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	refCountBefore := testutil.ToFloat64(jwksRefreshes)
	errCountBefore := testutil.ToFloat64(jwksRefreshErrors)

	// Start refresher with very short interval (20ms) so it retries fast.
	m.StartJWKSRefresher(ctx, server.URL, 20*time.Millisecond, slog.Default())

	// Wait for the background worker to fail the first time and succeed on the second/third attempt
	require.Eventually(t, func() bool {
		return m.rsaPublicKey.Load() != nil
	}, 1*time.Second, 10*time.Millisecond)

	assert.NotNil(t, m.rsaPublicKey.Load())
	assert.Equal(t, privateKey1.N, m.rsaPublicKey.Load().N)

	// Verify metrics
	assert.Greater(t, testutil.ToFloat64(jwksRefreshes)-refCountBefore, 1.0)
	assert.GreaterOrEqual(t, testutil.ToFloat64(jwksRefreshErrors)-errCountBefore, 1.0)
}

func TestJWKSRefresher_KeyRotation(t *testing.T) {
	privateKey1, err := rsa.GenerateKey(rand.Reader, 2048)
	require.NoError(t, err)
	privateKey2, err := rsa.GenerateKey(rand.Reader, 2048)
	require.NoError(t, err)

	nB64_1 := base64.RawURLEncoding.EncodeToString(privateKey1.N.Bytes())
	nB64_2 := base64.RawURLEncoding.EncodeToString(privateKey2.N.Bytes())
	eB64 := base64.RawURLEncoding.EncodeToString([]byte{1, 0, 1})

	makeJWKS := func(t *testing.T, n string) []byte {
		t.Helper()

		jwks := struct {
			Keys []map[string]string `json:"keys"`
		}{
			Keys: []map[string]string{
				{
					"kty": "RSA",
					"n":   n,
					"e":   eB64,
				},
			},
		}
		b, err := json.Marshal(jwks)
		require.NoError(t, err)
		return b
	}

	var useKey2 int32

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		if atomic.LoadInt32(&useKey2) == 1 {
			_, err := w.Write(makeJWKS(t, nB64_2))
			require.NoError(t, err)
		} else {
			_, err := w.Write(makeJWKS(t, nB64_1))
			require.NoError(t, err)
		}
	}))
	defer server.Close()

	m := NewJWTMiddleware("secret", nil)
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	m.StartJWKSRefresher(ctx, server.URL, 20*time.Millisecond, slog.Default())

	// Wait for key 1 to load
	require.Eventually(t, func() bool {
		k := m.rsaPublicKey.Load()
		return k != nil && k.N.Cmp(privateKey1.N) == 0
	}, 1*time.Second, 10*time.Millisecond)

	// Swap to key 2
	atomic.StoreInt32(&useKey2, 1)

	// Wait for key 2 to rotate
	require.Eventually(t, func() bool {
		k := m.rsaPublicKey.Load()
		return k != nil && k.N.Cmp(privateKey2.N) == 0
	}, 1*time.Second, 10*time.Millisecond)

	assert.Equal(t, privateKey2.N, m.rsaPublicKey.Load().N)
}
