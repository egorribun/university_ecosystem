package middleware

import (
	"context"
	"crypto/rand"
	"crypto/rsa"
	"crypto/x509"
	"encoding/base64"
	"encoding/json"
	"encoding/pem"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"github.com/golang-jwt/jwt/v5"
	"github.com/prometheus/client_golang/prometheus/testutil"
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

	middleware.storeRSAKeys(rsaKeySet{"current": &newKey.PublicKey})
	token.Header["kid"] = "unknown"
	_, err = middleware.keyFunc(token)
	require.ErrorContains(t, err, "unknown JWKS key id", "an unknown kid must remain rejected for a sole named key")
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

// TestJWKSFreshnessMaxAgeMatchesFileProcessor verifies that stale-key policy
// uses the same bounded refresh window, token lifetime, and skew as the
// file-processor verifier.
func TestJWKSFreshnessMaxAgeMatchesFileProcessor(t *testing.T) {
	tokenWindow := jwtMaxTokenAge + jwtMaxClockSkew
	require.Equal(t, defaultJWKSRefreshInterval+tokenWindow, jwksSnapshotMaxAge(0))
	require.Equal(t, minJWKSRefreshInterval+tokenWindow, jwksSnapshotMaxAge(minJWKSRefreshInterval-time.Nanosecond))
	require.Equal(t, 30*time.Minute+tokenWindow, jwksSnapshotMaxAge(30*time.Minute))
	require.Equal(t, maxJWKSRefreshInterval+tokenWindow, jwksSnapshotMaxAge(maxJWKSRefreshInterval+time.Hour))
}

func TestJWKSKeyFuncRejectsCurrentIssuedTokenAtSnapshotExpiry(t *testing.T) {
	privateKey, err := rsa.GenerateKey(rand.Reader, 2048)
	require.NoError(t, err)

	middleware := &JWTMiddleware{}
	middleware.jwksConfigured.Store(true)
	maxAge := 10 * time.Second
	middleware.jwksFreshnessLimit.Store(int64(maxAge))
	publishedAt := time.Now().UTC()
	middleware.storeRSAKeysAt(rsaKeySet{"current": &privateKey.PublicKey}, publishedAt)

	claims := jwt.MapClaims{
		"sub": "current-user",
		"iat": publishedAt.Unix(),
		"exp": publishedAt.Add(time.Hour).Unix(),
	}
	token := jwt.NewWithClaims(jwt.SigningMethodRS256, claims)
	token.Header["kid"] = "current"
	signed, err := token.SignedString(privateKey)
	require.NoError(t, err)

	parseAt := func(at time.Time) (*jwt.Token, error) {
		return jwt.ParseWithClaims(
			signed,
			jwt.MapClaims{},
			func(token *jwt.Token) (interface{}, error) {
				return middleware.keyFuncAt(token, at)
			},
			jwt.WithValidMethods([]string{"RS256"}),
			jwt.WithIssuedAt(),
			jwt.WithExpirationRequired(),
		)
	}

	justBeforeExpiry, err := parseAt(publishedAt.Add(maxAge - time.Nanosecond))
	require.NoError(t, err)
	require.True(t, justBeforeExpiry.Valid)

	_, err = parseAt(publishedAt.Add(maxAge))
	require.ErrorContains(t, err, "JWKS key snapshot is stale")
	_, err = parseAt(publishedAt.Add(maxAge + time.Nanosecond))
	require.ErrorContains(t, err, "JWKS key snapshot is stale")
}

func TestJWKSKeyFuncFailsClosedWithoutFreshSnapshot(t *testing.T) {
	middleware := &JWTMiddleware{}
	middleware.jwksConfigured.Store(true)
	middleware.jwksFreshnessLimit.Store(int64(time.Second))
	token := jwt.NewWithClaims(jwt.SigningMethodRS256, jwt.MapClaims{})
	_, err := middleware.keyFunc(token)
	require.ErrorContains(t, err, "JWKS snapshot is unavailable")

	privateKey, err := rsa.GenerateKey(rand.Reader, 2048)
	require.NoError(t, err)
	middleware.storeRSAKeysAt(rsaKeySet{"current": &privateKey.PublicKey}, time.Now().UTC())
	middleware.jwksFreshnessLimit.Store(0)
	_, err = middleware.keyFunc(token)
	require.ErrorContains(t, err, "JWKS key snapshot is stale")
}

func TestJWKSRefreshFailuresKeepStaleSnapshotAndSuccessfulEqualRefreshRenewsIt(t *testing.T) {
	privateKey, err := rsa.GenerateKey(rand.Reader, 2048)
	require.NoError(t, err)
	body := rsaJWKSBody(t, &privateKey.PublicKey)

	var unavailable atomic.Bool
	unavailable.Store(true)
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		if unavailable.Load() {
			http.Error(w, "JWKS unavailable", http.StatusServiceUnavailable)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write(body)
	}))
	defer server.Close()

	middleware := &JWTMiddleware{}
	middleware.jwksConfigured.Store(true)
	maxAge := 5 * time.Second
	middleware.jwksFreshnessLimit.Store(int64(maxAge))
	publishedAt := time.Now().UTC().Add(-time.Minute)
	middleware.storeRSAKeysAt(rsaKeySet{"": &privateKey.PublicKey}, publishedAt)
	oldSnapshot := middleware.jwksSnapshot.Load()

	for range 3 {
		rotated, refreshErr := middleware.refreshJWKSOnce(context.Background(), server.Client(), server.URL)
		require.Error(t, refreshErr)
		require.False(t, rotated)
		require.True(t, middleware.jwksSnapshot.Load() == oldSnapshot, "failed refresh must preserve the complete LKG snapshot")
		require.Equal(t, publishedAt, middleware.jwksSnapshot.Load().fetchedAt)
	}

	token := jwt.NewWithClaims(jwt.SigningMethodRS256, jwt.MapClaims{})
	_, err = middleware.keyFuncAt(token, publishedAt.Add(maxAge))
	require.ErrorContains(t, err, "JWKS key snapshot is stale")

	unavailable.Store(false)
	rotated, err := middleware.refreshJWKSOnce(context.Background(), server.Client(), server.URL)
	require.NoError(t, err)
	require.False(t, rotated, "an equal key set refreshes freshness without counting a rotation")
	newSnapshot := middleware.jwksSnapshot.Load()
	require.True(t, oldSnapshot != newSnapshot, "successful refresh must publish a new snapshot")
	require.True(t, rsaKeySetsEqual(oldSnapshot.keys, newSnapshot.keys))
	require.True(t, newSnapshot.fetchedAt.After(publishedAt))
	_, err = middleware.keyFuncAt(token, newSnapshot.fetchedAt)
	require.NoError(t, err, "a successful refresh restores acceptance for the published key")

	freshClaims := jwt.MapClaims{
		"sub": "current-user",
		"iat": time.Now().Unix(),
		"exp": time.Now().Add(time.Hour).Unix(),
	}
	freshToken := jwt.NewWithClaims(jwt.SigningMethodRS256, freshClaims)
	freshTokenString, err := freshToken.SignedString(privateKey)
	require.NoError(t, err)
	parsed, err := jwt.Parse(
		freshTokenString,
		middleware.keyFunc,
		jwt.WithValidMethods([]string{"RS256"}),
		jwt.WithIssuedAt(),
		jwt.WithExpirationRequired(),
	)
	require.NoError(t, err)
	require.True(t, parsed.Valid, "successful refresh must restore acceptance for a current-issued-at JWT")
}

func TestJWKSRefreshScheduleIntervalCapsMaximumAndPreservesShortIntervals(t *testing.T) {
	tests := []struct {
		name  string
		input time.Duration
		want  time.Duration
	}{
		{name: "zero uses default", input: 0, want: defaultJWKSRefreshInterval},
		{name: "negative uses default", input: -time.Second, want: defaultJWKSRefreshInterval},
		{name: "subsecond cadence is preserved", input: 250 * time.Millisecond, want: 250 * time.Millisecond},
		{name: "configured cadence is preserved", input: 5 * time.Minute, want: 5 * time.Minute},
		{name: "maximum is preserved", input: maxJWKSRefreshInterval, want: maxJWKSRefreshInterval},
		{name: "long cadence is capped", input: maxJWKSRefreshInterval + time.Hour, want: maxJWKSRefreshInterval},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			require.Equal(t, tt.want, scheduledJWKSRefreshInterval(tt.input))
		})
	}
}

func TestJWKSBootstrapPEMRemainsBoundedAfterInitialFetchFailure(t *testing.T) {
	privateKey, err := rsa.GenerateKey(rand.Reader, 2048)
	require.NoError(t, err)
	der, err := x509.MarshalPKIXPublicKey(&privateKey.PublicKey)
	require.NoError(t, err)
	publicKeyPEM := string(pem.EncodeToMemory(&pem.Block{Type: "PUBLIC KEY", Bytes: der}))

	rsaToken := jwt.NewWithClaims(jwt.SigningMethodRS256, jwt.MapClaims{})
	directPEM := NewJWTMiddlewareWithConfig("synthetic-test-secret", publicKeyPEM, nil, DefaultL1CacheConfig())
	directSnapshot := directPEM.jwksSnapshot.Load()
	require.NotNil(t, directSnapshot)
	farFuture := directSnapshot.fetchedAt.Add(2 * jwksSnapshotMaxAge(maxJWKSRefreshInterval))
	directKey, err := directPEM.keyFuncAt(rsaToken, farFuture)
	require.NoError(t, err, "PEM-only mode remains compatible without a JWKS freshness policy")
	require.Equal(t, privateKey.N, directKey.(*rsa.PublicKey).N)

	requestFinished := make(chan struct{})
	var requestOnce sync.Once
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		http.Error(w, "synthetic JWKS outage", http.StatusServiceUnavailable)
		requestOnce.Do(func() { close(requestFinished) })
	}))

	middleware := NewJWTMiddlewareWithConfig("synthetic-test-secret", publicKeyPEM, nil, DefaultL1CacheConfig())
	bootstrap := middleware.jwksSnapshot.Load()
	require.NotNil(t, bootstrap)
	ctx, cancel := context.WithCancel(context.Background())
	refreshErrorsBefore := testutil.ToFloat64(jwksRefreshErrors)
	middleware.StartJWKSRefresher(ctx, server.URL, maxJWKSRefreshInterval+time.Hour, slog.New(slog.NewTextHandler(io.Discard, nil)))
	workerFinished := make(chan struct{})
	go func() {
		jwksRefreshWG.Wait()
		close(workerFinished)
	}()
	t.Cleanup(func() {
		cancel()
		select {
		case <-workerFinished:
		case <-time.After(time.Second):
			t.Error("JWKS refresher did not stop after context cancellation")
		}
		server.Close()
	})

	select {
	case <-requestFinished:
	case <-time.After(time.Second):
		t.Fatal("initial JWKS fetch did not reach the failure endpoint")
	}
	require.Eventually(t, func() bool {
		return testutil.ToFloat64(jwksRefreshErrors) > refreshErrorsBefore
	}, time.Second, 5*time.Millisecond, "initial JWKS fetch must fail")

	require.True(t, middleware.jwksConfigured.Load())
	require.Equal(t, int64(jwksSnapshotMaxAge(maxJWKSRefreshInterval)), middleware.jwksFreshnessLimit.Load(), "long configured cadence must use the bounded freshness policy")
	require.Same(t, bootstrap, middleware.jwksSnapshot.Load(), "failed initial fetch must preserve the configured PEM bootstrap")
	freshUntil := bootstrap.fetchedAt.Add(time.Duration(middleware.jwksFreshnessLimit.Load()))
	_, err = middleware.keyFuncAt(rsaToken, freshUntil.Add(-time.Nanosecond))
	require.NoError(t, err, "a usable bootstrap key remains the bounded last-known-good key")
	_, err = middleware.keyFuncAt(rsaToken, freshUntil)
	require.ErrorContains(t, err, "JWKS key snapshot is stale", "bootstrap trust ends at the configured maximum age")

	currentClaims := jwt.MapClaims{
		"sub": "bootstrap-current-user",
		"iat": time.Now().Unix(),
		"exp": freshUntil.Add(time.Hour).Unix(),
	}
	parseAt := func(kid string, at time.Time) error {
		token := jwt.NewWithClaims(jwt.SigningMethodRS256, currentClaims)
		token.Header["kid"] = kid
		signed, signErr := token.SignedString(privateKey)
		require.NoError(t, signErr)
		_, parseErr := jwt.ParseWithClaims(
			signed,
			jwt.MapClaims{},
			func(token *jwt.Token) (interface{}, error) {
				return middleware.keyFuncAt(token, at)
			},
			jwt.WithValidMethods([]string{"RS256"}),
			jwt.WithIssuedAt(),
			jwt.WithExpirationRequired(),
			jwt.WithTimeFunc(func() time.Time { return at }),
		)
		return parseErr
	}
	for _, kid := range []string{"primary", "custom"} {
		require.NoError(
			t,
			parseAt(kid, freshUntil.Add(-time.Nanosecond)),
			"single unlabeled bootstrap key should verify a current JWT with kid %q",
			kid,
		)
		require.ErrorContains(
			t,
			parseAt(kid, freshUntil),
			"JWKS key snapshot is stale",
			"key-id compatibility must not extend bootstrap freshness for kid %q",
			kid,
		)
	}

	hmacToken := jwt.NewWithClaims(jwt.SigningMethodHS256, jwt.MapClaims{})
	_, err = middleware.keyFuncAt(hmacToken, freshUntil.Add(-time.Nanosecond))
	require.ErrorContains(t, err, "HS256 token rejected", "JWKS mode must not fall back to HMAC during the bootstrap window")
}

func TestJWKSKeyAndFreshnessSnapshotRemainsCoherentDuringConcurrentRefresh(t *testing.T) {
	oldKey, err := rsa.GenerateKey(rand.Reader, 2048)
	require.NoError(t, err)
	newKey, err := rsa.GenerateKey(rand.Reader, 2048)
	require.NoError(t, err)

	now := time.Now().UTC()
	middleware := &JWTMiddleware{}
	middleware.jwksConfigured.Store(true)
	middleware.jwksFreshnessLimit.Store(int64(time.Hour))
	middleware.storeRSAKeysAt(rsaKeySet{"old": &oldKey.PublicKey}, now.Add(-2*time.Hour))

	oldKeyToken := jwt.NewWithClaims(jwt.SigningMethodRS256, jwt.MapClaims{})
	oldKeyToken.Header["kid"] = "old"
	start := make(chan struct{})
	readersReady := make(chan struct{}, 4)
	writerDone := make(chan struct{})
	var workers sync.WaitGroup
	var accepted atomic.Int64
	var checked atomic.Int64

	workers.Add(1)
	go func() {
		defer workers.Done()
		<-start
		for range 4 {
			<-readersReady
		}
		for index := range 1000 {
			if index%2 == 0 {
				middleware.storeRSAKeysAt(rsaKeySet{"new": &newKey.PublicKey}, now)
			} else {
				middleware.storeRSAKeysAt(rsaKeySet{"old": &oldKey.PublicKey}, now.Add(-2*time.Hour))
			}
		}
		close(writerDone)
	}()

	for range 4 {
		workers.Add(1)
		go func() {
			defer workers.Done()
			<-start
			_, keyErr := middleware.keyFuncAt(oldKeyToken, now)
			checked.Add(1)
			if keyErr == nil {
				accepted.Add(1)
			}
			readersReady <- struct{}{}
			for {
				select {
				case <-writerDone:
					return
				default:
				}
				_, keyErr := middleware.keyFuncAt(oldKeyToken, now)
				checked.Add(1)
				if keyErr == nil {
					accepted.Add(1)
				}
			}
		}()
	}

	close(start)
	workers.Wait()
	require.Greater(t, checked.Load(), int64(0), "readers must observe refreshes")
	require.Zero(t, accepted.Load(), "a stale old key must never be paired with freshness from a newer key set")
}
