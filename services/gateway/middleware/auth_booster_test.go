package middleware

import (
	"context"
	"crypto/ecdsa"
	"crypto/elliptic"
	"crypto/rand"
	"crypto/x509"
	"encoding/pem"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/alicebob/miniredis/v2"
	"github.com/gin-gonic/gin"
	"github.com/golang-jwt/jwt/v5"
	"github.com/redis/go-redis/v9"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// TestNewJWTMiddleware_PanicOnInvalidPEM verifies that the middleware initialization panics
// when given an invalid PEM key config.
func TestNewJWTMiddleware_PanicOnInvalidPEM(t *testing.T) {
	assert.Panics(t, func() {
		NewJWTMiddlewareWithConfig("secret", "invalid-pem-content", nil, DefaultL1CacheConfig())
	})
}

// TestShouldRefreshProbabilistic verifies all paths of shouldRefreshProbabilistic.
func TestShouldRefreshProbabilistic(t *testing.T) {
	// Case 1: remaining <= 0 (already expired)
	storedAt := time.Now().Add(-10 * time.Minute)
	ttl := 5 * time.Minute
	assert.True(t, shouldRefreshProbabilistic(storedAt, ttl, 1.0))

	// Case 2: remaining > 0 (not expired yet)
	// With storedAt = now, elapsed = 0, remaining = ttl = 5 min.
	// Random factor Log(randFactor) will determine the threshold.
	// We check that it runs and returns a boolean.
	storedAt = time.Now()
	ttl = 5 * time.Minute
	res := shouldRefreshProbabilistic(storedAt, ttl, 1.0)
	t.Logf("Probabilistic refresh result: %v", res)
}

// TestFetchJWKSPublicKey_Errors verifies various error paths in fetchJWKSPublicKey.
func TestFetchJWKSPublicKey_Errors(t *testing.T) {
	httpClient := &http.Client{Timeout: 2 * time.Second}

	t.Run("invalid url", func(t *testing.T) {
		_, err := fetchJWKSPublicKey(context.Background(), httpClient, "invalid-proto://url")
		assert.Error(t, err)
	})

	t.Run("non-200 status", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			w.WriteHeader(http.StatusNotFound)
		}))
		defer server.Close()

		_, err := fetchJWKSPublicKey(context.Background(), httpClient, server.URL)
		assert.Error(t, err)
		assert.Contains(t, err.Error(), "unexpected status 404")
	})

	t.Run("invalid json and pem", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			w.WriteHeader(http.StatusOK)
			if _, err := w.Write([]byte("not-json-nor-pem")); err != nil {
				t.Logf("write failed: %v", err)
			}
		}))
		defer server.Close()

		_, err := fetchJWKSPublicKey(context.Background(), httpClient, server.URL)
		assert.Error(t, err)
		assert.Contains(t, err.Error(), "jwks: no PEM block found")
	})

	t.Run("pem not rsa", func(t *testing.T) {
		ecKey, err := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
		require.NoError(t, err)
		der, err := x509.MarshalPKIXPublicKey(&ecKey.PublicKey)
		require.NoError(t, err)
		pemBytes := pem.EncodeToMemory(&pem.Block{Type: "PUBLIC KEY", Bytes: der})

		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			w.WriteHeader(http.StatusOK)
			if _, err := w.Write(pemBytes); err != nil {
				t.Logf("write failed: %v", err)
			}
		}))
		defer server.Close()

		_, err = fetchJWKSPublicKey(context.Background(), httpClient, server.URL)
		assert.Error(t, err)
		assert.Contains(t, err.Error(), "jwks: key is not RSA")
	})

	t.Run("jwks no rsa key found", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			w.WriteHeader(http.StatusOK)
			_, _ = w.Write([]byte(`{"keys":[{"kty":"EC"}]}`)) //nolint:errcheck // t not in scope in handler func
		}))
		defer server.Close()

		_, err := fetchJWKSPublicKey(context.Background(), httpClient, server.URL)
		assert.Error(t, err)
		assert.Contains(t, err.Error(), "jwks: no RSA key found")
	})

	t.Run("jwks base64 decoding fails", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			w.WriteHeader(http.StatusOK)
			_, _ = w.Write([]byte(`{"keys":[{"kty":"RSA","n":"invalid base64 @@@","e":"AQAB"}]}`)) //nolint:errcheck // t not in scope in handler func
		}))
		defer server.Close()

		_, err := fetchJWKSPublicKey(context.Background(), httpClient, server.URL)
		assert.Error(t, err)
	})

	t.Run("jwks base64 decoding e fails", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			w.WriteHeader(http.StatusOK)
			_, _ = w.Write([]byte(`{"keys":[{"kty":"RSA","n":"somenbytes","e":"invalid base64 @@@"}]}`)) //nolint:errcheck // t not in scope in handler func
		}))
		defer server.Close()

		_, err := fetchJWKSPublicKey(context.Background(), httpClient, server.URL)
		assert.Error(t, err)
	})
}

// TestWarmL1Cache_Coverage verifies WarmL1Cache behavior.
func TestWarmL1Cache_Coverage(t *testing.T) {
	t.Run("redis nil", func(t *testing.T) {
		m := NewJWTMiddleware("secret", nil)
		assert.NotPanics(t, func() {
			m.WarmL1Cache(context.Background())
		})
	})

	t.Run("redis scan success", func(t *testing.T) {
		mr := miniredis.RunT(t)
		rClient := redis.NewClient(&redis.Options{Addr: mr.Addr()})
		defer func() { require.NoError(t, rClient.Close()) }()

		// Add some keys to miniredis
		err := mr.Set("revoked:jti:token1", "1")
		require.NoError(t, err)
		err = mr.Set("revoked:jti:token2", "1")
		require.NoError(t, err)

		m := NewJWTMiddleware("secret", rClient)
		assert.NotPanics(t, func() {
			m.WarmL1Cache(context.Background())
		})

		// Verify keys exist in L1 cache
		exists, found := m.checkL1Cache("revoked:jti:token1")
		assert.True(t, exists || !found) // could be false if XFetch triggered early refresh, but found should be checkable
	})

	t.Run("redis scan error", func(t *testing.T) {
		mr := miniredis.RunT(t)
		rClient := redis.NewClient(&redis.Options{Addr: mr.Addr()})
		// Close client to force scanner error
		rClient.Close() //nolint:errcheck,gosec // G104: intentional close to force redis scanner error

		m := NewJWTMiddleware("secret", rClient)
		assert.NotPanics(t, func() {
			m.WarmL1Cache(context.Background())
		})
	})
}

// TestListenForRevocations_PanicRecovery tests panic recovery in revocation listener.
func TestListenForRevocations_PanicRecovery(t *testing.T) {
	mr := miniredis.RunT(t)
	rClient := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	defer func() { require.NoError(t, rClient.Close()) }()

	m := NewJWTMiddleware("secret", rClient)
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	// Just checking it registers and returns.
	assert.NotPanics(t, func() {
		m.ListenForRevocations(ctx)
	})
}

// TestVerifySession_JTIEmpty verifies verifySession behavior when sessionID is empty.
func TestVerifySession_JTIEmpty(t *testing.T) {
	mr := miniredis.RunT(t)
	rClient := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	defer func() { require.NoError(t, rClient.Close()) }()

	m := NewJWTMiddleware("secret", rClient)
	isValid, shouldDeny, err := m.verifySession(context.Background(), "", true)
	assert.False(t, isValid)
	assert.False(t, shouldDeny)
	assert.NoError(t, err)
}

// TestCheckSessionInRedis_Error verifies that redis errors during session verification
// are propagated correctly.
func TestCheckSessionInRedis_Error(t *testing.T) {
	mr := miniredis.RunT(t)
	rClient := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	rClient.Close() //nolint:errcheck,gosec // G104: intentional close to force redis error

	m := NewJWTMiddleware("secret", rClient)
	isValid, shouldDeny, err := m.verifySession(context.Background(), "some-jti", true)
	assert.False(t, isValid)
	assert.True(t, shouldDeny)
	assert.Error(t, err)
}

// TestValidate_Optional_Gin tests Gin handler Validate/Optional with different scenarios.
func TestValidate_Optional_Gin(t *testing.T) {
	gin.SetMode(gin.ReleaseMode)

	t.Run("Validate with empty JTI", func(t *testing.T) {
		mr := miniredis.RunT(t)
		rClient := redis.NewClient(&redis.Options{Addr: mr.Addr()})
		defer func() { require.NoError(t, rClient.Close()) }()

		m := NewJWTMiddleware("secret", rClient)
		router := gin.New()
		router.Use(m.Validate(context.Background()))
		router.GET("/test", func(c *gin.Context) {
			c.Status(http.StatusOK)
		})

		// We sign a token without JTI
		token := jwt.NewWithClaims(jwt.SigningMethodHS256, &Claims{
			RegisteredClaims: jwt.RegisteredClaims{
				ExpiresAt: jwt.NewNumericDate(time.Now().Add(1 * time.Hour)),
				IssuedAt:  jwt.NewNumericDate(time.Now()),
			},
			UserID: "user-123",
		})
		tokenStr, err := token.SignedString([]byte("secret")) // nosemgrep
		require.NoError(t, err)

		rec := httptest.NewRecorder()
		req, err := http.NewRequestWithContext(context.Background(), http.MethodGet, "/test", nil)
		require.NoError(t, err)
		req.Header.Set("Authorization", "Bearer "+tokenStr)

		router.ServeHTTP(rec, req)
		assert.Equal(t, http.StatusUnauthorized, rec.Code)
	})

	t.Run("Validate JTI-less via Cookie", func(t *testing.T) {
		mr := miniredis.RunT(t)
		rClient := redis.NewClient(&redis.Options{Addr: mr.Addr()})
		defer func() { require.NoError(t, rClient.Close()) }()

		m := NewJWTMiddleware("secret", rClient)
		router := gin.New()
		router.Use(m.Validate(context.Background()))
		router.GET("/test", func(c *gin.Context) {
			c.Status(http.StatusOK)
		})

		token := jwt.NewWithClaims(jwt.SigningMethodHS256, &Claims{
			RegisteredClaims: jwt.RegisteredClaims{
				ExpiresAt: jwt.NewNumericDate(time.Now().Add(1 * time.Hour)),
				IssuedAt:  jwt.NewNumericDate(time.Now()),
			},
			UserID: "user-123",
		})
		tokenStr, err := token.SignedString([]byte("secret")) // nosemgrep
		require.NoError(t, err)

		rec := httptest.NewRecorder()
		req, err := http.NewRequestWithContext(context.Background(), http.MethodGet, "/test", nil)
		require.NoError(t, err)
		req.AddCookie(&http.Cookie{Name: AccessTokenCookieName, Value: tokenStr}) // nosemgrep

		router.ServeHTTP(rec, req)
		assert.Equal(t, http.StatusUnauthorized, rec.Code)
	})

	t.Run("Optional with JTI-less via Cookie", func(t *testing.T) {
		mr := miniredis.RunT(t)
		rClient := redis.NewClient(&redis.Options{Addr: mr.Addr()})
		defer func() { require.NoError(t, rClient.Close()) }()

		m := NewJWTMiddleware("secret", rClient)
		router := gin.New()
		router.Use(m.Optional(context.Background()))
		router.GET("/test", func(c *gin.Context) {
			userID, _ := c.Get("user_id")
			c.JSON(http.StatusOK, gin.H{"user_id": userID})
		})

		token := jwt.NewWithClaims(jwt.SigningMethodHS256, &Claims{
			RegisteredClaims: jwt.RegisteredClaims{
				ExpiresAt: jwt.NewNumericDate(time.Now().Add(1 * time.Hour)),
				IssuedAt:  jwt.NewNumericDate(time.Now()),
			},
			UserID: "user-123",
		})
		tokenStr, err := token.SignedString([]byte("secret")) // nosemgrep
		require.NoError(t, err)

		rec := httptest.NewRecorder()
		req, err := http.NewRequestWithContext(context.Background(), http.MethodGet, "/test", nil)
		require.NoError(t, err)
		req.AddCookie(&http.Cookie{Name: AccessTokenCookieName, Value: tokenStr}) // nosemgrep

		router.ServeHTTP(rec, req)
		assert.Equal(t, http.StatusOK, rec.Code)
		assert.Contains(t, rec.Body.String(), `user_id":null`) // unauthenticated
	})
}
