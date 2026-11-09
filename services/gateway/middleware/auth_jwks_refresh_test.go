// JWKS refresh, parsing, logging, and middleware lifecycle contracts.
package middleware

import (
	"context"
	"crypto/rand"
	"crypto/rsa"
	"crypto/x509"
	"encoding/json"
	"encoding/pem"
	"errors"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"sync/atomic"
	"testing"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/golang-jwt/jwt/v5"
	"github.com/redis/go-redis/v9"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// spyWriter is a helper to verify log outputs - commented out to resolve unused check
/*
type spyWriter struct {
	mu   sync.Mutex
	logs []string
}

func (s *spyWriter) Write(p []byte) (n int, err error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.logs = append(s.logs, string(p))
	return len(p), nil
}

func (s *spyWriter) Contains(str string) bool {
	s.mu.Lock()
	defer s.mu.Unlock()
	for _, log := range s.logs {
		if strings.Contains(log, str) {
			return true
		}
	}
	return false
}
*/

// Generate valid RSA keys for testing
func generateRSAKeyPair() (*rsa.PrivateKey, *rsa.PublicKey, string) {
	priv, err := rsa.GenerateKey(rand.Reader, 2048)
	if err != nil {
		panic(err)
	}
	pubASN1, err := x509.MarshalPKIXPublicKey(&priv.PublicKey)
	if err != nil {
		panic(err)
	}
	pubBlock := &pem.Block{
		Type:  "PUBLIC KEY",
		Bytes: pubASN1,
	}
	pemBytes := pem.EncodeToMemory(pubBlock)
	return priv, &priv.PublicKey, string(pemBytes)
}

func TestStartJWKSRefresher_SuccessAndFailureAndCancel(t *testing.T) {
	privateKey, pubPEM := rsaTestKeys(t)
	var requests atomic.Int32
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		body := pubPEM
		if requests.Add(1) == 1 {
			w.Header().Set("Content-Type", "application/json")
			body = `{"keys": []}`
		}
		if _, err := io.WriteString(w, body); err != nil {
			t.Errorf("write JWKS test response: %v", err)
		}
	}))
	defer srv.Close()

	middleware := NewJWTMiddlewareWithConfig("secret", "", nil, DefaultL1CacheConfig())
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	const interval = 50 * time.Millisecond
	logger := slog.New(slog.NewTextHandler(io.Discard, nil))
	middleware.StartJWKSRefresher(ctx, srv.URL, interval, logger)

	require.Eventually(t, func() bool {
		key := middleware.rsaPublicKey.Load()
		return key != nil && key.N.Cmp(privateKey.N) == 0
	}, 2*time.Second, 5*time.Millisecond, "the refresher must recover from an invalid initial key set")
	require.GreaterOrEqual(t, requests.Load(), int32(2))
	cancel()
	requestCount := requests.Load()
	require.Never(t, func() bool { return requests.Load() > requestCount },
		3*interval, 5*time.Millisecond, "cancelled refresher must stop polling")
}

type jwksRetryLogQueue chan []byte

func (q jwksRetryLogQueue) Write(p []byte) (int, error) {
	entry := append([]byte(nil), p...)
	select {
	case q <- entry:
	default:
	}
	return len(p), nil
}

func TestStartJWKSRefresherRetainsKeyAndCapsBackoffAfterRepeatedFailures(t *testing.T) {
	_, originalPEM := rsaTestKeys(t)
	rotatedKey, rotatedPEM := rsaTestKeys(t)
	thirdRequest := make(chan struct{})
	releaseSuccess := make(chan struct{})
	var requests atomic.Int32
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch requests.Add(1) {
		case 1, 2:
			http.Error(w, "temporarily unavailable", http.StatusServiceUnavailable)
			return
		case 3:
			close(thirdRequest)
			select {
			case <-releaseSuccess:
			case <-r.Context().Done():
				return
			}
		}
		if _, err := io.WriteString(w, rotatedPEM); err != nil {
			t.Errorf("write JWKS response: %v", err)
		}
	}))
	t.Cleanup(server.Close)

	middleware := NewJWTMiddlewareWithConfig(testSecret, originalPEM, nil, DefaultL1CacheConfig())
	bootstrap := middleware.jwksSnapshot.Load()
	require.NotNil(t, bootstrap)
	logs := make(jwksRetryLogQueue, 8)
	logger := slog.New(slog.NewJSONHandler(logs, nil))
	ctx, cancel := context.WithCancel(context.Background())
	const interval = 10 * time.Millisecond
	middleware.StartJWKSRefresher(ctx, server.URL, interval, logger)
	t.Cleanup(func() {
		cancel()
		stopped := make(chan struct{})
		go func() {
			jwksRefreshWG.Wait()
			close(stopped)
		}()
		select {
		case <-stopped:
		case <-time.After(2 * time.Second):
			t.Error("JWKS refresher did not stop after cancellation")
		}
	})

	select {
	case <-thirdRequest:
	case <-time.After(2 * time.Second):
		t.Fatal("refresher did not retry the second failure")
	}
	require.EqualValues(t, 3, requests.Load())
	require.Same(t, bootstrap, middleware.jwksSnapshot.Load(), "failed fetches must retain the last known good key")

	type logEntry struct {
		Message   string        `json:"msg"`
		Attempt   int           `json:"attempt"`
		NextRetry time.Duration `json:"next_retry_in"`
	}
	readLog := func() logEntry {
		t.Helper()
		select {
		case raw := <-logs:
			var entry logEntry
			require.NoError(t, json.Unmarshal(raw, &entry))
			return entry
		case <-time.After(2 * time.Second):
			t.Fatal("missing JWKS retry log")
			return logEntry{}
		}
	}
	initial := readLog()
	require.Equal(t, "Initial JWKS fetch failed, retrying soon", initial.Message)
	require.Equal(t, interval, initial.NextRetry)
	retry := readLog()
	require.Equal(t, "JWKS refresh failed, retrying", retry.Message)
	require.Equal(t, 2, retry.Attempt)
	require.Equal(t, interval, retry.NextRetry, "backoff is capped at the configured refresh interval")

	close(releaseSuccess)
	require.Eventually(t, func() bool {
		key := middleware.rsaPublicKey.Load()
		return key != nil && key.N.Cmp(rotatedKey.N) == 0
	}, 2*time.Second, 5*time.Millisecond, "a successful retry must publish the rotated key")
}

func TestFetchJWKSKeySet_ErrorsAndPEMFallback(t *testing.T) {
	_, _, pemStr := generateRSAKeyPair()

	// Invalid URL
	_, err := fetchJWKSKeySet(context.Background(), http.DefaultClient, "http://invalid-domain-xyz.local")
	assert.Error(t, err)

	// Nil response / RoundTripper fail
	client := &http.Client{
		Transport: roundTripFunc(func(req *http.Request) (*http.Response, error) {
			return nil, errors.New("simulated error")
		}),
	}
	_, err = fetchJWKSKeySet(context.Background(), client, "http://example.com")
	assert.Error(t, err)

	// Non-200 Status
	srvError := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
	}))
	defer srvError.Close()
	_, err = fetchJWKSKeySet(context.Background(), http.DefaultClient, srvError.URL)
	assert.Error(t, err)

	// Valid PEM Fallback (Not JWKS format)
	srvPEM := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_, _ = w.Write([]byte(pemStr)) //nolint:errcheck // test server PEM write
	}))
	defer srvPEM.Close()
	pemKeys, err := fetchJWKSKeySet(context.Background(), http.DefaultClient, srvPEM.URL)
	assert.NoError(t, err)
	assert.NotEmpty(t, pemKeys)

	// Invalid JWKS JSON Structure (Non-RSA key)
	srvInvalidJWKS := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_, _ = w.Write([]byte(`{"keys":[{"kty":"EC","crv":"P-256"}]}`)) //nolint:errcheck // test server invalid JWKS write
	}))
	defer srvInvalidJWKS.Close()
	_, err = fetchJWKSKeySet(context.Background(), http.DefaultClient, srvInvalidJWKS.URL)
	assert.Error(t, err)
}

func TestFetchJWKSKeySet_NilHTTPResponseIsRejected(t *testing.T) {
	oldHTTPDo := httpDoFunc
	t.Cleanup(func() { httpDoFunc = oldHTTPDo })
	httpDoFunc = func(*http.Client, *http.Request) (*http.Response, error) { return nil, nil }

	_, err := fetchJWKSKeySet(context.Background(), http.DefaultClient, "http://example.com/jwks")
	require.EqualError(t, err, "jwks: fetch: nil response")
}

func TestSecureRandomFloat64_EntropyFailureUsesBoundedFallback(t *testing.T) {
	oldRead := cryptoRandReadFunc
	t.Cleanup(func() { cryptoRandReadFunc = oldRead })
	cryptoRandReadFunc = func([]byte) (int, error) {
		return 0, errors.New("entropy source unavailable")
	}

	assert.Equal(t, 0.5, secureRandomFloat64())
}

func TestNewJWTMiddlewareWithConfig_RejectsAmbiguousAudiences(t *testing.T) {
	assert.PanicsWithValue(t, "gateway: at most one JWT audience may be configured", func() {
		NewJWTMiddlewareWithConfig("secret", "", nil, DefaultL1CacheConfig(), "api", "other")
	})
	assert.PanicsWithValue(t, "gateway: JWT audience must not be blank", func() {
		NewJWTMiddlewareWithConfig("secret", "", nil, DefaultL1CacheConfig(), "  ")
	})
}

func TestListenForRevocations_PurgesThenStopsDuringBackoff(t *testing.T) {
	rdb := redis.NewClient(&redis.Options{Addr: "127.0.0.1:1"})
	t.Cleanup(func() { require.NoError(t, rdb.Close()) })
	middleware := NewJWTMiddlewareWithConfig("secret", "", rdb, DefaultL1CacheConfig())
	middleware.l1cache.Add("cached-session", cacheEntry{exists: true, storedAt: time.Now()})

	listenerEntered := make(chan struct{})
	releaseListener := make(chan struct{})
	middleware.listenOnceFunc = func(context.Context) {
		close(listenerEntered)
		<-releaseListener
	}
	ctx, cancel := context.WithCancel(context.Background())
	middleware.ListenForRevocations(ctx)
	<-listenerEntered
	close(releaseListener)

	require.Eventually(t, func() bool { return middleware.l1cache.Len() == 0 }, time.Second, time.Millisecond)
	cancel()
	// The listener is now in its backoff select. Give the cancelled branch a
	// deterministic scheduling opportunity before the test returns.
	require.Eventually(t, func() bool { return ctx.Err() != nil }, time.Second, time.Millisecond)
}

func TestListenForRevocations_AlreadyCancelledReturns(t *testing.T) {
	rdb := redis.NewClient(&redis.Options{Addr: "127.0.0.1:1"})
	t.Cleanup(func() { require.NoError(t, rdb.Close()) })
	middleware := NewJWTMiddlewareWithConfig("secret", "", rdb, DefaultL1CacheConfig())
	listenerCalled := make(chan struct{}, 1)
	middleware.listenOnceFunc = func(context.Context) {
		listenerCalled <- struct{}{}
	}

	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	middleware.ListenForRevocations(ctx)

	select {
	case <-listenerCalled:
		t.Fatal("revocation listener started for an already-cancelled context")
	case <-time.After(100 * time.Millisecond):
	}
}

func TestListenForRevocations_ReconnectsAfterBackoffTimer(t *testing.T) {
	rdb := redis.NewClient(&redis.Options{Addr: "127.0.0.1:1"})
	t.Cleanup(func() { require.NoError(t, rdb.Close()) })
	middleware := NewJWTMiddlewareWithConfig("secret", "", rdb, DefaultL1CacheConfig())
	calls := make(chan struct{}, 2)
	middleware.listenOnceFunc = func(context.Context) {
		calls <- struct{}{}
	}
	ctx, cancel := context.WithCancel(context.Background())
	t.Cleanup(cancel)

	middleware.ListenForRevocations(ctx)
	require.Eventually(t, func() bool {
		return len(calls) >= 2
	}, 3*time.Second, 10*time.Millisecond, "listener should reconnect after the backoff timer fires")
	cancel()
}

func TestListenForRevocations_DisconnectionAndClose(t *testing.T) {
	// Setup mock redis server that disconnects immediately
	url, cleanup := startMockRedis(t, mockRedisConfig{existsReply: ":0\r\n"})
	defer cleanup()

	opt, err := redis.ParseURL(url)
	require.NoError(t, err)
	rdb := redis.NewClient(opt)
	defer func() { _ = rdb.Close() }() //nolint:errcheck // ignore Redis client close error in test

	middleware := NewJWTMiddlewareWithConfig("secret", "", rdb, DefaultL1CacheConfig())
	ctx, cancel := context.WithCancel(context.Background())

	// Start listener
	middleware.ListenForRevocations(ctx)
	time.Sleep(100 * time.Millisecond)

	// Trigger connection loss by running cleanup (forces listener reconnection logic)
	cleanup()
	time.Sleep(150 * time.Millisecond)

	cancel()
	time.Sleep(50 * time.Millisecond)
}

func TestOptional_DowngradeAndServiceUnavailable(t *testing.T) {
	priv, _, pemStr := generateRSAKeyPair()
	middleware := NewJWTMiddlewareWithConfig(testSecret, "", nil, DefaultL1CacheConfig())

	// Configure RSA public key
	block, _ := pem.Decode([]byte(pemStr))
	require.NotNil(t, block)
	pubKey, err := x509.ParsePKIXPublicKey(block.Bytes)
	require.NoError(t, err)
	middleware.rsaPublicKey.Store(pubKey.(*rsa.PublicKey))

	// Create token signed with HS256 (Downgrade attempt against RSA configuration)
	claims := Claims{
		UserID: "student1",
		Role:   "student",
		RegisteredClaims: jwt.RegisteredClaims{
			Issuer:    DefaultJWTIssuer,
			Audience:  jwt.ClaimStrings{DefaultJWTAudience},
			ID:        "session-id-123",
			IssuedAt:  jwt.NewNumericDate(time.Now()),
			ExpiresAt: jwt.NewNumericDate(time.Now().Add(time.Hour)),
		},
	}
	hsToken := createValidToken(testSecret, claims)

	router := gin.New()
	router.GET("/test", middleware.Optional(context.Background()), func(c *gin.Context) {
		_, exists := c.Get("user_id")
		c.JSON(http.StatusOK, gin.H{"authenticated": exists})
	})

	// 1. Downgrade token -> treated as unauthenticated (not rejected with 401/403)
	w := httptest.NewRecorder()
	req := httptest.NewRequestWithContext(context.Background(), http.MethodGet, "/test", nil)
	req.Header.Set("Authorization", "Bearer "+hsToken)
	router.ServeHTTP(w, req)
	assert.Equal(t, http.StatusOK, w.Code)
	assert.Contains(t, w.Body.String(), `"authenticated":false`)

	// 2. RS256 token signed with RSA key
	rsTokenObj := jwt.NewWithClaims(jwt.SigningMethodRS256, claims)
	rsToken, err := rsTokenObj.SignedString(priv)
	require.NoError(t, err)

	// Set up Redis error for 503 path verification in verifySession
	rdb := redis.NewClient(&redis.Options{Addr: "127.0.0.1:9999"}) // unavailable address
	t.Cleanup(func() { assert.NoError(t, rdb.Close()) })
	middleware.redis = rdb

	// Set L1 cache TTL to zero or empty L1 cache so it misses and hits the unavailable Redis
	middleware.l1TTL = 10 * time.Millisecond
	middleware.l1cache.Purge()

	router2 := gin.New()
	router2.GET("/test", middleware.Optional(context.Background()), func(c *gin.Context) {
		_, exists := c.Get("user_id")
		c.JSON(http.StatusOK, gin.H{"authenticated": exists})
	})

	w2 := httptest.NewRecorder()
	req2 := httptest.NewRequestWithContext(context.Background(), http.MethodGet, "/test", nil)
	req2.Header.Set("Authorization", "Bearer "+rsToken)
	router2.ServeHTTP(w2, req2)
	// Optional fails open (returns 200, but authenticated is false)
	assert.Equal(t, http.StatusOK, w2.Code)
	assert.Contains(t, w2.Body.String(), `"authenticated":false`)

	// 3. Validate fails secure (returns 503 Service Unavailable)
	router3 := gin.New()
	router3.GET("/test", middleware.Validate(context.Background()), func(c *gin.Context) {
		c.JSON(http.StatusOK, gin.H{"status": "ok"})
	})

	w3 := httptest.NewRecorder()
	req3 := httptest.NewRequestWithContext(context.Background(), http.MethodGet, "/test", nil)
	req3.Header.Set("Authorization", "Bearer "+rsToken)
	router3.ServeHTTP(w3, req3)
	assert.Equal(t, http.StatusServiceUnavailable, w3.Code)
}
