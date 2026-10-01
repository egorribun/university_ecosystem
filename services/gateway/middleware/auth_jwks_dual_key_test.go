package middleware

import (
	"context"
	"crypto/rand"
	"crypto/rsa"
	"encoding/base64"
	"encoding/json"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"sync/atomic"
	"testing"
	"time"

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

func TestJWKSRotationWindowAcceptsBothKeysAndRetiresRemovedKey(t *testing.T) {
	oldKey, err := rsa.GenerateKey(rand.Reader, 2048)
	require.NoError(t, err)
	newKey, err := rsa.GenerateKey(rand.Reader, 2048)
	require.NoError(t, err)

	makeJWKS := func(keys map[string]*rsa.PublicKey) []byte {
		encode := func(value []byte) string {
			return base64.RawURLEncoding.EncodeToString(value)
		}
		entries := make([]map[string]string, 0, len(keys))
		for kid, key := range keys {
			entries = append(entries, map[string]string{
				"kty": "RSA",
				"kid": kid,
				"n":   encode(key.N.Bytes()),
				"e":   encode([]byte{1, 0, 1}),
			})
		}
		body, marshalErr := json.Marshal(map[string]any{"keys": entries})
		require.NoError(t, marshalErr)
		return body
	}

	var currentJWKS atomic.Value
	currentJWKS.Store(makeJWKS(map[string]*rsa.PublicKey{
		"old": &oldKey.PublicKey,
		"new": &newKey.PublicKey,
	}))
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write(currentJWKS.Load().([]byte))
	}))
	defer server.Close()

	middleware := NewJWTMiddlewareWithConfig("unused-hmac-key", "", nil, DefaultL1CacheConfig())
	ctx, cancel := context.WithCancel(context.Background())
	middleware.StartJWKSRefresher(ctx, server.URL, 10*time.Millisecond, slog.New(slog.NewTextHandler(io.Discard, nil)))
	t.Cleanup(func() {
		cancel()
		finished := make(chan struct{})
		go func() {
			jwksRefreshWG.Wait()
			close(finished)
		}()
		select {
		case <-finished:
		case <-time.After(time.Second):
			t.Error("JWKS refresher did not stop after context cancellation")
		}
	})

	waitForKids := func(want ...string) {
		expected := make(map[string]struct{}, len(want))
		for _, kid := range want {
			expected[kid] = struct{}{}
		}
		require.Eventually(t, func() bool {
			snapshot := middleware.rsaKeys.Load()
			if snapshot == nil || len(*snapshot) != len(expected) {
				return false
			}
			for kid := range expected {
				if _, ok := (*snapshot)[kid]; !ok {
					return false
				}
			}
			return true
		}, 2*time.Second, 5*time.Millisecond)
	}
	waitForKids("old", "new")

	sign := func(kid string, signingKey *rsa.PrivateKey) string {
		token := jwt.NewWithClaims(jwt.SigningMethodRS256, jwt.MapClaims{
			"sub": "synthetic-rotation-test-user",
			"exp": time.Now().Add(time.Minute).Unix(),
		})
		token.Header["kid"] = kid
		signed, signErr := token.SignedString(signingKey)
		require.NoError(t, signErr)
		return signed
	}
	oldToken := sign("old", oldKey)
	newToken := sign("new", newKey)
	wrongSignerToken := sign("new", oldKey)
	parse := func(tokenString string) error {
		parsed, parseErr := jwt.Parse(tokenString, middleware.keyFunc, jwt.WithValidMethods([]string{"RS256"}))
		if parseErr != nil {
			return parseErr
		}
		if !parsed.Valid {
			return jwt.ErrTokenSignatureInvalid
		}
		return nil
	}

	// ADR-013's overlap window accepts tokens signed by either published key,
	// while still verifying that a kid cannot authorize a signature from another key.
	require.NoError(t, parse(oldToken))
	require.NoError(t, parse(newToken))
	require.Error(t, parse(wrongSignerToken))

	currentJWKS.Store(makeJWKS(map[string]*rsa.PublicKey{"new": &newKey.PublicKey}))
	waitForKids("new")

	// Removing the retiring public key ends its acceptance window after refresh.
	require.Error(t, parse(oldToken))
	require.NoError(t, parse(newToken))
}
