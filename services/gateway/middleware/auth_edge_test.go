package middleware

// Coverage tests (testing session 10) for auth.go edge paths the prior sessions
// left uncovered: extractAlgFromHeader error arms, the Optional() RS256 +
// algorithm-downgrade branches, the Optional() valid-RS256 and revoked-session
// paths, and StartJWKSRefresher's equal-key (no-rotation) branch.
//
// Reuses the same-package helpers from auth_test.go (createTestRouter,
// createValidToken, testSecret) and auth_redis_test.go (startMockRedis,
// newRedisMiddleware, revocableClaims, bearerRequest).
//
// NOTE: keyFunc's default (unexpected-algorithm) branch is effectively
// unreachable through the public API — the jwt parser's WithValidMethods
// allowlist rejects any non-RS256/HS256 token BEFORE keyFunc runs — so it is
// not chased here (observation only).

import (
	"context"
	"crypto/rand"
	"crypto/rsa"
	"crypto/x509"
	"encoding/pem"
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

// rsaTestKeys generates an RSA keypair and returns the private key plus its
// PKIX PEM public encoding (the form NewJWTMiddlewareWithConfig expects).
func rsaTestKeys(t *testing.T) (*rsa.PrivateKey, string) {
	t.Helper()
	priv, err := rsa.GenerateKey(rand.Reader, 2048)
	require.NoError(t, err)
	pubASN1, err := x509.MarshalPKIXPublicKey(&priv.PublicKey)
	require.NoError(t, err)
	pubPEM := pem.EncodeToMemory(&pem.Block{Type: "PUBLIC KEY", Bytes: pubASN1})
	return priv, string(pubPEM)
}

func signRS256(t *testing.T, priv *rsa.PrivateKey, claims Claims) string {
	t.Helper()
	tok := jwt.NewWithClaims(jwt.SigningMethodRS256, claims)
	s, err := tok.SignedString(priv)
	require.NoError(t, err)
	return s
}

func freshClaims(jti string) Claims {
	return Claims{
		RegisteredClaims: jwt.RegisteredClaims{
			ID:        jti,
			IssuedAt:  jwt.NewNumericDate(time.Now().Add(-1 * time.Minute)),
			ExpiresAt: jwt.NewNumericDate(time.Now().Add(time.Hour)),
		},
		UserID:   "user-edge",
		Role:     "student",
		IsActive: true,
	}
}

// ---------------------------------------------------------------------------
// extractAlgFromHeader — directly callable error arms
// ---------------------------------------------------------------------------

func TestExtractAlgFromHeader_ErrorArms(t *testing.T) {
	t.Run("not three parts", func(t *testing.T) {
		_, err := extractAlgFromHeader("only.two")
		require.Error(t, err)
		assert.Contains(t, err.Error(), "expected 3 dot-separated parts")
	})
	t.Run("bad base64 header", func(t *testing.T) {
		_, err := extractAlgFromHeader("!!!notbase64!!!.payload.sig")
		require.Error(t, err)
		assert.Contains(t, err.Error(), "base64")
	})
	t.Run("bad json header", func(t *testing.T) {
		// base64url("not json") — decodes fine, fails json.Unmarshal.
		_, err := extractAlgFromHeader("bm90IGpzb24.payload.sig")
		require.Error(t, err)
		assert.Contains(t, err.Error(), "json")
	})
	t.Run("missing alg field", func(t *testing.T) {
		// base64url("{}") = "e30".
		_, err := extractAlgFromHeader("e30.payload.sig")
		require.Error(t, err)
		assert.Contains(t, err.Error(), "missing 'alg'")
	})
	t.Run("valid RS256 header", func(t *testing.T) {
		// base64url(`{"alg":"RS256"}`).
		alg, err := extractAlgFromHeader("eyJhbGciOiJSUzI1NiJ9.payload.sig")
		require.NoError(t, err)
		assert.Equal(t, "RS256", alg)
	})
}

// ---------------------------------------------------------------------------
// Optional() — RS256-configured branches
// ---------------------------------------------------------------------------

func captureContextHandler() (gin.HandlerFunc, *map[string]any) {
	captured := map[string]any{}
	return func(c *gin.Context) {
		if v, ok := c.Get("user_id"); ok {
			captured["user_id"] = v
		}
		c.Status(http.StatusOK)
	}, &captured
}

func TestOptional_RS256Configured_RejectsHS256Downgrade(t *testing.T) {
	_, pubPEM := rsaTestKeys(t)
	m := NewJWTMiddlewareWithConfig(testSecret, pubPEM, nil, DefaultL1CacheConfig())

	probe, captured := captureContextHandler()
	router := gin.New()
	router.GET("/test", m.Optional(context.Background()), probe)

	// A well-formed HS256 token — a downgrade attempt under RS256 config.
	hs := createValidToken(testSecret, freshClaims("jti-hs"))
	rec := httptest.NewRecorder()
	router.ServeHTTP(rec, bearerRequest(hs))

	assert.Equal(t, http.StatusOK, rec.Code, "optional auth continues")
	_, hasUser := (*captured)["user_id"]
	assert.False(t, hasUser, "downgrade attempt must stay unauthenticated")
}

func TestOptional_RS256Configured_MalformedHeaderUnauthenticated(t *testing.T) {
	_, pubPEM := rsaTestKeys(t)
	m := NewJWTMiddlewareWithConfig(testSecret, pubPEM, nil, DefaultL1CacheConfig())

	probe, captured := captureContextHandler()
	router := gin.New()
	router.GET("/test", m.Optional(context.Background()), probe)

	rec := httptest.NewRecorder()
	router.ServeHTTP(rec, bearerRequest("garbage-not-a-jwt"))

	assert.Equal(t, http.StatusOK, rec.Code)
	_, hasUser := (*captured)["user_id"]
	assert.False(t, hasUser, "malformed token → unauthenticated")
}

func TestOptional_RS256Configured_ValidTokenSetsContext(t *testing.T) {
	priv, pubPEM := rsaTestKeys(t)
	// nil redis → verifySession early-returns valid (m.redis == nil guard).
	m := NewJWTMiddlewareWithConfig(testSecret, pubPEM, nil, DefaultL1CacheConfig())

	probe, captured := captureContextHandler()
	router := gin.New()
	router.GET("/test", m.Optional(context.Background()), probe)

	token := signRS256(t, priv, freshClaims("jti-ok"))
	rec := httptest.NewRecorder()
	router.ServeHTTP(rec, bearerRequest(token))

	assert.Equal(t, http.StatusOK, rec.Code)
	assert.Equal(t, "user-edge", (*captured)["user_id"], "valid RS256 token sets user context")
}

func TestOptional_NoTokenContinues(t *testing.T) {
	m := NewJWTMiddleware(testSecret, nil)
	probe, captured := captureContextHandler()
	router := gin.New()
	router.GET("/test", m.Optional(context.Background()), probe)

	rec := httptest.NewRecorder()
	router.ServeHTTP(rec, httptest.NewRequest(http.MethodGet, "/test", nil))

	assert.Equal(t, http.StatusOK, rec.Code)
	_, hasUser := (*captured)["user_id"]
	assert.False(t, hasUser)
}

func TestOptional_RevokedSessionContinuesUnauthenticatedHS256(t *testing.T) {
	// Redis says the jti IS revoked → verifySession reports invalid →
	// Optional continues without user context (the !isValid arm).
	url, stop := startMockRedis(t, mockRedisConfig{existsReply: ":1\r\n"})
	defer stop()
	m := newRedisMiddleware(t, url) // HS256, redis-backed

	probe, captured := captureContextHandler()
	router := gin.New()
	router.GET("/test", m.Optional(context.Background()), probe)

	token := createValidToken(testSecret, revocableClaims("jti-revoked"))
	rec := httptest.NewRecorder()
	router.ServeHTTP(rec, bearerRequest(token))

	assert.Equal(t, http.StatusOK, rec.Code)
	_, hasUser := (*captured)["user_id"]
	assert.False(t, hasUser, "revoked session → unauthenticated, request still proceeds")
}

func TestOptional_ValidSessionSetsContextHS256(t *testing.T) {
	url, stop := startMockRedis(t, mockRedisConfig{existsReply: ":0\r\n"})
	defer stop()
	m := newRedisMiddleware(t, url)

	probe, captured := captureContextHandler()
	router := gin.New()
	router.GET("/test", m.Optional(context.Background()), probe)

	token := createValidToken(testSecret, revocableClaims("jti-live"))
	rec := httptest.NewRecorder()
	router.ServeHTTP(rec, bearerRequest(token))

	assert.Equal(t, http.StatusOK, rec.Code)
	assert.Equal(t, "user-1", (*captured)["user_id"])
}

// ---------------------------------------------------------------------------
// StartJWKSRefresher — equal-key (no-rotation) branch
// ---------------------------------------------------------------------------

func TestStartJWKSRefresher_EqualKeyNoRotation(t *testing.T) {
	_, pubPEM := rsaTestKeys(t)
	// JWKS endpoint that always returns the SAME PEM → the refresher should
	// detect the unchanged key and NOT count a rotation on the periodic poll.
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		_, _ = w.Write([]byte(pubPEM)) //nolint:errcheck // test server best-effort
	}))
	defer srv.Close()

	m := NewJWTMiddlewareWithConfig(testSecret, pubPEM, nil, DefaultL1CacheConfig())
	ctx, cancel := context.WithCancel(context.Background())
	// StartJWKSRefresher dereferences its logger arg (no nil-guard), so pass a
	// real discard logger. Very short interval so a couple of polls happen.
	logger := slog.New(slog.NewTextHandler(io.Discard, nil))
	go m.StartJWKSRefresher(ctx, srv.URL, 20*time.Millisecond, logger)
	time.Sleep(80 * time.Millisecond)
	cancel()

	// The key is still loaded and usable (equal-key poll didn't clobber it).
	assert.NotNil(t, m.rsaPublicKey.Load(), "public key remains loaded after equal-key polls")
}
