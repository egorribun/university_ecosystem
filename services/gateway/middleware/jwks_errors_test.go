package middleware

// Coverage tests (testing session 9) for the JWKS parsing error branches.
// The happy path is already exercised by TestJWKSRefresher in auth_test.go;
// this file drives the failure branches of fetchJWKSPublicKey,
// jwkToRSAPublicKey and parseRSAPublicKeyFromPEM.

import (
	"context"
	"crypto/ecdsa"
	"crypto/elliptic"
	"crypto/rand"
	"crypto/rsa"
	"crypto/x509"
	"encoding/base64"
	"encoding/json"
	"encoding/pem"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func rsaJWKSBody(t *testing.T, pub *rsa.PublicKey) []byte {
	t.Helper()
	body := struct {
		Keys []map[string]string `json:"keys"`
	}{Keys: []map[string]string{{
		"kty": "RSA",
		"n":   base64.RawURLEncoding.EncodeToString(pub.N.Bytes()),
		"e":   base64.RawURLEncoding.EncodeToString([]byte{1, 0, 1}),
	}}}
	b, err := json.Marshal(body)
	require.NoError(t, err)
	return b
}

func jwksServer(t *testing.T, status int, body []byte) *httptest.Server {
	t.Helper()
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(status)
		_, _ = w.Write(body) //nolint:errcheck // test handler write
	}))
	t.Cleanup(srv.Close)
	return srv
}

// ---------------------------------------------------------------------------
// fetchJWKSPublicKey
// ---------------------------------------------------------------------------

func TestFetchJWKSPublicKey_Success(t *testing.T) {
	key, err := rsa.GenerateKey(rand.Reader, 2048)
	require.NoError(t, err)
	srv := jwksServer(t, http.StatusOK, rsaJWKSBody(t, &key.PublicKey))

	pub, err := fetchJWKSPublicKey(context.Background(), srv.Client(), srv.URL)
	require.NoError(t, err)
	assert.Equal(t, key.N, pub.N)
}

func TestFetchJWKSPublicKey_Non200(t *testing.T) {
	srv := jwksServer(t, http.StatusInternalServerError, []byte("boom"))
	_, err := fetchJWKSPublicKey(context.Background(), srv.Client(), srv.URL)
	require.Error(t, err)
	assert.Contains(t, err.Error(), "unexpected status")
}

func TestFetchJWKSPublicKey_PEMFallback(t *testing.T) {
	key, err := rsa.GenerateKey(rand.Reader, 2048)
	require.NoError(t, err)
	der, err := x509.MarshalPKIXPublicKey(&key.PublicKey)
	require.NoError(t, err)
	pemBytes := pem.EncodeToMemory(&pem.Block{Type: "PUBLIC KEY", Bytes: der})

	// Body is not JSON → fetchJWKSPublicKey falls back to PEM parsing.
	srv := jwksServer(t, http.StatusOK, pemBytes)
	pub, err := fetchJWKSPublicKey(context.Background(), srv.Client(), srv.URL)
	require.NoError(t, err)
	assert.Equal(t, key.N, pub.N)
}

func TestFetchJWKSPublicKey_NoRSAKey(t *testing.T) {
	// Valid JSON, but the only key is EC → "no RSA key found".
	body := []byte(`{"keys":[{"kty":"EC","crv":"P-256","x":"abc","y":"def"}]}`)
	srv := jwksServer(t, http.StatusOK, body)
	_, err := fetchJWKSPublicKey(context.Background(), srv.Client(), srv.URL)
	require.Error(t, err)
	assert.Contains(t, err.Error(), "no RSA key found")
}

func TestFetchJWKSPublicKey_RequestError(t *testing.T) {
	// A cancelled context makes client.Do fail before any response.
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	srv := jwksServer(t, http.StatusOK, []byte("{}"))
	_, err := fetchJWKSPublicKey(ctx, srv.Client(), srv.URL)
	require.Error(t, err)
	assert.Contains(t, err.Error(), "jwks: fetch")
}

// ---------------------------------------------------------------------------
// jwkToRSAPublicKey
// ---------------------------------------------------------------------------

func TestJWKToRSAPublicKey_BadBase64(t *testing.T) {
	t.Run("bad n", func(t *testing.T) {
		_, err := jwkToRSAPublicKey("!!!not base64!!!", base64.RawURLEncoding.EncodeToString([]byte{1, 0, 1}))
		require.Error(t, err)
		assert.Contains(t, err.Error(), "decode n")
	})
	t.Run("bad e", func(t *testing.T) {
		_, err := jwkToRSAPublicKey(base64.RawURLEncoding.EncodeToString([]byte{0x01, 0x02}), "###")
		require.Error(t, err)
		assert.Contains(t, err.Error(), "decode e")
	})
	t.Run("valid", func(t *testing.T) {
		pub, err := jwkToRSAPublicKey(
			base64.RawURLEncoding.EncodeToString([]byte{0x01, 0x00, 0x01}),
			base64.RawURLEncoding.EncodeToString([]byte{0x01, 0x00, 0x01}),
		)
		require.NoError(t, err)
		assert.Equal(t, 65537, pub.E)
	})
}

// ---------------------------------------------------------------------------
// parseRSAPublicKeyFromPEM
// ---------------------------------------------------------------------------

func TestParseRSAPublicKeyFromPEM_Errors(t *testing.T) {
	t.Run("no PEM block", func(t *testing.T) {
		_, err := parseRSAPublicKeyFromPEM([]byte("definitely not pem"))
		require.Error(t, err)
		assert.Contains(t, err.Error(), "no PEM block")
	})

	t.Run("garbage DER", func(t *testing.T) {
		garbage := pem.EncodeToMemory(&pem.Block{Type: "PUBLIC KEY", Bytes: []byte("junk-der")})
		_, err := parseRSAPublicKeyFromPEM(garbage)
		require.Error(t, err)
		assert.Contains(t, err.Error(), "parse public key")
	})

	t.Run("non-RSA key", func(t *testing.T) {
		ec, err := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
		require.NoError(t, err)
		der, err := x509.MarshalPKIXPublicKey(&ec.PublicKey)
		require.NoError(t, err)
		ecPEM := pem.EncodeToMemory(&pem.Block{Type: "PUBLIC KEY", Bytes: der})
		_, err = parseRSAPublicKeyFromPEM(ecPEM)
		require.Error(t, err)
		assert.Contains(t, err.Error(), "not RSA")
	})

	t.Run("valid RSA", func(t *testing.T) {
		key, err := rsa.GenerateKey(rand.Reader, 2048)
		require.NoError(t, err)
		der, err := x509.MarshalPKIXPublicKey(&key.PublicKey)
		require.NoError(t, err)
		pemBytes := pem.EncodeToMemory(&pem.Block{Type: "PUBLIC KEY", Bytes: der})
		pub, err := parseRSAPublicKeyFromPEM(pemBytes)
		require.NoError(t, err)
		assert.Equal(t, key.N, pub.N)
	})
}
