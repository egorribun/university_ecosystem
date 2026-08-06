package middleware

import (
	"context"
	"net/http"
	"net/http/httptest"
	"net/http/httputil"
	"net/url"
	"testing"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/golang-jwt/jwt/v5"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"github.com/university-ecosystem/gateway/internal/handlers"
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
	m := NewJWTMiddleware(testSecret, nil)
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
	m := NewJWTMiddleware(testSecret, nil)
	capturedState := make(map[string]interface{})
	router := createOptionalTestRouter(m, &capturedState)

	req := httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/optional-test", nil)
	req.Header.Set("X-Tenant-ID", "tenant-hdr-100")
	rec := httptest.NewRecorder()

	router.ServeHTTP(rec, req)

	assert.Equal(t, http.StatusOK, rec.Code)
	assert.Nil(t, capturedState["user_id"])
	assert.Equal(t, "tenant-hdr-100", capturedState["tenant_id"])
}

func TestOptional_TenantPropagation_TokenOnlyNoHeader(t *testing.T) {
	m := NewJWTMiddleware(testSecret, nil)
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
	m := NewJWTMiddleware(testSecret, nil)
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
	m := NewJWTMiddleware(testSecret, nil)
	capturedState := make(map[string]interface{})
	router := createOptionalTestRouter(m, &capturedState)

	req := httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/optional-test", nil)
	req.Header.Set("X-Tenant-ID", "tenant-hdr-invalid-token")
	req.Header.Set("Authorization", "Bearer invalid-garbage-token")
	rec := httptest.NewRecorder()

	router.ServeHTTP(rec, req)

	assert.Equal(t, http.StatusOK, rec.Code)
	assert.Nil(t, capturedState["user_id"])
	assert.Equal(t, "tenant-hdr-invalid-token", capturedState["tenant_id"])
}

func TestOptional_TenantPropagation_ExpiredTokenWithHeader(t *testing.T) {
	m := NewJWTMiddleware(testSecret, nil)
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
	assert.Equal(t, "tenant-hdr-expired-token", capturedState["tenant_id"])
}

func TestOptional_TenantPropagation_ExpiredTokenWithoutHeader(t *testing.T) {
	m := NewJWTMiddleware(testSecret, nil)
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

func TestOptional_ProxyHandler_Integration(t *testing.T) {
	m := NewJWTMiddleware(testSecret, nil)
	internalSecret := []byte("test-internal-secret-32-bytes-long!")

	var forwardedHeaders http.Header

	backendServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		forwardedHeaders = r.Header.Clone()
		w.WriteHeader(http.StatusOK)
	}))
	defer backendServer.Close()

	targetURL, err := url.Parse(backendServer.URL)
	require.NoError(t, err)
	proxy := httputil.NewSingleHostReverseProxy(targetURL)

	router := gin.New()
	router.GET("/proxy-test", m.Optional(context.Background()), handlers.ProxyHandler(proxy, internalSecret))

	t.Run("token only sets X-Tenant-ID and HMAC signature downstream", func(t *testing.T) {
		forwardedHeaders = nil
		claims := Claims{
			RegisteredClaims: jwt.RegisteredClaims{
				ExpiresAt: jwt.NewNumericDate(time.Now().Add(time.Hour)),
				IssuedAt:  jwt.NewNumericDate(time.Now()),
				ID:        "sess-proxy-1",
			},
			UserID:   "user-proxy-1",
			Role:     "student",
			IsActive: true,
			TenantID: "tenant-from-jwt-claim",
		}
		tokenStr := createValidToken(testSecret, claims)

		req := httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/proxy-test", nil)
		req.Header.Set("Authorization", "Bearer "+tokenStr)
		req.Header.Set("X-Tenant-ID", "forged-client-tenant-header")
		rec := httptest.NewRecorder()

		router.ServeHTTP(rec, req)

		assert.Equal(t, http.StatusOK, rec.Code)
		assert.Equal(t, "user-proxy-1", forwardedHeaders.Get("X-User-ID"))
		assert.Equal(t, "sess-proxy-1", forwardedHeaders.Get("X-Session-ID"))
		assert.Equal(t, "tenant-from-jwt-claim", forwardedHeaders.Get("X-Tenant-ID"))
		assert.NotEmpty(t, forwardedHeaders.Get("X-Internal-Signature"))
	})

	t.Run("unauthenticated request with header forwards X-Tenant-ID without signature", func(t *testing.T) {
		forwardedHeaders = nil

		req := httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/proxy-test", nil)
		req.Header.Set("X-Tenant-ID", "tenant-anon-client")
		rec := httptest.NewRecorder()

		router.ServeHTTP(rec, req)

		assert.Equal(t, http.StatusOK, rec.Code)
		assert.Empty(t, forwardedHeaders.Get("X-User-ID"))
		assert.Empty(t, forwardedHeaders.Get("X-Session-ID"))
		assert.Equal(t, "tenant-anon-client", forwardedHeaders.Get("X-Tenant-ID"))
		assert.Empty(t, forwardedHeaders.Get("X-Internal-Signature"))
	})
}
