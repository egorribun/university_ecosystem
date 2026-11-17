package middleware_test

import (
	"context"
	"net/http"
	"net/http/httptest"
	"net/http/httputil"
	"net/url"
	"strings"
	"testing"
	"time"

	"github.com/alicebob/miniredis/v2"
	"github.com/gin-gonic/gin"
	"github.com/golang-jwt/jwt/v5"
	"github.com/redis/go-redis/v9"
	"github.com/stretchr/testify/require"
	"github.com/university-ecosystem/gateway/internal/handlers"
	gatewaymiddleware "github.com/university-ecosystem/gateway/middleware"
)

const identityBoundarySecret = "test-secret-key-for-testing-purposes"

// Use public middleware construction: this cross-layer test must not become
// part of the middleware package that handlers itself imports.
func newIdentityBoundaryMiddleware(t *testing.T) *gatewaymiddleware.JWTMiddleware {
	t.Helper()
	server := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{Addr: server.Addr()})
	t.Cleanup(func() { require.NoError(t, client.Close()) })
	require.NoError(t, client.Ping(t.Context()).Err())
	return gatewaymiddleware.NewJWTMiddlewareWithConfig(
		identityBoundarySecret, "", client, gatewaymiddleware.DefaultL1CacheConfig(),
	)
}

func identityBoundaryRequest(t *testing.T, token string) *http.Request {
	t.Helper()
	request := httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/test", nil)
	request.Header.Set("Authorization", "Bearer "+token)
	return request
}

func identityBoundaryToken(t *testing.T, subject, tokenID string) string {
	t.Helper()
	claims := jwt.MapClaims{
		"iss":       gatewaymiddleware.DefaultJWTIssuer,
		"aud":       gatewaymiddleware.DefaultJWTAudience,
		"exp":       time.Now().Add(time.Hour).Unix(),
		"iat":       time.Now().Add(-time.Minute).Unix(),
		"jti":       tokenID,
		"sub":       subject,
		"is_active": true,
		"role":      "student",
	}
	token, err := jwt.NewWithClaims(jwt.SigningMethodHS256, claims).SignedString([]byte(identityBoundarySecret))
	require.NoError(t, err)
	return token
}

func TestValidate_RejectsWhitespaceOnlySubject(t *testing.T) {
	middleware := newIdentityBoundaryMiddleware(t)
	router := gin.New()
	router.GET("/test", middleware.Validate(context.Background()), func(c *gin.Context) {
		c.Status(http.StatusNoContent)
	})

	recorder := httptest.NewRecorder()
	router.ServeHTTP(recorder, identityBoundaryRequest(t, identityBoundaryToken(t, " \t ", "blank-subject-required")))

	require.Equal(t, http.StatusUnauthorized, recorder.Code)
}

func TestOptional_DoesNotSignBlankSubjectOrTamperedTokenForBackend(t *testing.T) {
	var forwarded http.Header
	backend := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		forwarded = r.Header.Clone()
		w.WriteHeader(http.StatusOK)
	}))
	defer backend.Close()

	target, err := url.Parse(backend.URL)
	require.NoError(t, err)
	proxy := httputil.NewSingleHostReverseProxy(target)
	middleware := newIdentityBoundaryMiddleware(t)
	router := gin.New()
	router.GET("/test", middleware.Optional(context.Background()), handlers.ProxyHandler(proxy, []byte("synthetic-internal-hmac-key")))

	validToken := identityBoundaryToken(t, "synthetic-user", "tampered-signature-optional")
	parts := strings.Split(validToken, ".")
	require.Len(t, parts, 3)
	if strings.HasPrefix(parts[2], "A") {
		parts[2] = "B" + parts[2][1:]
	} else {
		parts[2] = "A" + parts[2][1:]
	}
	tamperedToken := strings.Join(parts, ".")

	for _, tc := range []struct {
		name  string
		token string
	}{
		{name: "blank subject", token: identityBoundaryToken(t, " \t ", "blank-subject-optional")},
		{name: "tampered signature", token: tamperedToken},
	} {
		t.Run(tc.name, func(t *testing.T) {
			forwarded = nil
			request := httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/test", nil)
			request.Header.Set("Authorization", "Bearer "+tc.token)
			request.Header.Set("X-User-ID", "forged-user")
			request.Header.Set("X-Session-ID", "forged-session")
			request.Header.Set("X-Tenant-ID", "forged-tenant")
			request.Header.Set("X-Internal-Signature", "forged-signature")
			recorder := httptest.NewRecorder()

			router.ServeHTTP(recorder, request)

			require.Equal(t, http.StatusOK, recorder.Code)
			require.NotNil(t, forwarded)
			for _, header := range []string{"X-User-ID", "X-Session-ID", "X-Tenant-ID", "X-Internal-Signature"} {
				require.Empty(t, forwarded.Get(header), "%s must not be forwarded for an unauthenticated optional principal", header)
			}
		})
	}
}
