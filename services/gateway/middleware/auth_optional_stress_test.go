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
)

func createOptionalTestRouter(m *JWTMiddleware, capturedState *map[string]interface{}) *gin.Engine {
	router := gin.New()
	router.GET("/optional-test", m.Optional(context.Background()), func(c *gin.Context) {
		state := make(map[string]interface{})
		if val, exists := c.Get("user_id"); exists {
			state["user_id"] = val
		}
		if val, exists := c.Get("user_role"); exists {
			state["user_role"] = val
		}
		if val, exists := c.Get("session_id"); exists {
			state["session_id"] = val
		}
		if val, exists := c.Get("tenant_id"); exists {
			state["tenant_id"] = val
		}
		if val, exists := c.Get("claims"); exists {
			state["claims"] = val
		}
		*capturedState = state
		c.Status(http.StatusOK)
	})
	return router
}

func TestOptional_TenantPropagation_NoHeaderNoToken(t *testing.T) {
	m := NewJWTMiddlewareWithConfig(testSecret, "", nil, DefaultL1CacheConfig())
	capturedState := make(map[string]interface{})
	router := createOptionalTestRouter(m, &capturedState)

	req := httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/optional-test", nil)
	rec := httptest.NewRecorder()

	router.ServeHTTP(rec, req)

	assert.Equal(t, http.StatusOK, rec.Code)
	assert.Nil(t, capturedState["user_id"])
	assert.Nil(t, capturedState["tenant_id"])
}

func TestOptional_TenantPropagation_HeaderOnlyNoToken(t *testing.T) {
	m := NewJWTMiddlewareWithConfig(testSecret, "", nil, DefaultL1CacheConfig())
	capturedState := make(map[string]interface{})
	router := createOptionalTestRouter(m, &capturedState)

	req := httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/optional-test", nil)
	req.Header.Set("X-Tenant-ID", "tenant-hdr-100")
	rec := httptest.NewRecorder()

	router.ServeHTTP(rec, req)

	assert.Equal(t, http.StatusOK, rec.Code)
	assert.Nil(t, capturedState["user_id"])
	assert.Nil(t, capturedState["tenant_id"])
}

func TestOptional_TenantPropagation_TokenOnlyNoHeader(t *testing.T) {
	m := newUnrevokedJWTMiddleware(t)
	capturedState := make(map[string]interface{})
	router := createOptionalTestRouter(m, &capturedState)

	claims := Claims{
		RegisteredClaims: jwt.RegisteredClaims{
			ExpiresAt: jwt.NewNumericDate(time.Now().Add(time.Hour)),
			IssuedAt:  jwt.NewNumericDate(time.Now()),
			ID:        "sess-jwt-1",
		},
		UserID:   "user-jwt-1",
		Role:     "student",
		IsActive: true,
		TenantID: "tenant-jwt-200",
	}
	tokenStr := createValidToken(testSecret, claims)

	req := httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/optional-test", nil)
	req.Header.Set("Authorization", "Bearer "+tokenStr)
	rec := httptest.NewRecorder()

	router.ServeHTTP(rec, req)

	assert.Equal(t, http.StatusOK, rec.Code)
	assert.Equal(t, "user-jwt-1", capturedState["user_id"])
	assert.Equal(t, "tenant-jwt-200", capturedState["tenant_id"])
}

func TestOptional_TenantPropagation_HeaderAndTokenPrecedence(t *testing.T) {
	m := newUnrevokedJWTMiddleware(t)
	capturedState := make(map[string]interface{})
	router := createOptionalTestRouter(m, &capturedState)

	claims := Claims{
		RegisteredClaims: jwt.RegisteredClaims{
			ExpiresAt: jwt.NewNumericDate(time.Now().Add(time.Hour)),
			IssuedAt:  jwt.NewNumericDate(time.Now()),
			ID:        "sess-jwt-2",
		},
		UserID:   "user-jwt-2",
		Role:     "teacher",
		IsActive: true,
		TenantID: "tenant-jwt-from-claims",
	}
	tokenStr := createValidToken(testSecret, claims)

	req := httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/optional-test", nil)
	req.Header.Set("X-Tenant-ID", "tenant-hdr-override")
	req.Header.Set("Authorization", "Bearer "+tokenStr)
	rec := httptest.NewRecorder()

	router.ServeHTTP(rec, req)

	assert.Equal(t, http.StatusOK, rec.Code)
	assert.Equal(t, "user-jwt-2", capturedState["user_id"])
	assert.Equal(t, "tenant-jwt-from-claims", capturedState["tenant_id"])
}

func TestOptional_TenantPropagation_InvalidTokenWithHeader(t *testing.T) {
	m := NewJWTMiddlewareWithConfig(testSecret, "", nil, DefaultL1CacheConfig())
	capturedState := make(map[string]interface{})
	router := createOptionalTestRouter(m, &capturedState)

	req := httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/optional-test", nil)
	req.Header.Set("X-Tenant-ID", "tenant-hdr-invalid-token")
	req.Header.Set("Authorization", "Bearer invalid-garbage-token")
	rec := httptest.NewRecorder()

	router.ServeHTTP(rec, req)

	assert.Equal(t, http.StatusOK, rec.Code)
	assert.Nil(t, capturedState["user_id"])
	assert.Nil(t, capturedState["tenant_id"])
}

func TestOptional_TenantPropagation_ExpiredTokenWithHeader(t *testing.T) {
	m := NewJWTMiddlewareWithConfig(testSecret, "", nil, DefaultL1CacheConfig())
	capturedState := make(map[string]interface{})
	router := createOptionalTestRouter(m, &capturedState)

	claims := Claims{
		RegisteredClaims: jwt.RegisteredClaims{
			ExpiresAt: jwt.NewNumericDate(time.Now().Add(-time.Hour)),
			IssuedAt:  jwt.NewNumericDate(time.Now().Add(-2 * time.Hour)),
			ID:        "sess-expired",
		},
		UserID:   "user-expired",
		TenantID: "tenant-expired-claims",
	}
	tokenStr := createValidToken(testSecret, claims)

	req := httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/optional-test", nil)
	req.Header.Set("X-Tenant-ID", "tenant-hdr-expired-token")
	req.Header.Set("Authorization", "Bearer "+tokenStr)
	rec := httptest.NewRecorder()

	router.ServeHTTP(rec, req)

	assert.Equal(t, http.StatusOK, rec.Code)
	assert.Nil(t, capturedState["user_id"])
	assert.Nil(t, capturedState["tenant_id"])
}

func TestOptional_TenantPropagation_ExpiredTokenWithoutHeader(t *testing.T) {
	m := NewJWTMiddlewareWithConfig(testSecret, "", nil, DefaultL1CacheConfig())
	capturedState := make(map[string]interface{})
	router := createOptionalTestRouter(m, &capturedState)

	claims := Claims{
		RegisteredClaims: jwt.RegisteredClaims{
			ExpiresAt: jwt.NewNumericDate(time.Now().Add(-time.Hour)),
			IssuedAt:  jwt.NewNumericDate(time.Now().Add(-2 * time.Hour)),
			ID:        "sess-expired-2",
		},
		UserID:   "user-expired-2",
		TenantID: "tenant-expired-claims-2",
	}
	tokenStr := createValidToken(testSecret, claims)

	req := httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/optional-test", nil)
	req.Header.Set("Authorization", "Bearer "+tokenStr)
	rec := httptest.NewRecorder()

	router.ServeHTTP(rec, req)

	assert.Equal(t, http.StatusOK, rec.Code)
	assert.Nil(t, capturedState["user_id"])
	assert.Nil(t, capturedState["tenant_id"])
}
