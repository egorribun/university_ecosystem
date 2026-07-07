package middleware

import (
	"context"
	"errors"
	"io"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// errorReader returns an error on Read.
type errorReader struct{}

func (e errorReader) Read(p []byte) (n int, err error) {
	return 0, errors.New("read error")
}

// roundTripFunc mocks http.RoundTripper.
type roundTripFunc func(req *http.Request) (*http.Response, error)

func (f roundTripFunc) RoundTrip(req *http.Request) (*http.Response, error) {
	return f(req)
}

func TestFetchJWKSPublicKey_EdgeCases(t *testing.T) {
	t.Run("nil response", func(t *testing.T) {
		client := &http.Client{
			Transport: roundTripFunc(func(req *http.Request) (*http.Response, error) {
				return nil, nil
			}),
		}
		_, err := fetchJWKSPublicKey(context.Background(), client, "http://localhost")
		require.Error(t, err)
		assert.Contains(t, err.Error(), "returned a nil *Response")
	})

	t.Run("body read error", func(t *testing.T) {
		client := &http.Client{
			Transport: roundTripFunc(func(req *http.Request) (*http.Response, error) {
				return &http.Response{
					StatusCode: http.StatusOK,
					Body:       io.NopCloser(errorReader{}),
				}, nil
			}),
		}
		_, err := fetchJWKSPublicKey(context.Background(), client, "http://localhost")
		require.Error(t, err)
		assert.Contains(t, err.Error(), "read body")
	})

	t.Run("malformed keys JSON element", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			w.WriteHeader(http.StatusOK)
			_, _ = w.Write([]byte(`{"keys": [123]}`)) // 123 is not a json object element for keys
		}))
		defer server.Close()

		_, err := fetchJWKSPublicKey(context.Background(), http.DefaultClient, server.URL)
		require.Error(t, err)
		assert.Contains(t, err.Error(), "no RSA key found")
	})

	t.Run("no RSA key found", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			w.WriteHeader(http.StatusOK)
			_, _ = w.Write([]byte(`{"keys": [{"kty": "EC"}]}`))
		}))
		defer server.Close()

		_, err := fetchJWKSPublicKey(context.Background(), http.DefaultClient, server.URL)
		require.Error(t, err)
		assert.Contains(t, err.Error(), "no RSA key found")
	})
}

func TestShouldRefreshProbabilistic_Expired(t *testing.T) {
	// TTL is 1 hour, stored 2 hours ago -> expired
	storedAt := time.Now().Add(-2 * time.Hour)
	assert.True(t, shouldRefreshProbabilistic(storedAt, time.Hour, 1.0))
}

func TestVerifySession_NilRedis(t *testing.T) {
	m := NewJWTMiddleware(testSecret, nil)
	m.redis = nil

	isValid, shouldDeny, err := m.verifySession(context.Background(), "jti-123", true)
	assert.True(t, isValid)
	assert.False(t, shouldDeny)
	assert.NoError(t, err)
}

func TestValidate_MalformedTokenHeader(t *testing.T) {
	gin.SetMode(gin.TestMode)
	_, pubPEM := rsaTestKeys(t)
	m := NewJWTMiddlewareWithConfig(testSecret, pubPEM, nil, DefaultL1CacheConfig())

	router := gin.New()
	router.GET("/test", m.Validate(context.Background()), func(c *gin.Context) {
		c.Status(http.StatusOK)
	})

	// Pass a token with a malformed header (non-base64)
	rec := httptest.NewRecorder()
	router.ServeHTTP(rec, bearerRequest(t, "invalid_header.payload.sig"))

	assert.Equal(t, http.StatusUnauthorized, rec.Code)
	assert.Contains(t, rec.Body.String(), "malformed token header")
}

func TestOptional_MalformedAndDowngrade(t *testing.T) {
	gin.SetMode(gin.TestMode)
	_, pubPEM := rsaTestKeys(t)
	m := NewJWTMiddlewareWithConfig(testSecret, pubPEM, nil, DefaultL1CacheConfig())

	probe, captured := captureContextHandler()
	router := gin.New()
	router.GET("/test", m.Optional(context.Background()), probe)

	t.Run("malformed header optional", func(t *testing.T) {
		rec := httptest.NewRecorder()
		router.ServeHTTP(rec, bearerRequest(t, "invalid_header.payload.sig"))

		assert.Equal(t, http.StatusOK, rec.Code)
		_, hasUser := (*captured)["user_id"]
		assert.False(t, hasUser, "should proceed unauthenticated on malformed header")
	})

	t.Run("algorithm downgrade optional", func(t *testing.T) {
		// HS256 token when RS256 is expected
		claims := freshClaims("jti-downgrade")
		token := createValidToken(testSecret, claims)

		rec := httptest.NewRecorder()
		router.ServeHTTP(rec, bearerRequest(t, token))

		assert.Equal(t, http.StatusOK, rec.Code)
		_, hasUser := (*captured)["user_id"]
		assert.False(t, hasUser, "should proceed unauthenticated on algorithm downgrade")
	})
}
