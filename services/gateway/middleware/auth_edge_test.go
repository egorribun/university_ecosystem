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
	"strconv"
	"testing"
	"time"

	"github.com/alicebob/miniredis/v2"
	"github.com/gin-gonic/gin"
	"github.com/golang-jwt/jwt/v5"
	"github.com/redis/go-redis/v9"
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
	if len(claims.Audience) == 0 {
		claims.Audience = jwt.ClaimStrings{DefaultJWTAudience}
	}
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
	router.ServeHTTP(rec, bearerRequest(t, hs))

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
	router.ServeHTTP(rec, bearerRequest(t, "garbage-not-a-jwt"))

	assert.Equal(t, http.StatusOK, rec.Code)
	_, hasUser := (*captured)["user_id"]
	assert.False(t, hasUser, "malformed token → unauthenticated")
}

func TestOptional_RS256Configured_ValidTokenSetsContext(t *testing.T) {
	priv, pubPEM := rsaTestKeys(t)
	m := NewJWTMiddlewareWithConfig(testSecret, pubPEM, newUnrevokedRedisClient(t), DefaultL1CacheConfig())

	probe, captured := captureContextHandler()
	router := gin.New()
	router.GET("/test", m.Optional(context.Background()), probe)

	token := signRS256(t, priv, freshClaims("jti-ok"))
	rec := httptest.NewRecorder()
	router.ServeHTTP(rec, bearerRequest(t, token))

	assert.Equal(t, http.StatusOK, rec.Code)
	assert.Equal(t, "user-edge", (*captured)["user_id"], "valid RS256 token sets user context")
}

func TestOptional_NoTokenContinues(t *testing.T) {
	m := NewJWTMiddleware(testSecret, nil)
	probe, captured := captureContextHandler()
	router := gin.New()
	router.GET("/test", m.Optional(context.Background()), probe)

	rec := httptest.NewRecorder()
	router.ServeHTTP(rec, httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/test", nil))

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
	router.ServeHTTP(rec, bearerRequest(t, token))

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
	router.ServeHTTP(rec, bearerRequest(t, token))

	assert.Equal(t, http.StatusOK, rec.Code)
	assert.Equal(t, "user-1", (*captured)["user_id"])
}

func TestOptional_RejectsOverageIssuedToken(t *testing.T) {
	m := NewJWTMiddleware(testSecret, nil)
	claims := freshClaims("jti-too-old")
	claims.IssuedAt = jwt.NewNumericDate(time.Now().Add(-jwtMaxTokenAge - time.Hour))
	token := createValidToken(testSecret, claims)

	probe, captured := captureContextHandler()
	router := gin.New()
	router.GET("/test", m.Optional(context.Background()), probe)
	rec := httptest.NewRecorder()
	router.ServeHTTP(rec, bearerRequest(t, token))

	assert.Equal(t, http.StatusOK, rec.Code)
	_, authenticated := (*captured)["user_id"]
	assert.False(t, authenticated)
}

func TestValidate_RejectsNonClaimsParserResult(t *testing.T) {
	oldParse := parseJWTClaimsFunc
	t.Cleanup(func() { parseJWTClaimsFunc = oldParse })
	parseJWTClaimsFunc = func(*jwt.Parser, string, jwt.Claims, jwt.Keyfunc) (*jwt.Token, error) {
		return &jwt.Token{Claims: &jwt.RegisteredClaims{}, Valid: true}, nil
	}

	m := NewJWTMiddleware(testSecret, nil)
	router := gin.New()
	router.GET("/test", m.Validate(context.Background()), func(c *gin.Context) { c.Status(http.StatusOK) })
	rec := httptest.NewRecorder()
	router.ServeHTTP(rec, bearerRequest(t, "synthetic"))

	assert.Equal(t, http.StatusUnauthorized, rec.Code)
}

func TestOptional_RejectsNonClaimsParserResult(t *testing.T) {
	oldParse := parseJWTClaimsFunc
	t.Cleanup(func() { parseJWTClaimsFunc = oldParse })
	parseJWTClaimsFunc = func(*jwt.Parser, string, jwt.Claims, jwt.Keyfunc) (*jwt.Token, error) {
		return &jwt.Token{Claims: &jwt.RegisteredClaims{}, Valid: true}, nil
	}

	m := NewJWTMiddleware(testSecret, nil)
	probe, captured := captureContextHandler()
	router := gin.New()
	router.GET("/test", m.Optional(context.Background()), probe)
	rec := httptest.NewRecorder()
	router.ServeHTTP(rec, bearerRequest(t, "synthetic"))

	assert.Equal(t, http.StatusOK, rec.Code)
	_, authenticated := (*captured)["user_id"]
	assert.False(t, authenticated)
}

func TestOptional_VerifySessionDecisionBranches(t *testing.T) {
	oldVerify := verifySessionFunc
	t.Cleanup(func() { verifySessionFunc = oldVerify })

	cases := []struct {
		name       string
		valid      bool
		deny       bool
		err        error
		wantStatus int
		wantUser   bool
	}{
		{name: "session invalid", valid: false, wantStatus: http.StatusOK},
		{name: "redis error but valid", valid: true, err: assert.AnError, wantStatus: http.StatusOK, wantUser: true},
		{name: "service unavailable", deny: true, err: assert.AnError, wantStatus: http.StatusServiceUnavailable},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			verifySessionFunc = func(*JWTMiddleware, context.Context, string, bool) (bool, bool, error) {
				return tc.valid, tc.deny, tc.err
			}
			m := NewJWTMiddleware(testSecret, nil)
			probe, captured := captureContextHandler()
			router := gin.New()
			router.GET("/test", m.Optional(context.Background()), probe)
			token := createValidToken(testSecret, freshClaims("jti-decision"))
			rec := httptest.NewRecorder()
			router.ServeHTTP(rec, bearerRequest(t, token))

			assert.Equal(t, tc.wantStatus, rec.Code)
			_, authenticated := (*captured)["user_id"]
			assert.Equal(t, tc.wantUser, authenticated)
		})
	}
}

func TestVerifySession_UsesRevocationL1Cache(t *testing.T) {
	oldRand := xfetchRandFunc
	t.Cleanup(func() { xfetchRandFunc = oldRand })
	xfetchRandFunc = func() float64 { return 1 }
	url, stop := startMockRedis(t, mockRedisConfig{existsReply: ":0\r\n"})
	defer stop()
	m := newRedisMiddleware(t, url)
	m.l1cache.Add("revoked:jti:cached", cacheEntry{exists: true, storedAt: time.Now()})

	isValid, shouldDeny, err := m.verifySession(context.Background(), "cached", true)
	assert.False(t, isValid)
	assert.False(t, shouldDeny)
	assert.NoError(t, err)
}

func TestShouldRefreshProbabilistic_ZeroRandomFactorIsSafe(t *testing.T) {
	oldRand := xfetchRandFunc
	t.Cleanup(func() { xfetchRandFunc = oldRand })
	xfetchRandFunc = func() float64 { return 0 }

	assert.True(t, shouldRefreshProbabilistic(time.Now(), time.Minute, 1))
}

func TestValidate_RejectsTokenWithExpiredIssuedAt(t *testing.T) {
	m := NewJWTMiddleware(testSecret, nil)
	router := createTestRouter(m.Validate(context.Background()))
	claims := revocableClaims("jti-expired-iat")
	claims.IssuedAt = jwt.NewNumericDate(time.Now().Add(-jwtMaxTokenAge - time.Minute))
	token := createValidToken(testSecret, claims)

	recorder := httptest.NewRecorder()
	router.ServeHTTP(recorder, bearerRequest(t, token))

	assert.Equal(t, http.StatusUnauthorized, recorder.Code)
	assert.Contains(t, recorder.Body.String(), "too old")
}

func TestWarmL1CacheStopsAtMaximumKeyLimit(t *testing.T) {
	mr := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	t.Cleanup(func() { _ = client.Close() }) //nolint:errcheck // test cleanup

	for i := 0; i < 10000; i++ {
		require.NoError(t, mr.Set("revoked:jti:warm-"+strconv.Itoa(i), "1"))
	}

	m := NewJWTMiddleware(testSecret, client)
	m.WarmL1Cache(context.Background())
	assert.Equal(t, 10000, m.l1cache.Len())
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
