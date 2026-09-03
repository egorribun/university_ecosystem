package middleware

import (
	"context"
	"crypto/rand"
	"crypto/rsa"
	"encoding/base64"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/golang-jwt/jwt/v5"
	"github.com/stretchr/testify/require"
)

func TestStoreRSAKeysEmptySnapshotDoesNotConfigureMiddleware(t *testing.T) {
	middleware := &JWTMiddleware{}
	middleware.storeRSAKeys(rsaKeySet{})

	require.Nil(t, middleware.rsaKeys.Load())
	require.Nil(t, middleware.rsaPublicKey.Load())
}

func TestRSAKeySetsEqualRejectsDifferentKeyCounts(t *testing.T) {
	first, err := rsa.GenerateKey(rand.Reader, 2048)
	require.NoError(t, err)
	second, err := rsa.GenerateKey(rand.Reader, 2048)
	require.NoError(t, err)

	require.False(t, rsaKeySetsEqual(
		rsaKeySet{"first": &first.PublicKey},
		rsaKeySet{"first": &first.PublicKey, "second": &second.PublicKey},
	))
}

func TestFetchJWKSKeySetRejectsDuplicateRSAKeyIDs(t *testing.T) {
	key, err := rsa.GenerateKey(rand.Reader, 2048)
	require.NoError(t, err)
	encode := func(value []byte) string {
		return base64.RawURLEncoding.EncodeToString(value)
	}
	body, err := json.Marshal(map[string]any{
		"keys": []map[string]string{
			{"kty": "RSA", "kid": "duplicate", "n": encode(key.N.Bytes()), "e": encode([]byte{1, 0, 1})},
			{"kty": "RSA", "kid": "duplicate", "n": encode(key.N.Bytes()), "e": encode([]byte{1, 0, 1})},
		},
	})
	require.NoError(t, err)
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write(body)
	}))
	defer server.Close()

	_, err = fetchJWKSKeySet(context.Background(), server.Client(), server.URL)
	require.EqualError(t, err, `jwks: duplicate RSA key id "duplicate"`)
}

func TestSelectJWKSRepresentativeCoversLegacyAndEmptySets(t *testing.T) {
	key, err := rsa.GenerateKey(rand.Reader, 2048)
	require.NoError(t, err)

	legacy, err := selectJWKSRepresentative(rsaKeySet{"": &key.PublicKey})
	require.NoError(t, err)
	require.Equal(t, key.N, legacy.N)

	_, err = selectJWKSRepresentative(rsaKeySet{})
	require.EqualError(t, err, "jwks: no RSA key found in JWKS response")
}

func TestFetchJWKSPublicKeySelectsStableRepresentativeForMultipleKeys(t *testing.T) {
	first, err := rsa.GenerateKey(rand.Reader, 2048)
	require.NoError(t, err)
	second, err := rsa.GenerateKey(rand.Reader, 2048)
	require.NoError(t, err)
	encode := func(value []byte) string {
		return base64.RawURLEncoding.EncodeToString(value)
	}
	body, err := json.Marshal(map[string]any{
		"keys": []map[string]string{
			{"kty": "RSA", "kid": "z-last", "n": encode(second.N.Bytes()), "e": encode([]byte{1, 0, 1})},
			{"kty": "RSA", "kid": "a-first", "n": encode(first.N.Bytes()), "e": encode([]byte{1, 0, 1})},
		},
	})
	require.NoError(t, err)
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write(body)
	}))
	defer server.Close()

	publicKey, err := fetchJWKSPublicKey(context.Background(), server.Client(), server.URL)
	require.NoError(t, err)
	require.Equal(t, first.N, publicKey.N)
}

func TestJWTMiddlewareKeyFuncFallsBackToSingleJWKSKeyWithoutKid(t *testing.T) {
	key, err := rsa.GenerateKey(rand.Reader, 2048)
	require.NoError(t, err)
	middleware := &JWTMiddleware{}
	middleware.storeRSAKeys(rsaKeySet{"only": &key.PublicKey})

	token := jwt.NewWithClaims(jwt.SigningMethodRS256, &Claims{})
	verificationKey, err := middleware.keyFunc(token)
	require.NoError(t, err)
	require.Equal(t, key.N, verificationKey.(*rsa.PublicKey).N)
}
