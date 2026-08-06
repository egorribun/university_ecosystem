package middleware

import (
	"context"
	"crypto/rand"
	"crypto/rsa"
	"crypto/x509"
	"encoding/base64"
	"encoding/json"
	"encoding/pem"
	"fmt"
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

	request := httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/test", nil)
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
			request := httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/test", nil)
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

	request := httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/test", nil)
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

	request := httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/test", nil)
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

	request := httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/test", nil)
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

	request := httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/test", nil)
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

	request := httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/test", nil)
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

	request := httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/test", nil)
	request.Header.Set("Authorization", "Bearer "+token)
	recorder := httptest.NewRecorder()

	router.ServeHTTP(recorder, request)

	assert.Equal(t, http.StatusOK, recorder.Code)
	assert.Equal(t, "optional-user", capturedUserID)
}

func TestRequireRole_RejectsWhenRoleNotInContext(t *testing.T) {
	router := gin.New()
	router.GET("/test", RequireRole("admin"))

	request := httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/test", nil)
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

	request := httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/test", nil)
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

	request := httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/test", nil)
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

func TestNewJWTMiddlewareWithConfig_PanicsOnInvalidRSAPubKey(t *testing.T) {
	assert.Panics(t, func() {
		NewJWTMiddlewareWithConfig("secret", "invalid-pem-data", nil, DefaultL1CacheConfig())
	})
}

func TestValidate_AcceptsRS256Token(t *testing.T) {
	privateKey, err := rsa.GenerateKey(rand.Reader, 2048)
	require.NoError(t, err)

	pubASN1, err := x509.MarshalPKIXPublicKey(&privateKey.PublicKey)
	require.NoError(t, err)
	pubBytes := pem.EncodeToMemory(&pem.Block{
		Type:  "PUBLIC KEY",
		Bytes: pubASN1,
	})

	m := NewJWTMiddlewareWithConfig("secret", string(pubBytes), nil, DefaultL1CacheConfig())
	router := createTestRouter(m.Validate(context.Background()))

	claims := Claims{
		RegisteredClaims: jwt.RegisteredClaims{
			ExpiresAt: jwt.NewNumericDate(time.Now().Add(time.Hour)),
			IssuedAt:  jwt.NewNumericDate(time.Now()),
			ID:        "session-123",
		},
		UserID:   "user-123",
		IsActive: true,
	}

	token := jwt.NewWithClaims(jwt.SigningMethodRS256, claims)
	tokenString, err := token.SignedString(privateKey)
	require.NoError(t, err)

	request := httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/test", nil)
	request.Header.Set("Authorization", "Bearer "+tokenString)
	recorder := httptest.NewRecorder()

	router.ServeHTTP(recorder, request)

	assert.Equal(t, http.StatusOK, recorder.Code)
}

func TestValidate_RejectsHS256TokenWhenRS256Configured(t *testing.T) {
	privateKey, err := rsa.GenerateKey(rand.Reader, 2048)
	require.NoError(t, err)

	pubASN1, err := x509.MarshalPKIXPublicKey(&privateKey.PublicKey)
	require.NoError(t, err)
	pubBytes := pem.EncodeToMemory(&pem.Block{
		Type:  "PUBLIC KEY",
		Bytes: pubASN1,
	})

	m := NewJWTMiddlewareWithConfig("secret", string(pubBytes), nil, DefaultL1CacheConfig())
	router := createTestRouter(m.Validate(context.Background()))

	claims := Claims{
		RegisteredClaims: jwt.RegisteredClaims{
			ExpiresAt: jwt.NewNumericDate(time.Now().Add(time.Hour)),
			IssuedAt:  jwt.NewNumericDate(time.Now()),
			ID:        "session-123",
		},
		UserID:   "user-123",
		IsActive: true,
	}

	token := jwt.NewWithClaims(jwt.SigningMethodHS256, claims)
	tokenString, err := token.SignedString([]byte("secret"))
	require.NoError(t, err)

	request := httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/test", nil)
	request.Header.Set("Authorization", "Bearer "+tokenString)
	recorder := httptest.NewRecorder()

	router.ServeHTTP(recorder, request)

	assert.Equal(t, http.StatusUnauthorized, recorder.Code)
}

func TestValidate_RejectsRS256TokenWhenHS256Configured(t *testing.T) {
	privateKey, err := rsa.GenerateKey(rand.Reader, 2048)
	require.NoError(t, err)

	m := NewJWTMiddleware("secret", nil)
	router := createTestRouter(m.Validate(context.Background()))

	claims := Claims{
		RegisteredClaims: jwt.RegisteredClaims{
			ExpiresAt: jwt.NewNumericDate(time.Now().Add(time.Hour)),
			IssuedAt:  jwt.NewNumericDate(time.Now()),
			ID:        "session-123",
		},
		UserID:   "user-123",
		IsActive: true,
	}

	token := jwt.NewWithClaims(jwt.SigningMethodRS256, claims)
	tokenString, err := token.SignedString(privateKey)
	require.NoError(t, err)

	request := httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/test", nil)
	request.Header.Set("Authorization", "Bearer "+tokenString)
	recorder := httptest.NewRecorder()

	router.ServeHTTP(recorder, request)

	assert.Equal(t, http.StatusUnauthorized, recorder.Code)
}

func TestExtractAlgFromHeader(t *testing.T) {
	t.Run("valid RS256 token", func(t *testing.T) {
		tokenString := "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiYWRtaW4iOnRydWV9.signature" //nolint:gosec // G101 JWT header/payload test fixture, not a real credential // pragma: allowlist secret
		alg, err := extractAlgFromHeader(tokenString)
		require.NoError(t, err)
		assert.Equal(t, "RS256", alg)
	})

	t.Run("missing alg", func(t *testing.T) {
		tokenString := "eyJ0eXAiOiJKV1QifQ.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiYWRtaW4iOnRydWV9.signature" //nolint:gosec // G101 JWT header/payload test fixture, not a real credential // pragma: allowlist secret
		_, err := extractAlgFromHeader(tokenString)
		require.Error(t, err)
	})

	t.Run("malformed base64", func(t *testing.T) {
		tokenString := "invalid!!!.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiYWRtaW4iOnRydWV9.signature" //nolint:gosec // G101: malformed JWT test fixture, not a real credential
		_, err := extractAlgFromHeader(tokenString)
		require.Error(t, err)
	})
}

func TestValidateIAT(t *testing.T) {
	t.Run("missing iat", func(t *testing.T) {
		claims := &Claims{}
		err := validateIAT(claims)
		require.Error(t, err)
		assert.Contains(t, err.Error(), "missing iat claim")
	})

	t.Run("future iat", func(t *testing.T) {
		claims := &Claims{
			RegisteredClaims: jwt.RegisteredClaims{
				IssuedAt: jwt.NewNumericDate(time.Now().Add(10 * time.Minute)),
			},
		}
		err := validateIAT(claims)
		require.Error(t, err)
		assert.Contains(t, err.Error(), "issued in the future")
	})

	t.Run("too old iat", func(t *testing.T) {
		claims := &Claims{
			RegisteredClaims: jwt.RegisteredClaims{
				IssuedAt: jwt.NewNumericDate(time.Now().Add(-25 * time.Hour)),
			},
		}
		err := validateIAT(claims)
		require.Error(t, err)
		assert.Contains(t, err.Error(), "is too old")
	})
}

func TestJWKSRefresher(t *testing.T) {
	privateKey, err := rsa.GenerateKey(rand.Reader, 2048)
	require.NoError(t, err)

	nB64 := base64.RawURLEncoding.EncodeToString(privateKey.N.Bytes())
	eB64 := base64.RawURLEncoding.EncodeToString([]byte{1, 0, 1})

	jwks := struct {
		Keys []map[string]string `json:"keys"`
	}{
		Keys: []map[string]string{
			{
				"kty": "RSA",
				"n":   nB64,
				"e":   eB64,
			},
		},
	}

	jwksBytes, err := json.Marshal(jwks)
	require.NoError(t, err)

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write(jwksBytes) //nolint:errcheck // test JWKS handler; write to httptest server cannot fail
	}))
	defer server.Close()

	m := NewJWTMiddleware("secret", nil)
	assert.Nil(t, m.rsaPublicKey.Load())

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	m.StartJWKSRefresher(ctx, server.URL, 50*time.Millisecond, slog.Default())

	time.Sleep(150 * time.Millisecond)

	assert.NotNil(t, m.rsaPublicKey.Load())
}

func TestJWTMiddleware_CheckL1Cache(t *testing.T) {
	m := NewJWTMiddleware(testSecret, nil)

	t.Run("miss when key absent", func(t *testing.T) {
		exists, found := m.checkL1Cache("absent-key")
		assert.False(t, found)
		assert.False(t, exists)
	})

	t.Run("hit for a far-from-expiry entry", func(t *testing.T) {
		// XFetch refreshes when `remaining < threshold`. A far-future storedAt makes
		// `remaining` enormous so the probabilistic refresh never fires → the hit
		// branch (l1Hits + return entry.exists,true) is exercised deterministically.
		// (A now-fresh entry has a ~37% refresh probability with beta=1.0 → flaky.)
		m.l1cache.Add("hit-key", cacheEntry{exists: true, storedAt: time.Now().Add(1000 * time.Hour)})
		exists, found := m.checkL1Cache("hit-key")
		assert.True(t, found)
		assert.True(t, exists)
	})

	t.Run("probabilistic refresh reports a miss for a stale entry", func(t *testing.T) {
		// storedAt far past the L1 TTL → XFetch deterministically refreshes →
		// checkL1Cache returns (false, false) so the caller revalidates via Redis.
		m.l1cache.Add("stale-key", cacheEntry{exists: true, storedAt: time.Now().Add(-time.Hour)})
		exists, found := m.checkL1Cache("stale-key")
		assert.False(t, found)
		assert.False(t, exists)
	})
}

func TestValidate_TenantSpoofingDefense(t *testing.T) {
	middleware := NewJWTMiddleware(testSecret, nil)

	var capturedTenantID interface{}
	router := gin.New()
	router.GET("/test-tenant-defense", middleware.Validate(context.Background()), func(c *gin.Context) {
		capturedTenantID, _ = c.Get("tenant_id")
		c.Status(http.StatusOK)
	})

	t.Run("claims.TenantID takes precedence over client header", func(t *testing.T) {
		claims := Claims{
			RegisteredClaims: jwt.RegisteredClaims{
				ExpiresAt: jwt.NewNumericDate(time.Now().Add(time.Hour)),
				IssuedAt:  jwt.NewNumericDate(time.Now()),
				ID:        "session-valid-tenant",
			},
			UserID:   "user-legit",
			Role:     "student",
			IsActive: true,
			TenantID: "tenant-legit-from-claims",
		}
		token := createValidToken(testSecret, claims)

		request := httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/test-tenant-defense", nil)
		request.Header.Set("Authorization", "Bearer "+token)
		request.Header.Set("X-Tenant-ID", "tenant-spoofed-by-client")
		recorder := httptest.NewRecorder()

		router.ServeHTTP(recorder, request)

		assert.Equal(t, http.StatusOK, recorder.Code)
		assert.Equal(t, "tenant-legit-from-claims", capturedTenantID)
	})

	t.Run("client header used when claims.TenantID is empty", func(t *testing.T) {
		claims := Claims{
			RegisteredClaims: jwt.RegisteredClaims{
				ExpiresAt: jwt.NewNumericDate(time.Now().Add(time.Hour)),
				IssuedAt:  jwt.NewNumericDate(time.Now()),
				ID:        "session-empty-tenant",
			},
			UserID:   "user-no-tenant",
			Role:     "student",
			IsActive: true,
			TenantID: "",
		}
		token := createValidToken(testSecret, claims)

		request := httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/test-tenant-defense", nil)
		request.Header.Set("Authorization", "Bearer "+token)
		request.Header.Set("X-Tenant-ID", "tenant-fallback-header")
		recorder := httptest.NewRecorder()

		router.ServeHTTP(recorder, request)

		assert.Equal(t, http.StatusOK, recorder.Code)
		assert.Equal(t, "tenant-fallback-header", capturedTenantID)
	})
}
