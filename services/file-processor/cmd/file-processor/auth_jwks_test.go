package main

import (
	"context"
	"crypto/rand"
	"crypto/rsa"
	"encoding/base64"
	"encoding/json"
	"errors"
	"io"
	"log/slog"
	"math/big"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	"github.com/golang-jwt/jwt/v5"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"github.com/university-ecosystem/file-processor/internal/config"
)

func encodeJWKInteger(value *big.Int) string {
	return base64.RawURLEncoding.EncodeToString(value.Bytes())
}

func rsaJWK(kid string, key *rsa.PublicKey) map[string]string {
	return map[string]string{
		"kty": "RSA",
		"use": "sig",
		"kid": kid,
		"alg": "RS256",
		"n":   encodeJWKInteger(key.N),
		"e":   encodeJWKInteger(big.NewInt(int64(key.E))),
	}
}

func marshalJWKS(t *testing.T, keys ...map[string]string) []byte {
	t.Helper()
	body, err := json.Marshal(map[string]any{"keys": keys})
	require.NoError(t, err)
	return body
}

func TestParseJWKSKeySetAcceptsCompleteRSASet(t *testing.T) {
	oldKey := generateRSAKey(t)
	newKey := generateRSAKey(t)
	keys, err := parseJWKSKeySet(marshalJWKS(t, rsaJWK("old", &oldKey.PublicKey), rsaJWK("new", &newKey.PublicKey)))
	require.NoError(t, err)
	require.Len(t, keys, 2)
	assert.True(t, keys["old"].Equal(&oldKey.PublicKey))
	assert.True(t, keys["new"].Equal(&newKey.PublicKey))
}

func TestParseJWKSKeySetRejectsMalformedOrUnsafeDocuments(t *testing.T) {
	key := generateRSAKey(t)
	valid := rsaJWK("valid", &key.PublicKey)
	cases := []struct {
		name string
		body []byte
		want string
	}{
		{name: "empty body", body: nil, want: "empty"},
		{name: "invalid json", body: []byte("{"), want: "valid JSON"},
		{name: "missing keys", body: []byte(`{}`), want: "no keys"},
		{name: "non rsa", body: mustJSON(t, map[string]any{"keys": []map[string]string{{"kty": "oct", "kid": "bad"}}}), want: "unsupported key type"},
		{name: "wrong use", body: mustJSON(t, map[string]any{"keys": []map[string]string{{"kty": "RSA", "kid": "bad", "use": "enc", "n": valid["n"], "e": valid["e"]}}}), want: "unsupported use"},
		{name: "wrong algorithm", body: mustJSON(t, map[string]any{"keys": []map[string]string{{"kty": "RSA", "kid": "bad", "alg": "RS384", "n": valid["n"], "e": valid["e"]}}}), want: "unsupported algorithm"},
		{name: "missing kid", body: mustJSON(t, map[string]any{"keys": []map[string]string{{"kty": "RSA", "n": valid["n"], "e": valid["e"]}}}), want: "invalid kid"},
		{name: "missing modulus", body: mustJSON(t, map[string]any{"keys": []map[string]string{{"kty": "RSA", "kid": "bad", "n": "", "e": valid["e"]}}}), want: "missing modulus"},
		{name: "invalid modulus", body: mustJSON(t, map[string]any{"keys": []map[string]string{{"kty": "RSA", "kid": "bad", "n": "not-base64!", "e": valid["e"]}}}), want: "modulus"},
		{name: "invalid exponent encoding", body: mustJSON(t, map[string]any{"keys": []map[string]string{{"kty": "RSA", "kid": "bad", "n": valid["n"], "e": "not-base64!"}}}), want: "exponent"},
		{name: "wrong exponent", body: mustJSON(t, map[string]any{"keys": []map[string]string{{"kty": "RSA", "kid": "bad", "n": valid["n"], "e": encodeJWKInteger(big.NewInt(3))}}}), want: "65537"},
		{name: "small modulus", body: smallModulusJWKS(t), want: "at least 2048 bits"},
		{name: "duplicate kid", body: marshalJWKS(t, valid, valid), want: "duplicate kid"},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			_, err := parseJWKSKeySet(tc.body)
			require.Error(t, err)
			assert.Contains(t, err.Error(), tc.want)
		})
	}
}

func mustJSON(t *testing.T, value any) []byte {
	t.Helper()
	body, err := json.Marshal(value)
	require.NoError(t, err)
	return body
}

func smallModulusJWKS(t *testing.T) []byte {
	t.Helper()
	key, err := rsa.GenerateKey(rand.Reader, 1024)
	require.NoError(t, err)
	return marshalJWKS(t, rsaJWK("small", &key.PublicKey))
}

type roundTripFunc func(*http.Request) (*http.Response, error)

func (f roundTripFunc) RoundTrip(req *http.Request) (*http.Response, error) {
	return f(req)
}

func TestFetchJWKSKeySetBoundsHTTPAndContext(t *testing.T) {
	key := generateRSAKey(t)
	validBody := marshalJWKS(t, rsaJWK("valid", &key.PublicKey))
	server := httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		writer.Header().Set("Content-Type", "application/json")
		_, _ = writer.Write(validBody)
	}))
	t.Cleanup(server.Close)

	keys, err := fetchJWKSKeySet(context.Background(), http.DefaultClient, server.URL)
	require.NoError(t, err)
	assert.Len(t, keys, 1)

	_, err = fetchJWKSKeySet(context.Background(), http.DefaultClient, server.URL+"?token=secret")
	assert.ErrorContains(t, err, "without credentials, query, or fragment")
	_, err = fetchJWKSKeySet(context.Background(), http.DefaultClient, "ftp://backend/jwks")
	assert.ErrorContains(t, err, "absolute HTTP(S)")
	_, err = fetchJWKSKeySet(context.Background(), nil, "http://")
	assert.Error(t, err)

	statusServer := httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, _ *http.Request) {
		writer.WriteHeader(http.StatusBadGateway)
	}))
	t.Cleanup(statusServer.Close)
	_, err = fetchJWKSKeySet(context.Background(), http.DefaultClient, statusServer.URL)
	assert.ErrorContains(t, err, "HTTP status 502")
	var redirectedRequests atomic.Int32
	targetServer := httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, _ *http.Request) {
		redirectedRequests.Add(1)
		_, _ = writer.Write(validBody)
	}))
	t.Cleanup(targetServer.Close)
	redirectServer := httptest.NewServer(http.RedirectHandler(targetServer.URL, http.StatusFound))
	t.Cleanup(redirectServer.Close)
	_, err = fetchJWKSKeySet(context.Background(), http.DefaultClient, redirectServer.URL)
	assert.ErrorContains(t, err, "HTTP status 302")
	assert.Zero(t, redirectedRequests.Load(), "JWKS client must not follow redirects")

	oversizedServer := httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, _ *http.Request) {
		_, _ = writer.Write([]byte(strings.Repeat("x", maxJWKSBodyBytes+1)))
	}))
	t.Cleanup(oversizedServer.Close)
	_, err = fetchJWKSKeySet(context.Background(), http.DefaultClient, oversizedServer.URL)
	assert.ErrorContains(t, err, "exceeds")

	nilResponseClient := &http.Client{Transport: roundTripFunc(func(*http.Request) (*http.Response, error) { return nil, nil })}
	_, err = fetchJWKSKeySet(context.Background(), nilResponseClient, "http://backend/jwks")
	assert.Error(t, err)
	nilBodyClient := &http.Client{Transport: roundTripFunc(func(*http.Request) (*http.Response, error) {
		return &http.Response{StatusCode: http.StatusOK, Body: nil}, nil
	})}
	_, err = fetchJWKSKeySet(context.Background(), nilBodyClient, "http://backend/jwks")
	assert.ErrorContains(t, err, "empty")
	errorClient := &http.Client{Transport: roundTripFunc(func(*http.Request) (*http.Response, error) {
		return nil, errors.New("transport failed")
	})}
	_, err = fetchJWKSKeySet(context.Background(), errorClient, "http://backend/jwks")
	assert.ErrorContains(t, err, "JWKS fetch failed")

	readErrorClient := &http.Client{Transport: roundTripFunc(func(*http.Request) (*http.Response, error) {
		return &http.Response{StatusCode: http.StatusOK, Body: errorReadCloser{}}, nil
	})}
	_, err = fetchJWKSKeySet(context.Background(), readErrorClient, "http://backend/jwks")
	assert.ErrorContains(t, err, "response read failed")

	canceled, cancel := context.WithCancel(context.Background())
	cancel()
	_, err = fetchJWKSKeySet(canceled, http.DefaultClient, server.URL)
	assert.Error(t, err)
}

type errorReadCloser struct{}

func (errorReadCloser) Read([]byte) (int, error) { return 0, errors.New("synthetic read failure") }
func (errorReadCloser) Close() error             { return nil }

func TestFetchJWKSKeySetRejectsRedirectsWithoutFollowingTarget(t *testing.T) {
	var targetRequests atomic.Int32
	target := httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, _ *http.Request) {
		targetRequests.Add(1)
		writer.WriteHeader(http.StatusOK)
	}))
	t.Cleanup(target.Close)
	redirect := httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, _ *http.Request) {
		writer.Header().Set("Location", target.URL)
		writer.WriteHeader(http.StatusFound)
	}))
	t.Cleanup(redirect.Close)

	_, err := fetchJWKSKeySet(context.Background(), http.DefaultClient, redirect.URL)
	assert.ErrorContains(t, err, "HTTP status 302")
	assert.Zero(t, targetRequests.Load())
}

func TestJWKSKeyFuncResolvesExactKidAndStaticFallback(t *testing.T) {
	oldKey := generateRSAKey(t)
	newKey := generateRSAKey(t)
	store := newRSAKeySetStore()
	store.Store(rsaKeySet{"old": &oldKey.PublicKey, "new": &newKey.PublicKey})
	resolver := jwtKeyFuncWithKeySet("hmac-secret", nil, store, true, "new", true)

	oldToken := jwt.New(jwt.SigningMethodRS256)
	oldToken.Header["kid"] = "old"
	resolved, err := resolver(oldToken)
	require.NoError(t, err)
	assert.True(t, resolved.(*rsa.PublicKey).Equal(&oldKey.PublicKey))

	newToken := jwt.New(jwt.SigningMethodRS256)
	newToken.Header["kid"] = "new"
	resolved, err = resolver(newToken)
	require.NoError(t, err)
	assert.True(t, resolved.(*rsa.PublicKey).Equal(&newKey.PublicKey))

	for _, token := range []*jwt.Token{
		jwt.New(jwt.SigningMethodRS256),
	} {
		_, err = resolver(token)
		assert.ErrorContains(t, err, "missing kid")
	}
	unknown := jwt.New(jwt.SigningMethodRS256)
	unknown.Header["kid"] = "removed"
	_, err = resolver(unknown)
	assert.ErrorContains(t, err, "unknown kid")
	nonString := jwt.New(jwt.SigningMethodRS256)
	nonString.Header["kid"] = 42
	_, err = resolver(nonString)
	assert.ErrorContains(t, err, "invalid kid type")

	staticResolver := jwtKeyFuncWithKeySet("hmac-secret", &oldKey.PublicKey, newRSAKeySetStore(), true, "active", true)
	static := jwt.New(jwt.SigningMethodRS256)
	static.Header["kid"] = "active"
	resolved, err = staticResolver(static)
	require.NoError(t, err)
	assert.True(t, resolved.(*rsa.PublicKey).Equal(&oldKey.PublicKey))
	static.Header["kid"] = "wrong"
	_, err = staticResolver(static)
	assert.ErrorContains(t, err, "unknown kid")
	delete(static.Header, "kid")
	_, err = staticResolver(static)
	assert.ErrorContains(t, err, "missing kid")

	legacyResolver := jwtKeyFuncWithKeySet("hmac-secret", &oldKey.PublicKey, newRSAKeySetStore(), false, "", false)
	legacy := jwt.New(jwt.SigningMethodRS256)
	resolved, err = legacyResolver(legacy)
	require.NoError(t, err)
	assert.True(t, resolved.(*rsa.PublicKey).Equal(&oldKey.PublicKey))

	hmac := jwt.New(jwt.SigningMethodHS256)
	_, err = resolver(hmac)
	assert.ErrorContains(t, err, "HS256 token rejected")
	_, err = jwtKeyFuncWithKeySet("hmac-secret", nil, nil, false, "", false)(hmac)
	require.NoError(t, err)
	_, err = jwtKeyFuncWithKeySet("", nil, nil, false, "", false)(hmac)
	assert.ErrorContains(t, err, "no JWT secret")
	_, err = jwtKeyFuncWithKeySet("hmac-secret", nil, nil, false, "", true)(hmac)
	assert.ErrorContains(t, err, "HS256 token rejected")

	for _, method := range []jwt.SigningMethod{jwt.SigningMethodRS384, jwt.SigningMethodES256, jwt.SigningMethodNone} {
		token := jwt.New(method)
		_, err = resolver(token)
		assert.Error(t, err)
	}
	_, err = resolver(nil)
	assert.ErrorContains(t, err, "nil")
}

func TestJWKSStoreIsAtomicAndDoesNotPublishEmptySets(t *testing.T) {
	key := generateRSAKey(t)
	store := newRSAKeySetStore()
	store.Store(nil)
	assert.Equal(t, 0, store.Len())
	store.Store(rsaKeySet{"one": &key.PublicKey})
	assert.Equal(t, 1, store.Len())
	store.Store(rsaKeySet{"two": &key.PublicKey, "nil": nil})
	assert.Equal(t, 1, store.Len())
	assert.Nil(t, (*rsaKeySetStore)(nil).Load())
	assert.Equal(t, 0, (*rsaKeySetStore)(nil).Len())
}

func TestJWKSStoreExpiresStaleSnapshots(t *testing.T) {
	key := generateRSAKey(t)
	store := newRSAKeySetStore(2 * time.Second)
	store.Store(rsaKeySet{"primary": &key.PublicKey})
	now := time.Now().UTC()
	store.snapshotAt.Store(now.UnixNano())

	assert.Len(t, store.LoadAt(now.Add(time.Second)), 1)
	assert.Empty(t, store.LoadAt(now.Add(2*time.Second)))
	assert.Empty(t, store.LoadAt(now.Add(3*time.Second)))
}

func TestJWKSStoreRejectsInvalidKeysAndEmptyStaleSnapshot(t *testing.T) {
	store := newRSAKeySetStore(time.Second)
	now := time.Now().UTC()
	assert.Empty(t, store.LoadAt(now))

	valid := generateRSAKey(t)
	weak := &rsa.PublicKey{N: valid.N, E: 3}
	store.Store(rsaKeySet{"nil": nil, "weak": weak})
	assert.Empty(t, store.LoadAt(now))
}

func TestJWKSResolverFailsClosedWhenSnapshotIsStale(t *testing.T) {
	key := generateRSAKey(t)
	store := newRSAKeySetStore(time.Second)
	store.Store(rsaKeySet{"primary": &key.PublicKey})
	store.snapshotAt.Store(time.Now().UTC().Add(-2 * time.Second).UnixNano())

	token := jwt.New(jwt.SigningMethodRS256)
	_, err := resolveRSAJWTKey(token, &key.PublicKey, store, true, "primary")
	require.Error(t, err)
	assert.Contains(t, err.Error(), "stale")
}

func TestInitializeJWKSKeySetUsesLKGAndRefreshes(t *testing.T) {
	oldKey := generateRSAKey(t)
	newKey := generateRSAKey(t)
	var requests atomic.Int32
	server := httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, _ *http.Request) {
		if requests.Add(1) == 1 {
			_, _ = writer.Write(marshalJWKS(t, rsaJWK("old", &oldKey.PublicKey)))
			return
		}
		_, _ = writer.Write(marshalJWKS(t, rsaJWK("new", &newKey.PublicKey)))
	}))
	t.Cleanup(server.Close)
	ctx, cancel := context.WithCancel(context.Background())
	t.Cleanup(cancel)
	store, err := initializeJWKSKeySet(ctx, &config.Config{JWKSURL: server.URL, JWKSRefreshInterval: 1, JWTActiveKID: "fallback"}, nil, discardLogger())
	require.NoError(t, err)
	require.NotNil(t, store)
	require.NotNil(t, store.Load()["old"])
	assert.Eventually(t, func() bool { _, ok := store.Load()["new"]; return ok }, 3*time.Second, 25*time.Millisecond)
	cancel()

	badServer := httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, _ *http.Request) {
		_, _ = writer.Write([]byte("not-json"))
	}))
	t.Cleanup(badServer.Close)
	static, err := initializeJWKSKeySet(context.Background(), &config.Config{JWKSURL: badServer.URL, JWTActiveKID: "fallback"}, &oldKey.PublicKey, discardLogger())
	require.NoError(t, err)
	require.NotNil(t, static)
	assert.True(t, static.Load()["fallback"].Equal(&oldKey.PublicKey))

	_, err = initializeJWKSKeySet(context.Background(), &config.Config{JWKSURL: badServer.URL}, nil, discardLogger())
	assert.ErrorContains(t, err, "initial JWKS fetch failed")
	_, err = initializeJWKSKeySet(context.Background(), &config.Config{JWKSURL: "file:///tmp/jwks"}, &oldKey.PublicKey, discardLogger())
	assert.ErrorContains(t, err, "absolute HTTP(S)")
	_, err = initializeJWKSKeySet(context.Background(), nil, nil, discardLogger())
	assert.ErrorContains(t, err, "configuration is nil")
}

func TestJWKSRefreshRetainsLKGOnMalformedRefresh(t *testing.T) {
	key := generateRSAKey(t)
	store := newRSAKeySetStore()
	store.Store(rsaKeySet{"lkg": &key.PublicKey})
	server := httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, _ *http.Request) {
		_, _ = writer.Write([]byte("malformed"))
	}))
	t.Cleanup(server.Close)

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	err := refreshJWKSOnce(ctx, http.DefaultClient, server.URL, store)
	assert.Error(t, err)
	assert.True(t, store.Load()["lkg"].Equal(&key.PublicKey))

	startJWKSRefresher(ctx, server.URL, 1*time.Millisecond, store, slog.New(slog.NewTextHandler(io.Discard, nil)))
	time.Sleep(20 * time.Millisecond)
	assert.True(t, store.Load()["lkg"].Equal(&key.PublicKey))
	cancel()
}

func TestJWKSRefreshIntervalAndValidationHelpers(t *testing.T) {
	assert.Equal(t, defaultJWKSRefreshSeconds*time.Second, boundedJWKSRefreshInterval(0))
	assert.Equal(t, defaultJWKSRefreshSeconds*time.Second, boundedJWKSRefreshInterval(-time.Second))
	assert.Equal(t, maxJWKSRefreshInterval, boundedJWKSRefreshInterval(48*time.Hour))
	assert.Equal(t, 2*time.Second, boundedJWKSRefreshInterval(2*time.Second))
	// The credential-bearing URL is an intentionally inert parser fixture, not
	// a credential; the pragma documents the proven detect-secrets false positive.
	for _, endpoint := range []string{"", " backend", "http://", "https://user:secret@backend/jwks", // pragma: allowlist secret
		"http://backend/jwks#fragment", "http://backend/jwks?x=1", "http://backend/jwks\n"} {
		if endpoint == "" {
			assert.Error(t, validateJWKSURL(endpoint))
			continue
		}
		assert.Error(t, validateJWKSURL(endpoint))
	}
	assert.NoError(t, validateJWKSURL("http://backend:8000/.well-known/jwks.json"))
}
