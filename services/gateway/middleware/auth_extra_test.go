package middleware

import (
	"context"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/golang-jwt/jwt/v5"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

type dummySigningMethod struct{}

func (d dummySigningMethod) Verify(signingString string, signature []byte, key interface{}) error {
	return nil
}
func (d dummySigningMethod) Sign(signingString string, key interface{}) ([]byte, error) {
	return []byte("sig"), nil
}
func (d dummySigningMethod) Alg() string {
	return "dummy"
}

func TestKeyFunc_UnexpectedSigningMethod(t *testing.T) {
	m := NewJWTMiddleware(testSecret, nil)
	tok := &jwt.Token{
		Method: dummySigningMethod{},
		Header: map[string]interface{}{"alg": "dummy"},
	}
	_, err := m.keyFunc(tok)
	require.Error(t, err)
	assert.Contains(t, err.Error(), "unexpected signing algorithm")
}

func TestKeyFunc_RS256NotConfigured(t *testing.T) {
	m := NewJWTMiddleware(testSecret, nil)
	tok := &jwt.Token{
		Method: jwt.SigningMethodRS256,
		Header: map[string]interface{}{"alg": "RS256"},
	}
	_, err := m.keyFunc(tok)
	require.Error(t, err)
	assert.Contains(t, err.Error(), "RS256 token received but JWKS_PUBLIC_KEY_PEM is not configured")
}

func TestKeyFunc_HS256DowngradeRejected(t *testing.T) {
	_, pubPEM := rsaTestKeys(t)
	m := NewJWTMiddlewareWithConfig(testSecret, pubPEM, nil, DefaultL1CacheConfig())
	tok := &jwt.Token{
		Method: jwt.SigningMethodHS256,
		Header: map[string]interface{}{"alg": "HS256"},
	}
	_, err := m.keyFunc(tok)
	require.Error(t, err)
	assert.Contains(t, err.Error(), "HS256 token rejected")
}

func TestValidate_InactiveUserAccount(t *testing.T) {
	gin.SetMode(gin.TestMode)
	m := NewJWTMiddleware(testSecret, nil)

	claims := Claims{
		RegisteredClaims: jwt.RegisteredClaims{
			ID:        "jti-inactive",
			IssuedAt:  jwt.NewNumericDate(time.Now().Add(-1 * time.Minute)),
			ExpiresAt: jwt.NewNumericDate(time.Now().Add(time.Hour)),
		},
		UserID:   "user-inactive",
		Role:     "student",
		IsActive: false, // inactive user
	}

	token := createValidToken(testSecret, claims)
	router := gin.New()
	router.GET("/test", m.Validate(context.Background()), func(c *gin.Context) {
		c.Status(http.StatusOK)
	})

	rec := httptest.NewRecorder()
	router.ServeHTTP(rec, bearerRequest(t, token))

	assert.Equal(t, http.StatusForbidden, rec.Code)
	assert.Contains(t, rec.Body.String(), "user account is not active")
}

func TestValidate_RedisDownFailSecure(t *testing.T) {
	gin.SetMode(gin.TestMode)
	
	url, stop := startMockRedis(t, mockRedisConfig{})
	m := newRedisMiddleware(t, url)
	stop() // close mockRedis to trigger connection refused/outage

	claims := freshClaims("jti-fail-secure")
	token := createValidToken(testSecret, claims)

	router := gin.New()
	router.GET("/test", m.Validate(context.Background()), func(c *gin.Context) {
		c.Status(http.StatusOK)
	})

	rec := httptest.NewRecorder()
	router.ServeHTTP(rec, bearerRequest(t, token))

	assert.Equal(t, http.StatusServiceUnavailable, rec.Code)
	assert.Contains(t, rec.Body.String(), "session verification temporarily unavailable")
}

func TestOptional_RedisDownFailSafe(t *testing.T) {
	gin.SetMode(gin.TestMode)
	
	url, stop := startMockRedis(t, mockRedisConfig{})
	m := newRedisMiddleware(t, url)
	stop() // close mockRedis to trigger connection refused/outage

	claims := freshClaims("jti-fail-safe")
	token := createValidToken(testSecret, claims)

	probe, captured := captureContextHandler()
	router := gin.New()
	router.GET("/test", m.Optional(context.Background()), probe)

	rec := httptest.NewRecorder()
	router.ServeHTTP(rec, bearerRequest(t, token))

	assert.Equal(t, http.StatusOK, rec.Code)
	_, hasUser := (*captured)["user_id"]
	assert.False(t, hasUser, "should continue as unauthenticated")
}

func TestStartJWKSRefresher_FailuresAndRetries(t *testing.T) {
	calls := 0
	_, pubPEM := rsaTestKeys(t)
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		calls++
		if calls == 1 {
			w.WriteHeader(http.StatusInternalServerError)
			_, _ = w.Write([]byte("unexpected status 500"))
			return
		}
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(pubPEM))
	}))
	defer srv.Close()

	m := NewJWTMiddleware(testSecret, nil)
	ctx, cancel := context.WithCancel(context.Background())
	logger := slog.New(slog.NewTextHandler(io.Discard, nil))
	
	go m.StartJWKSRefresher(ctx, srv.URL, 10*time.Millisecond, logger)
	
	// Wait to let both calls happen
	time.Sleep(50 * time.Millisecond)
	cancel()

	assert.NotNil(t, m.rsaPublicKey.Load())
}

func TestListenForRevocations_ConnFailure(t *testing.T) {
	url, stop := startMockRedis(t, mockRedisConfig{})
	m := newRedisMiddleware(t, url)
	stop() // close redis to trigger connection refused

	ctx, cancel := context.WithTimeout(context.Background(), 50*time.Millisecond)
	defer cancel()

	// Should run and return or retry without panicking
	m.ListenForRevocations(ctx)
}
