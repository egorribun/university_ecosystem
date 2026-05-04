package middleware

import (
	"context"
	"fmt"
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
	tokenString, err := token.SignedString([]byte(secret))
	if err != nil {
		panic(fmt.Sprintf("failed to sign test token: %v", err))
	}
	return tokenString
}

func createTestRouter(handler gin.HandlerFunc) *gin.Engine {
	router := gin.New()
	router.GET("/test", handler)
	return router
}

func TestNewJWTMiddleware_CreatesMiddlewareWithSecret(t *testing.T) {
	middleware := NewJWTMiddleware(testSecret, nil)

	assert.NotNil(t, middleware)
	assert.Equal(t, []byte(testSecret), middleware.secret)
}

func TestValidate_RejectsMissingAuthorizationHeader(t *testing.T) {
	middleware := NewJWTMiddleware(testSecret, nil)
	router := createTestRouter(middleware.Validate(context.Background()))

	request := httptest.NewRequest(http.MethodGet, "/test", nil)
	recorder := httptest.NewRecorder()

	router.ServeHTTP(recorder, request)

	assert.Equal(t, http.StatusUnauthorized, recorder.Code)
	assert.Contains(t, recorder.Body.String(), "missing authorization header")
}

func TestValidate_RejectsInvalidAuthorizationFormat(t *testing.T) {
	middleware := NewJWTMiddleware(testSecret, nil)
	router := createTestRouter(middleware.Validate(context.Background()))

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
	middleware := NewJWTMiddleware(testSecret, nil)
	router := createTestRouter(middleware.Validate(context.Background()))

	request := httptest.NewRequest(http.MethodGet, "/test", nil)
	request.Header.Set("Authorization", "Bearer invalid.token.here")
	recorder := httptest.NewRecorder()

	router.ServeHTTP(recorder, request)

	assert.Equal(t, http.StatusUnauthorized, recorder.Code)
	assert.Contains(t, recorder.Body.String(), "invalid token")
}

func TestValidate_RejectsTokenSignedWithWrongSecret(t *testing.T) {
	middleware := NewJWTMiddleware(testSecret, nil)
	router := createTestRouter(middleware.Validate(context.Background()))

	claims := Claims{
		RegisteredClaims: jwt.RegisteredClaims{
			ExpiresAt: jwt.NewNumericDate(time.Now().Add(time.Hour)),
			IssuedAt:  jwt.NewNumericDate(time.Now()),
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
	middleware := NewJWTMiddleware(testSecret, nil)
	router := createTestRouter(middleware.Validate(context.Background()))

	claims := Claims{
		RegisteredClaims: jwt.RegisteredClaims{
			ExpiresAt: jwt.NewNumericDate(time.Now().Add(time.Hour)),
			IssuedAt:  jwt.NewNumericDate(time.Now()),
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
	middleware := NewJWTMiddleware(testSecret, nil)

	var capturedUserID interface{}
	var capturedRole interface{}

	router := gin.New()
	router.GET("/test", middleware.Validate(context.Background()), func(c *gin.Context) {
		capturedUserID, _ = c.Get("user_id")
		capturedRole, _ = c.Get("user_role")
		c.Status(http.StatusOK)
	})

	claims := Claims{
		RegisteredClaims: jwt.RegisteredClaims{
			ExpiresAt: jwt.NewNumericDate(time.Now().Add(time.Hour)),
			IssuedAt:  jwt.NewNumericDate(time.Now()),
		},
		UserID:   "user-456",
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
	assert.Equal(t, "admin", capturedRole)
}

func TestOptional_AllowsRequestWithoutToken(t *testing.T) {
	middleware := NewJWTMiddleware(testSecret, nil)

	handlerCalled := false
	router := gin.New()
	router.GET("/test", middleware.Optional(context.Background()), func(c *gin.Context) {
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
	middleware := NewJWTMiddleware(testSecret, nil)

	var capturedUserID interface{}
	router := gin.New()
	router.GET("/test", middleware.Optional(context.Background()), func(c *gin.Context) {
		capturedUserID, _ = c.Get("user_id")
		c.Status(http.StatusOK)
	})

	claims := Claims{
		RegisteredClaims: jwt.RegisteredClaims{
			ExpiresAt: jwt.NewNumericDate(time.Now().Add(time.Hour)),
			IssuedAt:  jwt.NewNumericDate(time.Now()),
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

// TestShouldRefreshProbabilistic_BoundaryAndStatistical exercises the XFetch
// refresh-probability function (PERF-31-02) directly with synthetic timestamps
// — much faster + more deterministic than the integration test variant. Runs
// in microseconds because no real wall-clock waits are involved.
//
// XFetch math (auth.go:450-461) for beta=1.0:
//
//	refresh = remaining < -ttl * ln(rand)
//	       ↔ rand < e^(-remaining/ttl)
//
// So the refresh probability is e^(-remaining/ttl), monotonically increasing
// from ~36.8% (full TTL remaining) toward 100% (entry near expiry).
//
// Three sub-tests:
//   - expired_always_refreshes: remaining ≤ 0 short-circuit at line 452-454,
//     no rand involvement, must always return true.
//   - fresh_one_third_rate: just-stored entries with full TTL remaining
//     refresh at ~36.8% rate (e^-1). Bounds 280-470 over 1000 trials.
//   - near_expiry_high_rate: entries 80% through TTL (remaining=20% of TTL)
//     refresh at ~81.9% rate (e^-0.2). Bounds 700-950 over 1000 trials.
//
// Companion to TestIntegration_L1CacheXFetchProbabilisticRefresh which wires
// the same function through verifySession + real Redis.
func TestShouldRefreshProbabilistic_BoundaryAndStatistical(t *testing.T) {
	t.Run("expired_always_refreshes", func(t *testing.T) {
		// storedAt 2s ago, TTL 1s → remaining = -1s; line 452 short-circuit.
		require.True(t, shouldRefreshProbabilistic(time.Now().Add(-2*time.Second), time.Second, 1.0),
			"expired entries (remaining ≤ 0) must always trigger refresh")
	})

	t.Run("fresh_one_third_rate", func(t *testing.T) {
		// Just-stored entries with full 10s TTL remaining. Per the XFetch
		// formula `rand < e^(-remaining/ttl)` for beta=1, fresh entries
		// (remaining ≈ ttl) refresh at ~e^-1 ≈ 36.8%.
		var fired int
		for i := 0; i < 1000; i++ {
			if shouldRefreshProbabilistic(time.Now(), 10*time.Second, 1.0) {
				fired++
			}
		}
		require.Greater(t, fired, 280,
			"fresh entries must refresh at ~36.8%% (>28%%), got %d/1000", fired)
		require.Less(t, fired, 470,
			"fresh entries must refresh at ~36.8%% (<47%%), got %d/1000", fired)
	})

	t.Run("near_expiry_high_rate", func(t *testing.T) {
		// 8s of 10s TTL elapsed → 2s remaining. Per `rand < e^(-remaining/ttl)`,
		// refresh probability is e^-0.2 ≈ 81.9%.
		storedAt := time.Now().Add(-8 * time.Second)
		var fired int
		for i := 0; i < 1000; i++ {
			if shouldRefreshProbabilistic(storedAt, 10*time.Second, 1.0) {
				fired++
			}
		}
		require.Greater(t, fired, 700,
			"near-expiry entries must refresh at ~81.9%% (>70%%), got %d/1000", fired)
		require.Less(t, fired, 950,
			"near-expiry entries must refresh at ~81.9%% (<95%%), got %d/1000", fired)
	})
}
