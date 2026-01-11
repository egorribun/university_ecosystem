package middleware

import (
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/golang-jwt/jwt/v5"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

const testSecret = "test-secret-key-for-testing-purposes"

func init() {
	gin.SetMode(gin.TestMode)
}

func createValidToken(secret string, claims Claims) string {
	token := jwt.NewWithClaims(jwt.SigningMethodHS256, claims)
	tokenString, _ := token.SignedString([]byte(secret))
	return tokenString
}

func createTestRouter(handler gin.HandlerFunc) *gin.Engine {
	router := gin.New()
	router.GET("/test", handler)
	return router
}

func TestNewJWTMiddleware_CreatesMiddlewareWithSecret(t *testing.T) {
	middleware := NewJWTMiddleware(testSecret)

	assert.NotNil(t, middleware)
	assert.Equal(t, []byte(testSecret), middleware.secret)
}

func TestValidate_RejectsMissingAuthorizationHeader(t *testing.T) {
	middleware := NewJWTMiddleware(testSecret)
	router := createTestRouter(middleware.Validate())

	request := httptest.NewRequest(http.MethodGet, "/test", nil)
	recorder := httptest.NewRecorder()

	router.ServeHTTP(recorder, request)

	assert.Equal(t, http.StatusUnauthorized, recorder.Code)
	assert.Contains(t, recorder.Body.String(), "missing authorization header")
}

func TestValidate_RejectsInvalidAuthorizationFormat(t *testing.T) {
	middleware := NewJWTMiddleware(testSecret)
	router := createTestRouter(middleware.Validate())

	testCases := []struct {
		name   string
		header string
	}{
		{"no bearer prefix", "invalid-token"},
		{"wrong prefix", "Basic token123"},
		{"bearer only", "Bearer"},
		{"empty value", "Bearer "},
	}

	for _, testCase := range testCases {
		t.Run(testCase.name, func(t *testing.T) {
			request := httptest.NewRequest(http.MethodGet, "/test", nil)
			request.Header.Set("Authorization", testCase.header)
			recorder := httptest.NewRecorder()

			router.ServeHTTP(recorder, request)

			assert.Equal(t, http.StatusUnauthorized, recorder.Code)
		})
	}
}

func TestValidate_RejectsInvalidToken(t *testing.T) {
	middleware := NewJWTMiddleware(testSecret)
	router := createTestRouter(middleware.Validate())

	request := httptest.NewRequest(http.MethodGet, "/test", nil)
	request.Header.Set("Authorization", "Bearer invalid.token.here")
	recorder := httptest.NewRecorder()

	router.ServeHTTP(recorder, request)

	assert.Equal(t, http.StatusUnauthorized, recorder.Code)
	assert.Contains(t, recorder.Body.String(), "invalid token")
}

func TestValidate_RejectsTokenSignedWithWrongSecret(t *testing.T) {
	middleware := NewJWTMiddleware(testSecret)
	router := createTestRouter(middleware.Validate())

	claims := Claims{
		RegisteredClaims: jwt.RegisteredClaims{
			ExpiresAt: jwt.NewNumericDate(time.Now().Add(time.Hour)),
		},
		UserID:   "user-123",
		IsActive: true,
	}
	wrongSecretToken := createValidToken("wrong-secret", claims)

	request := httptest.NewRequest(http.MethodGet, "/test", nil)
	request.Header.Set("Authorization", "Bearer "+wrongSecretToken)
	recorder := httptest.NewRecorder()

	router.ServeHTTP(recorder, request)

	assert.Equal(t, http.StatusUnauthorized, recorder.Code)
}

func TestValidate_RejectsInactiveUser(t *testing.T) {
	middleware := NewJWTMiddleware(testSecret)
	router := createTestRouter(middleware.Validate())

	claims := Claims{
		RegisteredClaims: jwt.RegisteredClaims{
			ExpiresAt: jwt.NewNumericDate(time.Now().Add(time.Hour)),
		},
		UserID:   "user-123",
		IsActive: false,
	}
	token := createValidToken(testSecret, claims)

	request := httptest.NewRequest(http.MethodGet, "/test", nil)
	request.Header.Set("Authorization", "Bearer "+token)
	recorder := httptest.NewRecorder()

	router.ServeHTTP(recorder, request)

	assert.Equal(t, http.StatusForbidden, recorder.Code)
	assert.Contains(t, recorder.Body.String(), "user account is not active")
}

func TestValidate_AcceptsValidTokenAndSetsContext(t *testing.T) {
	middleware := NewJWTMiddleware(testSecret)

	var capturedUserID interface{}
	var capturedEmail interface{}
	var capturedRole interface{}

	router := gin.New()
	router.GET("/test", middleware.Validate(), func(c *gin.Context) {
		capturedUserID, _ = c.Get("user_id")
		capturedEmail, _ = c.Get("user_email")
		capturedRole, _ = c.Get("user_role")
		c.Status(http.StatusOK)
	})

	claims := Claims{
		RegisteredClaims: jwt.RegisteredClaims{
			ExpiresAt: jwt.NewNumericDate(time.Now().Add(time.Hour)),
		},
		UserID:   "user-456",
		Email:    "test@example.com",
		Role:     "admin",
		IsActive: true,
	}
	token := createValidToken(testSecret, claims)

	request := httptest.NewRequest(http.MethodGet, "/test", nil)
	request.Header.Set("Authorization", "Bearer "+token)
	recorder := httptest.NewRecorder()

	router.ServeHTTP(recorder, request)

	assert.Equal(t, http.StatusOK, recorder.Code)
	assert.Equal(t, "user-456", capturedUserID)
	assert.Equal(t, "test@example.com", capturedEmail)
	assert.Equal(t, "admin", capturedRole)
}

func TestOptional_AllowsRequestWithoutToken(t *testing.T) {
	middleware := NewJWTMiddleware(testSecret)

	handlerCalled := false
	router := gin.New()
	router.GET("/test", middleware.Optional(), func(c *gin.Context) {
		handlerCalled = true
		c.Status(http.StatusOK)
	})

	request := httptest.NewRequest(http.MethodGet, "/test", nil)
	recorder := httptest.NewRecorder()

	router.ServeHTTP(recorder, request)

	assert.Equal(t, http.StatusOK, recorder.Code)
	assert.True(t, handlerCalled)
}

func TestOptional_ExtractsClaimsWhenTokenProvided(t *testing.T) {
	middleware := NewJWTMiddleware(testSecret)

	var capturedUserID interface{}
	router := gin.New()
	router.GET("/test", middleware.Optional(), func(c *gin.Context) {
		capturedUserID, _ = c.Get("user_id")
		c.Status(http.StatusOK)
	})

	claims := Claims{
		RegisteredClaims: jwt.RegisteredClaims{
			ExpiresAt: jwt.NewNumericDate(time.Now().Add(time.Hour)),
		},
		UserID:   "optional-user",
		IsActive: true,
	}
	token := createValidToken(testSecret, claims)

	request := httptest.NewRequest(http.MethodGet, "/test", nil)
	request.Header.Set("Authorization", "Bearer "+token)
	recorder := httptest.NewRecorder()

	router.ServeHTTP(recorder, request)

	assert.Equal(t, http.StatusOK, recorder.Code)
	assert.Equal(t, "optional-user", capturedUserID)
}

func TestRequireRole_RejectsWhenRoleNotInContext(t *testing.T) {
	router := gin.New()
	router.GET("/test", RequireRole("admin"))

	request := httptest.NewRequest(http.MethodGet, "/test", nil)
	recorder := httptest.NewRecorder()

	router.ServeHTTP(recorder, request)

	assert.Equal(t, http.StatusForbidden, recorder.Code)
	assert.Contains(t, recorder.Body.String(), "role not found")
}

func TestRequireRole_RejectsWrongRole(t *testing.T) {
	router := gin.New()
	router.GET("/test", func(c *gin.Context) {
		c.Set("user_role", "user")
		c.Next()
	}, RequireRole("admin", "moderator"))

	request := httptest.NewRequest(http.MethodGet, "/test", nil)
	recorder := httptest.NewRecorder()

	router.ServeHTTP(recorder, request)

	assert.Equal(t, http.StatusForbidden, recorder.Code)
	assert.Contains(t, recorder.Body.String(), "insufficient permissions")
}

func TestRequireRole_AcceptsMatchingRole(t *testing.T) {
	handlerCalled := false
	router := gin.New()
	router.GET("/test", func(c *gin.Context) {
		c.Set("user_role", "admin")
		c.Next()
	}, RequireRole("admin", "superadmin"), func(c *gin.Context) {
		handlerCalled = true
		c.Status(http.StatusOK)
	})

	request := httptest.NewRequest(http.MethodGet, "/test", nil)
	recorder := httptest.NewRecorder()

	router.ServeHTTP(recorder, request)

	assert.Equal(t, http.StatusOK, recorder.Code)
	require.True(t, handlerCalled)
}
