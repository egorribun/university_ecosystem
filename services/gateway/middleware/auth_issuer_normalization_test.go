package middleware

import (
	"context"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/golang-jwt/jwt/v5"
	"github.com/stretchr/testify/require"
)

func TestTrimJWTIssuerWhitespaceMatchesPythonStripSet(t *testing.T) {
	pythonStripWhitespace := []rune{
		'\u0009', '\u000a', '\u000b', '\u000c', '\u000d',
		'\u001c', '\u001d', '\u001e', '\u001f', '\u0020',
		'\u0085', '\u00a0', '\u1680',
		'\u2000', '\u2001', '\u2002', '\u2003', '\u2004', '\u2005',
		'\u2006', '\u2007', '\u2008', '\u2009', '\u200a',
		'\u2028', '\u2029', '\u202f', '\u205f', '\u3000',
	}
	for _, whitespace := range pythonStripWhitespace {
		input := string(whitespace) + "issuer" + string(whitespace)
		require.Equal(t, "issuer", trimJWTIssuerWhitespace(input), "U+%04X", whitespace)
	}
	require.Equal(t, "\ufeffissuer\ufeff", trimJWTIssuerWhitespace("\ufeffissuer\ufeff"))
}

func TestValidate_JWTIssuerNormalizationMatchesPythonForRealTokens(t *testing.T) {
	privateKey, publicPEM := rsaTestKeys(t)
	astral512 := strings.Repeat("😀", 512)
	cases := []struct {
		name           string
		configured     string
		canonicalClaim string
	}{
		{name: "file separator edges", configured: "\x1cissuer\x1c", canonicalClaim: "issuer"},
		{name: "group separator edges", configured: "\x1dissuer\x1d", canonicalClaim: "issuer"},
		{name: "record separator edges", configured: "\x1eissuer\x1e", canonicalClaim: "issuer"},
		{name: "unit separator edges", configured: "\x1fissuer\x1f", canonicalClaim: "issuer"},
		{name: "next line edges", configured: "\u0085issuer\u0085", canonicalClaim: "issuer"},
		{name: "BOM edges preserved", configured: "\ufeffissuer\ufeff", canonicalClaim: "\ufeffissuer\ufeff"},
		{name: "512 astral code points", configured: astral512, canonicalClaim: astral512},
	}

	for _, testCase := range cases {
		t.Run(testCase.name, func(t *testing.T) {
			middleware := NewJWTMiddlewareWithConfigAndIssuer(testSecret, publicPEM, newUnrevokedRedisClient(t), DefaultL1CacheConfig(), DefaultJWTAudience, testCase.configured)
			router := createTestRouter(middleware.Validate(context.Background()))
			token := jwt.NewWithClaims(jwt.SigningMethodRS256, issuerTestClaims(testCase.canonicalClaim, "normalized-"+testCase.name))
			tokenString, err := token.SignedString(privateKey)
			require.NoError(t, err)

			request := httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/test", nil)
			request.Header.Set("Authorization", "Bearer "+tokenString)
			recorder := httptest.NewRecorder()
			router.ServeHTTP(recorder, request)
			require.Equal(t, http.StatusOK, recorder.Code)
		})
	}
}

func TestNewJWTMiddlewareWithConfigAndIssuerRejectsPythonNormalizedInvalidValues(t *testing.T) {
	cases := []struct {
		name   string
		issuer string
		want   string
	}{
		{name: "blank after strip", issuer: "\x1c\x1f\u0085", want: "JWT issuer must not be blank"},
		{name: "embedded C0", issuer: "issuer\x1cinside", want: "JWT issuer contains invalid characters"},
		{name: "513 astral code points", issuer: strings.Repeat("😀", 513), want: "JWT issuer contains invalid characters"},
	}
	for _, testCase := range cases {
		t.Run(testCase.name, func(t *testing.T) {
			require.PanicsWithValue(t, "gateway: "+testCase.want, func() {
				NewJWTMiddlewareWithConfigAndIssuer(testSecret, "", newUnrevokedRedisClient(t), DefaultL1CacheConfig(), DefaultJWTAudience, testCase.issuer)
			})
		})
	}
}
