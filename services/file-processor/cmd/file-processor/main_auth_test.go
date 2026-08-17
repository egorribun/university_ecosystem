package main

// Coverage tests (testing session 9) for the pure auth helpers in main.go:
// parseRSAPublicKey, jwtKeyFunc (FIX-ALG-01 algorithm-confusion guards),
// httpJWTMiddleware (incl. the FIX-ALG-02 downgrade pre-check), authFunc
// (gRPC metadata path) and the setupGRPCServer smoke.
//
// ⛔ setupGraphQLServer is deliberately NOT called (os.ReadFile of
// schema.graphql relative to cwd + os.Exit(1) on failure); connectTemporal /
// startNatsSubscriber / runServers need live infrastructure.

import (
	"context"
	"crypto/ecdsa"
	"crypto/elliptic"
	"crypto/rand"
	"crypto/rsa"
	"crypto/x509"
	"encoding/pem"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"os"
	"testing"

	"github.com/golang-jwt/jwt/v5"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"github.com/university-ecosystem/file-processor/internal/config"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/metadata"
	"google.golang.org/grpc/status"
)

func testLogger() *slog.Logger {
	return slog.New(slog.NewTextHandler(os.Stdout, &slog.HandlerOptions{Level: slog.LevelError}))
}

func generateRSAKey(t *testing.T) *rsa.PrivateKey {
	t.Helper()
	key, err := rsa.GenerateKey(rand.Reader, 2048)
	require.NoError(t, err)
	return key
}

func rsaPublicPEM(t *testing.T, pub *rsa.PublicKey) string {
	t.Helper()
	der, err := x509.MarshalPKIXPublicKey(pub)
	require.NoError(t, err)
	return string(pem.EncodeToMemory(&pem.Block{Type: "PUBLIC KEY", Bytes: der}))
}

func signedToken(t *testing.T, method jwt.SigningMethod, key any, claims jwt.MapClaims) string {
	t.Helper()
	token := jwt.NewWithClaims(method, claims)
	signed, err := token.SignedString(key)
	require.NoError(t, err)
	return signed
}

// ---------------------------------------------------------------------------
// parseRSAPublicKey
// ---------------------------------------------------------------------------

func TestParseRSAPublicKey_Valid(t *testing.T) {
	key := generateRSAKey(t)
	pub, err := parseRSAPublicKey(rsaPublicPEM(t, &key.PublicKey))
	require.NoError(t, err)
	assert.Equal(t, key.N, pub.N)
}

func TestParseRSAPublicKey_Errors(t *testing.T) {
	t.Run("no PEM block", func(t *testing.T) {
		_, err := parseRSAPublicKey("not a pem at all")
		require.Error(t, err)
		assert.Contains(t, err.Error(), "no PEM block")
	})

	t.Run("garbage DER", func(t *testing.T) {
		garbage := string(pem.EncodeToMemory(&pem.Block{Type: "PUBLIC KEY", Bytes: []byte("junk")}))
		_, err := parseRSAPublicKey(garbage)
		require.Error(t, err)
		assert.Contains(t, err.Error(), "failed to parse")
	})

	t.Run("non-RSA key", func(t *testing.T) {
		ecKey, err := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
		require.NoError(t, err)
		der, err := x509.MarshalPKIXPublicKey(&ecKey.PublicKey)
		require.NoError(t, err)
		ecPEM := string(pem.EncodeToMemory(&pem.Block{Type: "PUBLIC KEY", Bytes: der}))
		_, err = parseRSAPublicKey(ecPEM)
		require.Error(t, err)
		assert.Contains(t, err.Error(), "not an RSA key")
	})
}

// ---------------------------------------------------------------------------
// jwtKeyFunc — FIX-ALG-01 algorithm matrix
// ---------------------------------------------------------------------------

func TestJWTKeyFunc_AlgorithmMatrix(t *testing.T) {
	rsaKey := generateRSAKey(t)

	t.Run("RS256 with key configured returns key", func(t *testing.T) {
		fn := jwtKeyFunc("", &rsaKey.PublicKey)
		got, err := fn(jwt.New(jwt.SigningMethodRS256))
		require.NoError(t, err)
		assert.Equal(t, &rsaKey.PublicKey, got)
	})

	t.Run("RS256 without key errors", func(t *testing.T) {
		fn := jwtKeyFunc("secret", nil) // pragma: allowlist secret
		_, err := fn(jwt.New(jwt.SigningMethodRS256))
		require.Error(t, err)
		assert.Contains(t, err.Error(), "no RSA public key configured")
	})

	t.Run("HS256 rejected when RS256 configured (FIX-ALG-01)", func(t *testing.T) {
		fn := jwtKeyFunc("secret", &rsaKey.PublicKey) // pragma: allowlist secret
		_, err := fn(jwt.New(jwt.SigningMethodHS256))
		require.Error(t, err)
		assert.Contains(t, err.Error(), "HS256 token rejected")
	})

	t.Run("HS256 without secret errors", func(t *testing.T) {
		fn := jwtKeyFunc("", nil)
		_, err := fn(jwt.New(jwt.SigningMethodHS256))
		require.Error(t, err)
		assert.Contains(t, err.Error(), "no JWT secret configured")
	})

	t.Run("HS256 with secret returns secret bytes", func(t *testing.T) {
		fn := jwtKeyFunc("hmac-secret", nil) // pragma: allowlist secret
		got, err := fn(jwt.New(jwt.SigningMethodHS256))
		require.NoError(t, err)
		assert.Equal(t, []byte("hmac-secret"), got)
	})

	t.Run("unexpected method rejected", func(t *testing.T) {
		fn := jwtKeyFunc("secret", nil) // pragma: allowlist secret
		_, err := fn(jwt.New(jwt.SigningMethodES256))
		require.Error(t, err)
		assert.Contains(t, err.Error(), "unexpected signing method")
	})
}

// ---------------------------------------------------------------------------
// httpJWTMiddleware
// ---------------------------------------------------------------------------

func runMiddleware(t *testing.T, secret string, rsaPub *rsa.PublicKey, authHeader string) (*httptest.ResponseRecorder, *string) {
	t.Helper()
	var capturedSub *string
	next := http.HandlerFunc(func(_ http.ResponseWriter, r *http.Request) {
		if sub, ok := r.Context().Value(userIDKey).(string); ok {
			capturedSub = &sub
		}
	})
	handler := httpJWTMiddleware(secret, rsaPub, testLogger(), next)
	req := httptest.NewRequestWithContext(t.Context(), http.MethodPost, "/graphql", nil)
	if authHeader != "" {
		req.Header.Set("Authorization", authHeader)
	}
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)
	return rec, capturedSub
}

func TestHTTPJWTMiddleware_MissingOrMalformedHeader(t *testing.T) {
	rec, _ := runMiddleware(t, "secret", nil, "")
	assert.Equal(t, http.StatusUnauthorized, rec.Code)

	rec, _ = runMiddleware(t, "secret", nil, "Token abc")
	assert.Equal(t, http.StatusUnauthorized, rec.Code)
}

func TestHTTPJWTMiddleware_DowngradeRejectedWhenRS256Configured(t *testing.T) {
	rsaKey := generateRSAKey(t)
	hs := signedToken(t, jwt.SigningMethodHS256, []byte("secret"), jwt.MapClaims{"sub": "u"})
	rec, _ := runMiddleware(t, "secret", &rsaKey.PublicKey, "Bearer "+hs)
	assert.Equal(t, http.StatusUnauthorized, rec.Code)
}

func TestHTTPJWTMiddleware_ValidRS256SetsUserContext(t *testing.T) {
	rsaKey := generateRSAKey(t)
	rs := signedToken(t, jwt.SigningMethodRS256, rsaKey, jwt.MapClaims{"sub": "user-42"})
	rec, sub := runMiddleware(t, "", &rsaKey.PublicKey, "Bearer "+rs)
	assert.Equal(t, http.StatusOK, rec.Code)
	require.NotNil(t, sub)
	assert.Equal(t, "user-42", *sub)
}

func TestHTTPJWTMiddleware_ValidHS256WhenNoRSA(t *testing.T) {
	hs := signedToken(t, jwt.SigningMethodHS256, []byte("hmac-secret"), jwt.MapClaims{"sub": "user-h"})
	rec, sub := runMiddleware(t, "hmac-secret", nil, "Bearer "+hs)
	assert.Equal(t, http.StatusOK, rec.Code)
	require.NotNil(t, sub)
	assert.Equal(t, "user-h", *sub)
}

func TestHTTPJWTMiddleware_InvalidSignatureRejected(t *testing.T) {
	hs := signedToken(t, jwt.SigningMethodHS256, []byte("wrong-secret"), jwt.MapClaims{"sub": "u"})
	rec, _ := runMiddleware(t, "right-secret", nil, "Bearer "+hs)
	assert.Equal(t, http.StatusUnauthorized, rec.Code)
}

func TestHTTPJWTMiddleware_NonMapClaimsAreRejected(t *testing.T) {
	oldParseJWT := parseJWTFunc
	t.Cleanup(func() { parseJWTFunc = oldParseJWT })
	parseJWTFunc = func(string, jwt.Keyfunc, ...jwt.ParserOption) (*jwt.Token, error) {
		return &jwt.Token{Claims: &jwt.RegisteredClaims{}, Valid: true}, nil
	}

	rec, _ := runMiddleware(t, "test-secret", nil, "Bearer synthetic")
	assert.Equal(t, http.StatusUnauthorized, rec.Code)
}

// Synthetic tenant claims specify the trust rule for a future authoritative
// issuer. The current Python login issuer intentionally emits no tenant scope.
func TestHTTPJWTMiddleware_TenantContextUsesSignedClaimOnly(t *testing.T) {
	token := signedToken(t, jwt.SigningMethodHS256, []byte("hmac-secret"), jwt.MapClaims{
		"sub":       "tenant-user",
		"tenant_id": "claim-tenant",
	})

	for _, tc := range []struct {
		name       string
		header     string
		wantTenant string
	}{
		{name: "forged header cannot override claim", header: "header-tenant", wantTenant: "claim-tenant"},
		{name: "claim is used without header", wantTenant: "claim-tenant"},
	} {
		t.Run(tc.name, func(t *testing.T) {
			var tenant string
			next := http.HandlerFunc(func(_ http.ResponseWriter, r *http.Request) {
				tenant, _ = r.Context().Value(tenantIDKey).(string)
			})
			handler := httpJWTMiddleware("hmac-secret", nil, testLogger(), next)
			req := httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/graphql", nil)
			if tc.header != "" {
				req.Header.Set("X-Tenant-ID", tc.header)
			}
			req.Header.Set("Authorization", "Bearer "+token)
			rec := httptest.NewRecorder()

			handler.ServeHTTP(rec, req)
			assert.Equal(t, http.StatusOK, rec.Code)
			assert.Equal(t, tc.wantTenant, tenant)
		})
	}

	t.Run("forged header without claim is ignored", func(t *testing.T) {
		claimlessToken := signedToken(
			t,
			jwt.SigningMethodHS256,
			[]byte("hmac-secret"),
			jwt.MapClaims{"sub": "tenant-user"},
		)
		var tenant string
		next := http.HandlerFunc(func(_ http.ResponseWriter, r *http.Request) {
			tenant, _ = r.Context().Value(tenantIDKey).(string)
		})
		handler := httpJWTMiddleware("hmac-secret", nil, testLogger(), next)
		req := httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/graphql", nil)
		req.Header.Set("Authorization", "Bearer "+claimlessToken)
		req.Header.Set("X-Tenant-ID", "forged-header-tenant")
		rec := httptest.NewRecorder()

		handler.ServeHTTP(rec, req)
		assert.Equal(t, http.StatusOK, rec.Code)
		assert.Empty(t, tenant)
	})
}

// ---------------------------------------------------------------------------
// authFunc — gRPC metadata path
// ---------------------------------------------------------------------------

func metadataCtx(token string) context.Context {
	md := metadata.Pairs("authorization", "Bearer "+token)
	return metadata.NewIncomingContext(context.Background(), md)
}

func TestAuthFunc_ValidTokenPutsSubInContext(t *testing.T) {
	fn := authFunc("grpc-secret", nil, testLogger()) // pragma: allowlist secret
	token := signedToken(t, jwt.SigningMethodHS256, []byte("grpc-secret"), jwt.MapClaims{"sub": "grpc-user"})

	ctx, err := fn(metadataCtx(token))
	require.NoError(t, err)
	assert.Equal(t, "grpc-user", ctx.Value(userIDKey))
}

// As above, this exercises verifier behavior, not current token minting.
func TestAuthFunc_TenantContextUsesSignedClaimOnly(t *testing.T) {
	fn := authFunc("grpc-secret", nil, testLogger()) // pragma: allowlist secret
	token := signedToken(t, jwt.SigningMethodHS256, []byte("grpc-secret"), jwt.MapClaims{
		"sub":       "grpc-tenant-user",
		"tenant_id": "claim-tenant",
	})

	withMetadata, err := fn(metadata.NewIncomingContext(
		context.Background(),
		metadata.Pairs(
			"authorization", "Bearer "+token,
			"x-tenant-id", "metadata-tenant",
		),
	))
	require.NoError(t, err)
	assert.Equal(t, "claim-tenant", withMetadata.Value(tenantIDKey))

	claimOnly, err := fn(metadataCtx(token))
	require.NoError(t, err)
	assert.Equal(t, "claim-tenant", claimOnly.Value(tenantIDKey))

	claimlessToken := signedToken(
		t,
		jwt.SigningMethodHS256,
		[]byte("grpc-secret"),
		jwt.MapClaims{"sub": "grpc-tenant-user"},
	)
	claimless, err := fn(metadata.NewIncomingContext(
		context.Background(),
		metadata.Pairs(
			"authorization", "Bearer "+claimlessToken,
			"x-tenant-id", "forged-metadata-tenant",
		),
	))
	require.NoError(t, err)
	assert.Nil(t, claimless.Value(tenantIDKey))
}

func TestAuthFunc_InvalidTokenUnauthenticated(t *testing.T) {
	fn := authFunc("grpc-secret", nil, testLogger()) // pragma: allowlist secret
	token := signedToken(t, jwt.SigningMethodHS256, []byte("other-secret"), jwt.MapClaims{"sub": "x"})

	_, err := fn(metadataCtx(token))
	require.Error(t, err)
	assert.Equal(t, codes.Unauthenticated, status.Code(err))
}

func TestAuthFunc_MissingSubRejected(t *testing.T) {
	fn := authFunc("grpc-secret", nil, testLogger()) // pragma: allowlist secret
	token := signedToken(t, jwt.SigningMethodHS256, []byte("grpc-secret"), jwt.MapClaims{"role": "nobody"})

	_, err := fn(metadataCtx(token))
	require.Error(t, err)
	assert.Equal(t, codes.Unauthenticated, status.Code(err))
}

func TestAuthFunc_NonMapClaimsAreRejected(t *testing.T) {
	oldParseJWT := parseJWTFunc
	t.Cleanup(func() { parseJWTFunc = oldParseJWT })
	parseJWTFunc = func(string, jwt.Keyfunc, ...jwt.ParserOption) (*jwt.Token, error) {
		return &jwt.Token{Claims: &jwt.RegisteredClaims{}, Valid: true}, nil
	}

	_, err := authFunc("test-secret", nil, testLogger())(metadataCtx("synthetic"))
	require.Error(t, err)
	assert.Equal(t, codes.Unauthenticated, status.Code(err))
}

func TestAuthFunc_MissingMetadataErrors(t *testing.T) {
	fn := authFunc("grpc-secret", nil, testLogger()) // pragma: allowlist secret
	_, err := fn(context.Background())
	require.Error(t, err)
}

// ---------------------------------------------------------------------------
// setupGRPCServer smoke — registers services without binding a listener
// ---------------------------------------------------------------------------

func TestSetupGRPCServer_BuildsServer(t *testing.T) {
	cfg := &config.Config{JWTSecret: "smoke-secret"} // pragma: allowlist secret
	srv, err := setupGRPCServer(context.Background(), cfg, nil, nil, testLogger())
	require.NoError(t, err)
	require.NotNil(t, srv)
	info := srv.GetServiceInfo()
	assert.Contains(t, info, "grpc.health.v1.Health")
	srv.Stop()
}
