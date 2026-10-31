package spiffe

import (
	"bytes"
	"crypto/rand"
	"crypto/rsa"
	"encoding/base64"
	"encoding/json"
	"strings"
	"testing"

	"github.com/go-jose/go-jose/v4"
	"github.com/spiffe/go-spiffe/v2/bundle/jwtbundle"
	"github.com/spiffe/go-spiffe/v2/spiffeid"
)

func TestGoJoseRSAJWKModulusBoundary(t *testing.T) {
	td, err := spiffeid.TrustDomainFromString("example.org")
	if err != nil {
		t.Fatal("invalid fixed test trust domain")
	}
	const keyID = "rsa-modulus-boundary"
	for _, test := range []struct {
		name   string
		bits   int
		reject bool
	}{
		{name: "4096-bit-public-key", bits: 4096},
		{name: "4097-bit-public-key", bits: 4097, reject: true},
	} {
		t.Run(test.name, func(t *testing.T) {
			// Public parser input only: no private parameters or key generation.
			modulus := make([]byte, (test.bits+7)/8)
			modulus[0] = byte(1 << uint((test.bits-1)%8))
			modulus[len(modulus)-1] |= 1
			jwks, err := json.Marshal(map[string]any{
				"keys": []map[string]string{{
					"kid": keyID,
					"kty": "RSA",
					"n":   base64.RawURLEncoding.EncodeToString(modulus),
					"e":   "AQAB",
				}},
			})
			if err != nil || len(jwks) > 1024 {
				t.Fatal("invalid bounded public JWKS fixture")
			}

			bundle, err := jwtbundle.Parse(td, jwks)
			if test.reject {
				if err == nil || bundle != nil {
					t.Fatal("accepted public RSA JWK beyond the 4096-bit modulus limit")
				}
				if !strings.Contains(err.Error(), "modulus too large") {
					t.Fatal("oversized public RSA JWK failed outside the modulus bound")
				}
				return
			}
			if err != nil || bundle == nil {
				t.Fatal("rejected public RSA JWK at the 4096-bit modulus limit")
			}
			if bundle.TrustDomain() != td || len(bundle.JWTAuthorities()) != 1 {
				t.Fatal("public JWT bundle identity or authority count changed")
			}
			authority, found := bundle.FindJWTAuthority(keyID)
			public, ok := authority.(*rsa.PublicKey)
			if !found || !ok || public == nil || public.N == nil || public.E != 65537 ||
				public.N.BitLen() != test.bits || !bytes.Equal(public.N.Bytes(), modulus) {
				t.Fatal("public RSA authority did not preserve the bounded modulus and exponent")
			}
		})
	}
}

// These controls characterize the locked dependency, not a production JWT ingress.
func TestGoJoseOrdinaryRSACompactRoundTrip(t *testing.T) {
	key := newGoJoseCompatibilityKey(t)
	bundle, err := parseGoJoseCompatibilityJWK(t, goJoseCompatibilityJWK(&key.PublicKey))
	if err != nil || bundle == nil {
		t.Fatal("rejected ordinary public RSA JWKS")
	}
	if bundle.TrustDomain().String() != "example.org" || len(bundle.JWTAuthorities()) != 1 {
		t.Fatal("ordinary public JWT bundle identity or authority count changed")
	}
	authority, found := bundle.FindJWTAuthority("rsa-compatibility")
	public, ok := authority.(*rsa.PublicKey)
	if !found || !ok || public == nil || public.N == nil || public.E != 65537 ||
		public.N.BitLen() != 2048 || !public.Equal(&key.PublicKey) {
		t.Fatal("ordinary public RSA authority changed")
	}

	payload := []byte("bounded go-jose compatibility payload")
	compact := signGoJoseCompatibilityPayload(t, key, payload)
	parsed, err := jose.ParseSignedCompact(compact, []jose.SignatureAlgorithm{jose.RS256})
	if err != nil || parsed == nil {
		t.Fatal("rejected ordinary RS256 compact JWS")
	}
	verified, err := parsed.Verify(public)
	if err != nil || !bytes.Equal(verified, payload) {
		t.Fatal("ordinary RS256 compact JWS did not verify the exact payload")
	}
	assertGoJoseTamperedSignatureRejected(t, compact, public)
}

func TestGoJoseJWS32SignatureBoundary(t *testing.T) {
	key := newGoJoseCompatibilityKey(t)
	payload := []byte("bounded go-jose signature-count payload")
	compact := signGoJoseCompatibilityPayload(t, key, payload)
	atLimit := goJoseCompatibilityGeneralJWS(t, compact, 32)
	parsed, err := jose.ParseSignedJSON(atLimit, []jose.SignatureAlgorithm{jose.RS256})
	if err != nil || parsed == nil {
		t.Fatal("rejected general JWS at the 32-signature limit")
	}
	if len(parsed.Signatures) != 32 {
		t.Fatal("general JWS signature count changed")
	}
	index, _, verified, err := parsed.VerifyMulti(&key.PublicKey)
	if err != nil || index != 0 || !bytes.Equal(verified, payload) {
		t.Fatal("general JWS at the signature limit did not verify the exact payload")
	}

	overLimit := goJoseCompatibilityGeneralJWS(t, compact, 33)
	rejected, err := jose.ParseSignedJSON(overLimit, []jose.SignatureAlgorithm{jose.RS256})
	if err == nil || rejected != nil {
		t.Fatal("accepted general JWS beyond the 32-signature limit")
	}
	if !strings.Contains(err.Error(), "too many signatures in JWS; maximum is 32") {
		t.Fatal("general JWS failed outside the signature-count limit")
	}
}

func TestGoJoseRSAJWKRejectsMalformedParameters(t *testing.T) {
	key := newGoJoseCompatibilityKey(t)
	fields := goJoseCompatibilityJWK(&key.PublicKey)
	bundle, err := parseGoJoseCompatibilityJWK(t, fields)
	if err != nil || bundle == nil {
		t.Fatal("rejected the valid public RSA JWK mutation baseline")
	}

	for _, test := range []struct {
		name     string
		field    string
		exponent []byte
		omit     bool
		want     string
	}{
		{name: "missing-modulus", field: "n", omit: true, want: "missing n/e values"},
		{name: "missing-exponent", field: "e", omit: true, want: "missing n/e values"},
		{name: "zero-exponent", exponent: []byte{0}, want: "bad e value"},
		{name: "one-exponent", exponent: []byte{1}, want: "bad e value"},
		{
			name:     "signed-64-bit-overflow",
			exponent: []byte{0x80, 0, 0, 0, 0, 0, 0, 0},
			want:     "bad e value",
		},
		{
			name:     "unsigned-64-bit-overflow",
			exponent: []byte{1, 0, 0, 0, 0, 0, 0, 0, 0},
			want:     "bad e value",
		},
	} {
		t.Run(test.name, func(t *testing.T) {
			malformed := goJoseCompatibilityJWK(&key.PublicKey)
			if test.omit {
				delete(malformed, test.field)
			} else {
				malformed["e"] = base64.RawURLEncoding.EncodeToString(test.exponent)
			}
			rejected, parseErr := parseGoJoseCompatibilityJWK(t, malformed)
			if parseErr == nil || rejected != nil {
				t.Fatal("accepted malformed public RSA JWK")
			}
			if !strings.Contains(parseErr.Error(), test.want) {
				t.Fatal("public RSA JWK failed outside the expected parameter validation")
			}
		})
	}
}

func TestGoJoseRejectsNullProtectedHeader(t *testing.T) {
	for _, test := range []struct {
		name  string
		input string
		parse func(string, []jose.SignatureAlgorithm) (*jose.JSONWebSignature, error)
	}{
		{
			name:  "compact",
			input: "bnVsbA.dGVzdA.AAAA",
			parse: jose.ParseSignedCompact,
		},
		{
			name:  "general",
			input: `{"payload":"dGVzdA","signatures":[{"protected":"bnVsbA","header":{"alg":"RS256"},"signature":"AAAA"}]}`,
			parse: jose.ParseSignedJSON,
		},
	} {
		t.Run(test.name, func(t *testing.T) {
			parsed, err := test.parse(test.input, []jose.SignatureAlgorithm{jose.RS256})
			if err == nil || parsed != nil {
				t.Fatal("accepted null protected JWS header")
			}
			if !strings.Contains(err.Error(), "invalid protected header") {
				t.Fatal("null protected JWS header failed outside header validation")
			}
		})
	}
}

func newGoJoseCompatibilityKey(t *testing.T) *rsa.PrivateKey {
	t.Helper()
	key, err := rsa.GenerateKey(rand.Reader, 2048)
	if err != nil || key == nil || key.N == nil || key.N.BitLen() != 2048 || key.E != 65537 {
		t.Fatal("could not generate the ordinary RSA compatibility fixture")
	}
	return key
}

func goJoseCompatibilityJWK(public *rsa.PublicKey) map[string]string {
	return map[string]string{
		"kid": "rsa-compatibility",
		"kty": "RSA",
		"n":   base64.RawURLEncoding.EncodeToString(public.N.Bytes()),
		"e":   "AQAB",
	}
}

func parseGoJoseCompatibilityJWK(t *testing.T, fields map[string]string) (*jwtbundle.Bundle, error) {
	t.Helper()
	td, err := spiffeid.TrustDomainFromString("example.org")
	if err != nil {
		t.Fatal("invalid fixed compatibility trust domain")
	}
	body, err := json.Marshal(map[string]any{"keys": []map[string]string{fields}})
	if err != nil || len(body) > 1024 {
		t.Fatal("invalid bounded public JWKS compatibility fixture")
	}
	return jwtbundle.Parse(td, body)
}

func signGoJoseCompatibilityPayload(t *testing.T, key *rsa.PrivateKey, payload []byte) string {
	t.Helper()
	signer, err := jose.NewSigner(jose.SigningKey{Algorithm: jose.RS256, Key: key}, nil)
	if err != nil || signer == nil {
		t.Fatal("could not create the RS256 compatibility signer")
	}
	signed, err := signer.Sign(payload)
	if err != nil || signed == nil {
		t.Fatal("could not sign the compatibility payload")
	}
	compact, err := signed.CompactSerialize()
	if err != nil || compact == "" || len(compact) > 1024 {
		t.Fatal("invalid bounded compact JWS compatibility fixture")
	}
	return compact
}

func assertGoJoseTamperedSignatureRejected(t *testing.T, compact string, public *rsa.PublicKey) {
	t.Helper()
	parts := strings.Split(compact, ".")
	if len(parts) != 3 {
		t.Fatal("invalid compact JWS segment count")
	}
	signature, err := base64.RawURLEncoding.DecodeString(parts[2])
	if err != nil || len(signature) == 0 {
		t.Fatal("invalid compact JWS signature fixture")
	}
	signature[0] ^= 1
	parts[2] = base64.RawURLEncoding.EncodeToString(signature)
	tampered, err := jose.ParseSignedCompact(strings.Join(parts, "."), []jose.SignatureAlgorithm{jose.RS256})
	if err != nil || tampered == nil {
		t.Fatal("tampered compact JWS failed before signature verification")
	}
	verified, err := tampered.Verify(public)
	if err == nil || verified != nil {
		t.Fatal("accepted a tampered RS256 signature")
	}
}

func goJoseCompatibilityGeneralJWS(t *testing.T, compact string, count int) string {
	t.Helper()
	parts := strings.Split(compact, ".")
	if len(parts) != 3 || count < 1 || count > 33 {
		t.Fatal("invalid bounded general JWS fixture parameters")
	}
	signatures := make([]map[string]string, count)
	for index := range signatures {
		signatures[index] = map[string]string{
			"protected": parts[0],
			"signature": parts[2],
		}
	}
	body, err := json.Marshal(map[string]any{
		"payload":    parts[1],
		"signatures": signatures,
	})
	if err != nil || len(body) > 32*1024 {
		t.Fatal("invalid bounded general JWS compatibility fixture")
	}
	return string(body)
}
