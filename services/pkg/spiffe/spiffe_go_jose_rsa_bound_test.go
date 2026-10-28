package spiffe

import (
	"bytes"
	"crypto/rsa"
	"encoding/base64"
	"encoding/json"
	"strings"
	"testing"

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
