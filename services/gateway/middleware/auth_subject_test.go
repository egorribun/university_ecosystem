package middleware

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/golang-jwt/jwt/v5"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func signedTokenWithoutSubject(t *testing.T) string {
	t.Helper()
	claims := jwt.MapClaims{
		"aud":       DefaultJWTAudience,
		"exp":       time.Now().Add(time.Hour).Unix(),
		"iat":       time.Now().Add(-time.Minute).Unix(),
		"jti":       "missing-subject-jti",
		"is_active": true,
		"role":      "student",
	}
	token, err := jwt.NewWithClaims(jwt.SigningMethodHS256, claims).SignedString([]byte(testSecret))
	require.NoError(t, err)
	return token
}

func TestValidate_RejectsTokenWithoutSubject(t *testing.T) {
	middleware := newUnrevokedJWTMiddleware(t)
	token := signedTokenWithoutSubject(t)

	handlerCalled := false
	router := gin.New()
	router.GET("/test", middleware.Validate(context.Background()), func(c *gin.Context) {
		handlerCalled = true
		c.Status(http.StatusOK)
	})
	recorder := httptest.NewRecorder()
	router.ServeHTTP(recorder, bearerRequest(t, token))

	assert.Equal(t, http.StatusUnauthorized, recorder.Code)
	assert.False(t, handlerCalled, "a token without a subject must not reach protected handlers")
}

func TestOptional_InactivePrincipalRemainsUnauthenticated(t *testing.T) {
	middleware := newUnrevokedJWTMiddleware(t)
	claims := revocableClaims("inactive-optional-jti")
	claims.IsActive = false
	token := createValidToken(testSecret, claims)

	var authenticated bool
	router := gin.New()
	router.GET("/test", middleware.Optional(context.Background()), func(c *gin.Context) {
		_, authenticated = c.Get("user_id")
		c.Status(http.StatusOK)
	})
	recorder := httptest.NewRecorder()
	router.ServeHTTP(recorder, bearerRequest(t, token))

	assert.Equal(t, http.StatusOK, recorder.Code)
	assert.False(t, authenticated, "an inactive principal must not be asserted to downstream services")
}

func TestOptional_MissingSubjectRemainsUnauthenticated(t *testing.T) {
	middleware := newUnrevokedJWTMiddleware(t)
	token := signedTokenWithoutSubject(t)

	var authenticated bool
	router := gin.New()
	router.GET("/test", middleware.Optional(context.Background()), func(c *gin.Context) {
		_, authenticated = c.Get("user_id")
		c.Status(http.StatusOK)
	})
	recorder := httptest.NewRecorder()
	router.ServeHTTP(recorder, bearerRequest(t, token))

	assert.Equal(t, http.StatusOK, recorder.Code)
	assert.False(t, authenticated, "a token without a subject must remain anonymous")
}
