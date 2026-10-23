package config

import (
	"strings"
	"testing"

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

func TestLoad_JWTIssuerMatchesPythonStripSemantics(t *testing.T) {
	t.Setenv("JWT_SECRET", "private-test-secret")
	t.Setenv("VITE_ENVIRONMENT", "development")

	astral512 := strings.Repeat("😀", 512)
	astral513 := strings.Repeat("😀", 513)
	cases := []struct {
		name      string
		issuer    string
		want      string
		wantError bool
	}{
		{name: "file separator is stripped", issuer: "\x1cissuer\x1c", want: "issuer"},
		{name: "group separator is stripped", issuer: "\x1dissuer\x1d", want: "issuer"},
		{name: "record separator is stripped", issuer: "\x1eissuer\x1e", want: "issuer"},
		{name: "unit separator is stripped", issuer: "\x1fissuer\x1f", want: "issuer"},
		{name: "next line is stripped", issuer: "\u0085issuer\u0085", want: "issuer"},
		{name: "BOM is preserved", issuer: "\ufeffissuer\ufeff", want: "\ufeffissuer\ufeff"},
		{name: "512 astral code points accepted", issuer: astral512, want: astral512},
		{name: "513 astral code points rejected", issuer: astral513, wantError: true},
		{name: "embedded C0 rejected", issuer: "issuer\x1cinside", wantError: true},
		{name: "blank after Python strip rejected", issuer: "\x1c\x1f\u0085", wantError: true},
	}

	for _, testCase := range cases {
		t.Run(testCase.name, func(t *testing.T) {
			t.Setenv("JWT_ISSUER", testCase.issuer)
			cfg, err := Load()
			if testCase.wantError {
				require.ErrorContains(t, err, "JWT_ISSUER")
				require.Nil(t, cfg)
				return
			}
			require.NoError(t, err)
			require.Equal(t, testCase.want, cfg.JWTIssuer)
		})
	}
}
