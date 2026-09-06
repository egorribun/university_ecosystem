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

func TestFetchJWKSKeySetRetainsBothRotationKeys(t *testing.T) {
	oldKey, err := rsa.GenerateKey(rand.Reader, 2048)
	require.NoError(t, err)
	newKey, err := rsa.GenerateKey(rand.Reader, 2048)
	require.NoError(t, err)
	encode := func(value []byte) string {
		return base64.RawURLEncoding.EncodeToString(value)
	}
	body, err := json.Marshal(map[string]any{
		"keys": []map[string]string{
			{"kty": "RSA", "kid": "old", "n": encode(oldKey.N.Bytes()), "e": encode([]byte{1, 0, 1})},
			{"kty": "RSA", "kid": "new", "n": encode(newKey.N.Bytes()), "e": encode([]byte{1, 0, 1})},
		},
	})
	require.NoError(t, err)
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write(body)
	}))
	defer server.Close()

	keys, err := fetchJWKSKeySet(context.Background(), server.Client(), server.URL)
	require.NoError(t, err)
	require.Len(t, keys, 2)
	oldPublic, oldOK := keys["old"]
	require.True(t, oldOK)
	if oldPublic == nil {
		t.Fatal("old rotation key must not be nil")
	}
	newPublic, newOK := keys["new"]
	require.True(t, newOK)
	if newPublic == nil {
		t.Fatal("new rotation key must not be nil")
	}
	require.Equal(t, oldKey.N, oldPublic.N)
	require.Equal(t, newKey.N, newPublic.N)
}

func TestJWTMiddlewareKeyFuncSelectsJWKSKeyByKid(t *testing.T) {
	oldKey, err := rsa.GenerateKey(rand.Reader, 2048)
	require.NoError(t, err)
	newKey, err := rsa.GenerateKey(rand.Reader, 2048)
	require.NoError(t, err)
	middleware := &JWTMiddleware{}
	middleware.storeRSAKeys(rsaKeySet{
		"old": &oldKey.PublicKey,
		"new": &newKey.PublicKey,
	})

	token := jwt.NewWithClaims(jwt.SigningMethodRS256, &Claims{})
	token.Header["kid"] = "old"
	key, err := middleware.keyFunc(token)
	require.NoError(t, err)
	require.Equal(t, oldKey.N, key.(*rsa.PublicKey).N)

	token.Header["kid"] = "new"
	key, err = middleware.keyFunc(token)
	require.NoError(t, err)
	require.Equal(t, newKey.N, key.(*rsa.PublicKey).N)

	token.Header["kid"] = "unknown"
	_, err = middleware.keyFunc(token)
	require.ErrorContains(t, err, "unknown JWKS key id")

	delete(token.Header, "kid")
	_, err = middleware.keyFunc(token)
	require.ErrorContains(t, err, "missing kid")
}
