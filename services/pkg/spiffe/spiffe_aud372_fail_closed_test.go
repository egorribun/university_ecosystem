package spiffe

import (
	"crypto/ecdsa"
	"crypto/elliptic"
	"crypto/rand"
	"crypto/x509"
	"crypto/x509/pkix"
	"errors"
	"math/big"
	"net/url"
	"testing"
	"time"

	"github.com/spiffe/go-spiffe/v2/bundle/x509bundle"
	"github.com/spiffe/go-spiffe/v2/spiffeid"
	"github.com/spiffe/go-spiffe/v2/svid/x509svid"
)

type aud372Source struct {
	bundle  *x509bundle.Bundle
	rootKey *ecdsa.PrivateKey
}

func (s *aud372Source) GetX509SVID() (*x509svid.SVID, error) {
	return nil, errors.New("SVID access is not used by this test")
}

func (s *aud372Source) GetX509BundleForTrustDomain(td spiffeid.TrustDomain) (*x509bundle.Bundle, error) {
	return s.bundle.GetX509BundleForTrustDomain(td)
}

func (*aud372Source) Close() error { return nil }

func TestAUD372ServerTLSConfigRejectsEmptyAllowlist(t *testing.T) {
	client := newAUD372Client(t)
	for _, test := range []struct {
		name string
		ids  []string
	}{
		{name: "no arguments"},
		{name: "empty slice", ids: []string{}},
	} {
		t.Run(test.name, func(t *testing.T) {
			serverTLS, err := client.ServerTLSConfig(test.ids...)
			if err != nil {
				t.Fatalf("ServerTLSConfig failed before peer authorization: %v", err)
			}
			leaf := newAUD372SVID(t, client, "spiffe://example.org/ns/default/sa/unspecified")
			if err := serverTLS.VerifyPeerCertificate([][]byte{leaf.Raw}, nil); err == nil {
				t.Fatal("accepted a same-domain client with an empty client ID allowlist")
			}
		})
	}
}
func TestAUD372ServerTLSConfigAuthorizesOnlyExplicitClientID(t *testing.T) {
	client := newAUD372Client(t)
	const allowedID = "spiffe://example.org/ns/default/sa/gateway"

	serverTLS, err := client.ServerTLSConfig(allowedID)
	if err != nil {
		t.Fatalf("ServerTLSConfig rejected explicit client ID: %v", err)
	}

	for _, test := range []struct {
		name      string
		id        string
		wantError bool
	}{
		{name: "explicit ID", id: allowedID},
		{name: "other ID in trusted domain", id: "spiffe://example.org/ns/default/sa/other", wantError: true},
		{name: "ID in another domain", id: "spiffe://other.example/ns/default/sa/gateway", wantError: true},
	} {
		t.Run(test.name, func(t *testing.T) {
			leaf := newAUD372SVID(t, client, test.id)
			err := serverTLS.VerifyPeerCertificate([][]byte{leaf.Raw}, nil)
			if test.wantError && err == nil {
				t.Fatalf("accepted unlisted client ID %q", test.id)
			}
			if !test.wantError && err != nil {
				t.Fatalf("rejected listed client ID %q: %v", test.id, err)
			}
		})
	}
}

func newAUD372Client(t *testing.T) *Client {
	t.Helper()

	td, err := spiffeid.TrustDomainFromString("example.org")
	if err != nil {
		t.Fatal(err)
	}
	rootKey, err := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	if err != nil {
		t.Fatal(err)
	}
	now := time.Now()
	rootTemplate := &x509.Certificate{
		SerialNumber:          big.NewInt(1),
		Subject:               pkix.Name{CommonName: "AUD-372 test root"},
		NotBefore:             now.Add(-time.Hour),
		NotAfter:              now.Add(time.Hour),
		IsCA:                  true,
		BasicConstraintsValid: true,
		KeyUsage:              x509.KeyUsageCertSign | x509.KeyUsageDigitalSignature,
	}
	rootDER, err := x509.CreateCertificate(rand.Reader, rootTemplate, rootTemplate, &rootKey.PublicKey, rootKey)
	if err != nil {
		t.Fatal(err)
	}
	root, err := x509.ParseCertificate(rootDER)
	if err != nil {
		t.Fatal(err)
	}
	bundle := x509bundle.FromX509Authorities(td, []*x509.Certificate{root})

	return &Client{source: &aud372Source{bundle: bundle, rootKey: rootKey}, trustDomain: td}
}

func newAUD372SVID(t *testing.T, client *Client, spiffeURI string) *x509.Certificate {
	t.Helper()

	source, ok := client.source.(*aud372Source)
	if !ok {
		t.Fatal("unexpected test source type")
	}
	root := source.bundle.X509Authorities()[0]
	uri, err := url.Parse(spiffeURI)
	if err != nil {
		t.Fatal(err)
	}
	leafKey, err := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	if err != nil {
		t.Fatal(err)
	}
	leafTemplate := &x509.Certificate{
		SerialNumber: big.NewInt(2),
		NotBefore:    time.Now().Add(-time.Hour),
		NotAfter:     time.Now().Add(time.Hour),
		KeyUsage:     x509.KeyUsageDigitalSignature,
		ExtKeyUsage:  []x509.ExtKeyUsage{x509.ExtKeyUsageClientAuth},
		URIs:         []*url.URL{uri},
	}
	leafDER, err := x509.CreateCertificate(rand.Reader, leafTemplate, root, &leafKey.PublicKey, source.rootKey)
	if err != nil {
		t.Fatal(err)
	}
	leaf, err := x509.ParseCertificate(leafDER)
	if err != nil {
		t.Fatal(err)
	}
	return leaf
}
