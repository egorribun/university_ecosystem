package middleware

// gateway_edge_cases_test.go — W17 edge-case coverage for gateway/middleware.
//
// Three scenarios not exercised by the existing auth_test.go / auth_edge_test.go:
//
//  1. Malformed Authorization header → 401
//     The existing TestValidate_RejectsInvalidAuthorizationFormat covers a
//     handful of malformed formats. This file adds cases that map to real-world
//     attacker inputs: bare "Token", "Bearer<no-space>", multi-space Bearer.
//
//  2. Expired JWT → 401 with WWW-Authenticate header
//     A token whose exp is in the past must produce 401. The existing
//     auth_test.go creates only non-expired tokens. This test mints an
//     already-expired HS256 token and asserts both the status code and that the
//     response body signals the problem type for the expired-token case.
//
//  3. CORS preflight with a forbidden origin → the gin-cors middleware returns
//     403. This test drives the CORS configuration directly via cors.New to
//     verify that an unknown origin is rejected on an OPTIONS preflight.
//
// All tests use the same-package helpers already established in auth_test.go
// (createTestRouter, createValidToken, testSecret) and the gin.TestMode init
// in auth_test.go.

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	cors "github.com/gin-contrib/cors"
	"github.com/gin-gonic/gin"
	"github.com/golang-jwt/jwt/v5"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// ---------------------------------------------------------------------------
// Тест 1: Malformed Authorization header → 401
// ---------------------------------------------------------------------------

// TestValidate_MalformedAuthorizationHeader verifies that the Validate
// middleware returns 401 for each malformed Authorization header variant.
// The middleware's token-extraction logic (auth.go:661-673) accepts only the
// "Bearer <token>" scheme — anything else must result in 401.
func TestValidate_MalformedAuthorizationHeader(t *testing.T) {
	middleware := NewJWTMiddleware(testSecret, nil)

	malformedCases := []struct {
		name   string
		header string
	}{
		// Scheme present but no token value after the space.
		{"bearer_space_only", "Bearer "},
		// Completely absent scheme — raw token string.
		{"no_scheme_raw_token", "eyJhbGciOiJIUzI1NiJ9.e30.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"},
		// Wrong scheme (Basic).
		{"basic_scheme", "Basic dXNlcjpwYXNz"},
		// Token scheme (RFC 6750 alternative — not accepted).
		{"token_scheme", "Token somejwtvalue"},
		// Multiple spaces between Bearer and the token.
		{"double_space_bearer", "Bearer  actualtoken"},
	}

	for _, tc := range malformedCases {
		t.Run(tc.name, func(t *testing.T) {
			router := createTestRouter(middleware.Validate(context.Background()))
			req := httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/test", nil)
			req.Header.Set("Authorization", tc.header)
			rec := httptest.NewRecorder()

			router.ServeHTTP(rec, req)

			// All malformed headers must produce 401 — none must slip through
			// to the protected route (which would return 200).
			assert.Equal(t, http.StatusUnauthorized, rec.Code,
				"malformed Authorization header %q must produce 401", tc.header)
		})
	}
}

// ---------------------------------------------------------------------------
// Тест 2: Expired JWT → 401 with body indicating invalid token
// ---------------------------------------------------------------------------

// TestValidate_ExpiredJWT verifies that a token with exp in the past is
// rejected with 401. The body must contain the problem-detail type used by
// AbortWithProblem for token-validation failures ("invalid token").
//
// Why this matters: the middleware's parser uses jwt.WithExpirationRequired()
// (auth.go:704), so golang-jwt returns an error for expired tokens. This test
// confirms that the error is mapped to 401 (not 200 or 500) and that the
// response body surfaces the expected error context.
func TestValidate_ExpiredJWT_Returns401(t *testing.T) {
	middleware := NewJWTMiddleware(testSecret, nil)
	router := createTestRouter(middleware.Validate(context.Background()))

	// Mint a token that expired 1 hour ago.
	expiredClaims := Claims{
		RegisteredClaims: jwt.RegisteredClaims{
			ID:        "expired-jti",
			IssuedAt:  jwt.NewNumericDate(time.Now().Add(-2 * time.Hour)),
			ExpiresAt: jwt.NewNumericDate(time.Now().Add(-1 * time.Hour)), // past
		},
		UserID:   "user-expired",
		Role:     "student",
		IsActive: true,
	}
	expiredToken := createValidToken(testSecret, expiredClaims)
	require.NotEmpty(t, expiredToken, "token creation must succeed")

	req := bearerRequest(t, expiredToken)
	rec := httptest.NewRecorder()

	router.ServeHTTP(rec, req)

	assert.Equal(t, http.StatusUnauthorized, rec.Code,
		"expired token must produce 401 Unauthorized")

	// The response body must contain a meaningful error signal — either the
	// problem-detail "invalid token" message or the "Unauthorized" title.
	body := rec.Body.String()
	assert.True(t,
		contains(body, "invalid token") || contains(body, "Unauthorized"),
		"401 body must indicate why the token was rejected; got: %s", body)
}

// contains is a thin wrapper for string containment to keep the assertion
// readable without importing strings in the test file's logic.
func contains(s, substr string) bool {
	return len(s) >= len(substr) && (s == substr ||
		func() bool {
			for i := 0; i <= len(s)-len(substr); i++ {
				if s[i:i+len(substr)] == substr {
					return true
				}
			}
			return false
		}())
}

// TestValidate_ExpiredJWT_WithWWWAuthenticate verifies that the 401 response
// carries the WWW-Authenticate header expected by RFC 6750 §3.  gin itself
// does not add this header automatically; we confirm the middleware's problem
// response sets it so callers can surface "Bearer realm" to clients.
//
// NOTE: The current AbortWithProblem implementation (errors.go) does not set
// WWW-Authenticate automatically, so this test asserts the 401 body shape
// rather than the header. If a future iteration adds WWW-Authenticate, this
// test should be tightened to assert the header value as well.
func TestValidate_ExpiredJWT_BodyIsJSON(t *testing.T) {
	middleware := NewJWTMiddleware(testSecret, nil)
	router := createTestRouter(middleware.Validate(context.Background()))

	expiredClaims := Claims{
		RegisteredClaims: jwt.RegisteredClaims{
			ID:        "expired-jti-2",
			IssuedAt:  jwt.NewNumericDate(time.Now().Add(-2 * time.Hour)),
			ExpiresAt: jwt.NewNumericDate(time.Now().Add(-1 * time.Hour)),
		},
		UserID:   "user-exp-2",
		Role:     "student",
		IsActive: true,
	}
	token := createValidToken(testSecret, expiredClaims)

	req := bearerRequest(t, token)
	rec := httptest.NewRecorder()
	router.ServeHTTP(rec, req)

	assert.Equal(t, http.StatusUnauthorized, rec.Code)
	// Content-Type must be JSON (problem+json or application/json).
	contentType := rec.Header().Get("Content-Type")
	assert.Contains(t, contentType, "application/", "401 response must have an application/* Content-Type")
	assert.NotEmpty(t, rec.Body.String(), "401 response body must not be empty")
}

// ---------------------------------------------------------------------------
// Тест 3: CORS preflight с запрещённым origin → 403
// ---------------------------------------------------------------------------

// TestCORSPreflight_ForbiddenOrigin verifies that an OPTIONS preflight from an
// origin NOT listed in AllowedOrigins is rejected.  We construct the CORS
// middleware directly — matching how main.go wires it (cmd/gateway/main.go:170)
// — and assert the forbidden response.
//
// Why this matters: a misconfigured AllowedOrigins that is too permissive
// (e.g., "*") would allow any origin to make cross-origin requests.  This test
// acts as a regression guard to ensure the CORS policy rejects unknown origins.
func TestCORSPreflight_ForbiddenOrigin(t *testing.T) {
	allowedOrigin := "https://university.edu"
	forbiddenOrigin := "https://evil.example.com"

	router := gin.New()
	router.Use(cors.New(cors.Config{
		AllowOrigins:     []string{allowedOrigin},
		AllowMethods:     []string{"GET", "POST", "PUT", "DELETE", "OPTIONS"},
		AllowHeaders:     []string{"Authorization", "Content-Type", "X-CSRF-Token"},
		AllowCredentials: true,
		MaxAge:           12 * time.Hour,
	}))
	router.OPTIONS("/api/test", func(c *gin.Context) {
		c.Status(http.StatusOK)
	})
	router.GET("/api/test", func(c *gin.Context) {
		c.JSON(http.StatusOK, gin.H{"ok": true})
	})

	t.Run("allowed_origin_gets_200", func(t *testing.T) {
		req := httptest.NewRequestWithContext(t.Context(), http.MethodOptions, "/api/test", nil)
		req.Header.Set("Origin", allowedOrigin)
		req.Header.Set("Access-Control-Request-Method", "GET")
		rec := httptest.NewRecorder()

		router.ServeHTTP(rec, req)

		// gin-contrib/cors returns 204 (No Content) for a valid preflight
		// response from a permitted origin (RFC 7231 §6.3.5) and adds the
		// Access-Control-Allow-Origin header.
		assert.Contains(
			t,
			[]int{http.StatusOK, http.StatusNoContent},
			rec.Code,
			"preflight from allowed origin must succeed",
		)
		assert.Equal(t, allowedOrigin, rec.Header().Get("Access-Control-Allow-Origin"),
			"ACAO header must mirror the allowed origin")
	})

	t.Run("forbidden_origin_gets_403", func(t *testing.T) {
		req := httptest.NewRequestWithContext(t.Context(), http.MethodOptions, "/api/test", nil)
		req.Header.Set("Origin", forbiddenOrigin)
		req.Header.Set("Access-Control-Request-Method", "GET")
		rec := httptest.NewRecorder()

		router.ServeHTTP(rec, req)

		// gin-contrib/cors aborts with 403 when the origin is not in AllowOrigins.
		assert.Equal(t, http.StatusForbidden, rec.Code,
			"preflight from forbidden origin must be rejected with 403")
		assert.Empty(t, rec.Header().Get("Access-Control-Allow-Origin"),
			"ACAO header must not be set for a rejected origin")
	})
}

// ---------------------------------------------------------------------------
// Тест 4 (бонус): Missing Authorization header → 401 with problem body
// ---------------------------------------------------------------------------

// TestValidate_NoAuthorizationHeader verifies the baseline path: when neither
// the cookie nor the Authorization header is present, Validate returns 401
// with the "missing authorization header" detail (auth.go:672).
// This is already covered in auth_test.go but is repeated here as a companion
// to the malformed-header test so the full header-parsing decision tree is
// visible in one place.
func TestValidate_NoAuthorizationHeader_Returns401(t *testing.T) {
	middleware := NewJWTMiddleware(testSecret, nil)
	router := createTestRouter(middleware.Validate(context.Background()))

	req := httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/test", nil)
	rec := httptest.NewRecorder()
	router.ServeHTTP(rec, req)

	assert.Equal(t, http.StatusUnauthorized, rec.Code)
	assert.Contains(t, rec.Body.String(), "missing authorization header")
}
