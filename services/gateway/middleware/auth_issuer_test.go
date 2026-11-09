package middleware

import (
	"context"
	"crypto/rsa"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/golang-jwt/jwt/v5"
	"github.com/stretchr/testify/require"
)

func issuerTestClaims(issuer, jti string) Claims {
	return Claims{
		RegisteredClaims: jwt.RegisteredClaims{
			Issuer:    issuer,
			Audience:  jwt.ClaimStrings{DefaultJWTAudience},
			ExpiresAt: jwt.NewNumericDate(time.Now().Add(time.Hour)),
			IssuedAt:  jwt.NewNumericDate(time.Now()),
			ID:        jti,
		},
		UserID:   "issuer-test-user",
		Role:     "student",
		IsActive: true,
	}
}

func TestNewJWTMiddlewareWithConfigAndIssuerRejectsInvalidSettings(t *testing.T) {
	for _, testCase := range []struct {
		name     string
		audience string
		issuer   string
		want     string
	}{
		{name: "blank audience", issuer: DefaultJWTIssuer, want: "JWT audience must not be blank"},
		{name: "blank issuer", audience: DefaultJWTAudience, issuer: " \t ", want: "JWT issuer must not be blank"},
		{name: "control character issuer", audience: DefaultJWTAudience, issuer: "trusted\nissuer", want: "JWT issuer contains invalid characters"},
		{name: "overlong issuer", audience: DefaultJWTAudience, issuer: strings.Repeat("a", 513), want: "JWT issuer contains invalid characters"},
	} {
		t.Run(testCase.name, func(t *testing.T) {
			defer func() {
				recovered := recover()
				require.NotNil(t, recovered, "invalid middleware configuration must fail at construction")
				require.Contains(t, recovered.(string), testCase.want)
			}()
			NewJWTMiddlewareWithConfigAndIssuer(testSecret, "", newUnrevokedRedisClient(t), DefaultL1CacheConfig(), testCase.audience, testCase.issuer)
		})
	}
}

func TestValidate_RejectsMissingAndForeignIssuer(t *testing.T) {
	privateKey, publicPEM := rsaTestKeys(t)
	middleware := NewJWTMiddlewareWithConfig(testSecret, publicPEM, newUnrevokedRedisClient(t), DefaultL1CacheConfig())
	router := createTestRouter(middleware.Validate(context.Background()))

	for _, testCase := range []struct {
		name   string
		issuer string
		want   int
	}{
		{name: "configured issuer", issuer: DefaultJWTIssuer, want: http.StatusOK},
		{name: "missing issuer", issuer: "", want: http.StatusUnauthorized},
		{name: "foreign issuer", issuer: "https://foreign.example", want: http.StatusUnauthorized},
	} {
		t.Run(testCase.name, func(t *testing.T) {
			token := jwt.NewWithClaims(jwt.SigningMethodRS256, issuerTestClaims(testCase.issuer, "validate-"+testCase.name))
			tokenString, err := token.SignedString(privateKey)
			require.NoError(t, err)

			request := httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/test", nil)
			request.Header.Set("Authorization", "Bearer "+tokenString)
			recorder := httptest.NewRecorder()
			router.ServeHTTP(recorder, request)

			require.Equal(t, testCase.want, recorder.Code)
		})
	}
}

func TestValidate_AcceptsOldAndNewRSAKeysWithConfiguredIssuer(t *testing.T) {
	oldPrivateKey, _ := rsaTestKeys(t)
	newPrivateKey, newPublicPEM := rsaTestKeys(t)
	const configuredIssuer = "https://api.example"
	middleware := NewJWTMiddlewareWithConfigAndIssuer(testSecret, newPublicPEM, newUnrevokedRedisClient(t), DefaultL1CacheConfig(), DefaultJWTAudience, configuredIssuer)
	middleware.storeRSAKeys(rsaKeySet{
		"old": &oldPrivateKey.PublicKey,
		"new": &newPrivateKey.PublicKey,
	})
	router := createTestRouter(middleware.Validate(context.Background()))

	for _, testCase := range []struct {
		kid        string
		privateKey *rsa.PrivateKey
	}{{kid: "old", privateKey: oldPrivateKey}, {kid: "new", privateKey: newPrivateKey}} {
		t.Run(testCase.kid, func(t *testing.T) {
			token := jwt.NewWithClaims(jwt.SigningMethodRS256, issuerTestClaims(configuredIssuer, "rotation-"+testCase.kid))
			token.Header["kid"] = testCase.kid
			tokenString, err := token.SignedString(testCase.privateKey)
			require.NoError(t, err)

			request := httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/test", nil)
			request.Header.Set("Authorization", "Bearer "+tokenString)
			recorder := httptest.NewRecorder()
			router.ServeHTTP(recorder, request)

			require.Equal(t, http.StatusOK, recorder.Code)
		})
	}
}

func TestOptional_IssuerNegativeControlsRemainUnauthenticated(t *testing.T) {
	privateKey, publicPEM := rsaTestKeys(t)
	middleware := NewJWTMiddlewareWithConfig(testSecret, publicPEM, newUnrevokedRedisClient(t), DefaultL1CacheConfig())
	var authenticated bool
	router := gin.New()
	router.GET("/test", middleware.Optional(context.Background()), func(c *gin.Context) {
		_, authenticated = c.Get("user_id")
		c.Status(http.StatusOK)
	})

	for _, testCase := range []struct {
		name     string
		issuer   string
		wantAuth bool
	}{
		{name: "configured issuer", issuer: DefaultJWTIssuer, wantAuth: true},
		{name: "missing issuer", issuer: "", wantAuth: false},
		{name: "foreign issuer", issuer: "https://foreign.example", wantAuth: false},
	} {
		t.Run(testCase.name, func(t *testing.T) {
			token := jwt.NewWithClaims(jwt.SigningMethodRS256, issuerTestClaims(testCase.issuer, "optional-"+testCase.name))
			tokenString, err := token.SignedString(privateKey)
			require.NoError(t, err)

			request := httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/test", nil)
			request.Header.Set("Authorization", "Bearer "+tokenString)
			recorder := httptest.NewRecorder()
			authenticated = false
			router.ServeHTTP(recorder, request)

			require.Equal(t, http.StatusOK, recorder.Code)
			require.Equal(t, testCase.wantAuth, authenticated)
		})
	}
}
