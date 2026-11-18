package main

import (
	"context"
	"crypto/ecdsa"
	"crypto/elliptic"
	"crypto/rand"
	"crypto/tls"
	"crypto/x509"
	"errors"
	"io"
	"math/big"
	"net/http"
	"net/http/httptest"
	"net/url"
	"sync/atomic"
	"testing"
	"time"

	"github.com/spiffe/go-spiffe/v2/bundle/x509bundle"
	"github.com/spiffe/go-spiffe/v2/spiffeid"
	"github.com/spiffe/go-spiffe/v2/spiffetls/tlsconfig"
	"github.com/spiffe/go-spiffe/v2/svid/x509svid"
	"github.com/spiffe/go-spiffe/v2/workloadapi"
)

func tlsFixtureCA(t *testing.T) (*x509.Certificate, *ecdsa.PrivateKey) {
	t.Helper()
	key, err := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	if err != nil {
		t.Fatal(err)
	}
	template := &x509.Certificate{
		SerialNumber: big.NewInt(1), IsCA: true, BasicConstraintsValid: true,
		KeyUsage: x509.KeyUsageCertSign | x509.KeyUsageCRLSign,
		NotBefore: time.Now().Add(-time.Hour), NotAfter: time.Now().Add(time.Hour),
	}
	der, err := x509.CreateCertificate(rand.Reader, template, template, &key.PublicKey, key)
	if err != nil {
		t.Fatal(err)
	}
	cert, err := x509.ParseCertificate(der)
	if err != nil {
		t.Fatal(err)
	}
	return cert, key
}

func tlsFixtureSVID(t *testing.T, ca *x509.Certificate, key *ecdsa.PrivateKey, id spiffeid.ID, expires time.Time) *x509svid.SVID {
	t.Helper()
	leafKey, err := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	if err != nil {
		t.Fatal(err)
	}
	uri, err := url.Parse(id.String())
	if err != nil {
		t.Fatal(err)
	}
	serial, err := rand.Int(rand.Reader, new(big.Int).Lsh(big.NewInt(1), 128))
	if err != nil {
		t.Fatal(err)
	}
	template := &x509.Certificate{
		SerialNumber: serial, URIs: []*url.URL{uri}, BasicConstraintsValid: true,
		KeyUsage: x509.KeyUsageDigitalSignature,
		ExtKeyUsage: []x509.ExtKeyUsage{x509.ExtKeyUsageClientAuth, x509.ExtKeyUsageServerAuth},
		NotBefore: time.Now().Add(-time.Hour), NotAfter: expires,
	}
	der, err := x509.CreateCertificate(rand.Reader, template, ca, &leafKey.PublicKey, key)
	if err != nil {
		t.Fatal(err)
	}
	cert, err := x509.ParseCertificate(der)
	if err != nil {
		t.Fatal(err)
	}
	return &x509svid.SVID{ID: id, Certificates: []*x509.Certificate{cert}, PrivateKey: leafKey}
}

func tlsFixtureContext(svid *x509svid.SVID, roots ...*x509.Certificate) *workloadapi.X509Context {
	return &workloadapi.X509Context{
		SVIDs:   []*x509svid.SVID{svid},
		Bundles: x509bundle.NewSet(x509bundle.FromX509Authorities(svid.ID.TrustDomain(), roots)),
	}
}

func tlsFixtureServer(t *testing.T, serverSVID *x509svid.SVID, root *x509.Certificate, self spiffeid.ID, handler http.Handler) *httptest.Server {
	t.Helper()
	server := httptest.NewUnstartedServer(handler)
	server.TLS = tlsconfig.MTLSServerConfig(
		serverSVID,
		x509bundle.FromX509Authorities(self.TrustDomain(), []*x509.Certificate{root}),
		tlsconfig.AuthorizeID(self),
	)
	// httptest installs a localhost certificate when Certificates is empty; avoid
	// that fallback for IP-address requests without SNI.
	server.TLS.Certificates = []tls.Certificate{{
		Certificate: [][]byte{serverSVID.Certificates[0].Raw},
		PrivateKey: serverSVID.PrivateKey, Leaf: serverSVID.Certificates[0],
	}}
	server.TLS.MinVersion = tls.VersionTLS13
	server.StartTLS()
	t.Cleanup(server.Close)
	return server
}

func TestProxyTLSIdentityBoundary(t *testing.T) {
	self := spiffeid.RequireFromString("spiffe://university.ecosystem/frontend")
	peer := spiffeid.RequireFromString("spiffe://university.ecosystem/backend")
	wrong := spiffeid.RequireFromString("spiffe://university.ecosystem/unrelated")
	ca, key := tlsFixtureCA(t)
	foreignCA, foreignKey := tlsFixtureCA(t)
	validUntil := time.Now().Add(10 * time.Minute)
	client := tlsFixtureSVID(t, ca, key, self, validUntil)
	tests := []struct {
		name   string
		server *x509svid.SVID
		client *x509svid.SVID
		status int
	}{
		{"authorized", tlsFixtureSVID(t, ca, key, peer, validUntil), client, http.StatusOK},
		{"wrong-peer-same-ca", tlsFixtureSVID(t, ca, key, wrong, validUntil), client, http.StatusBadGateway},
		{"untrusted-peer-ca", tlsFixtureSVID(t, foreignCA, foreignKey, peer, validUntil), client, http.StatusBadGateway},
		{"expired-peer", tlsFixtureSVID(t, ca, key, peer, time.Now().Add(-time.Minute)), client, http.StatusBadGateway},
		{"wrong-self", tlsFixtureSVID(t, ca, key, peer, validUntil), tlsFixtureSVID(t, ca, key, wrong, validUntil), http.StatusBadGateway},
		{"expired-self", tlsFixtureSVID(t, ca, key, peer, validUntil), tlsFixtureSVID(t, ca, key, self, time.Now().Add(-time.Minute)), http.StatusBadGateway},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			var calls atomic.Int32
			server := tlsFixtureServer(t, tc.server, ca, self, http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				calls.Add(1)
				if r.Header.Get("Authorization") != "Bearer example" || r.Header.Get("Cookie") != "session=example" {
					t.Error("end-user credentials were not preserved")
				}
				if r.Header.Get("X-Internal-Signature") != "" || r.Header.Get("Forwarded") != "" || r.Header.Get("X-Forwarded-For") != "" {
					t.Error("untrusted forwarding or internal identity headers survived")
				}
				w.WriteHeader(http.StatusOK)
			}))
			origin, err := url.Parse(server.URL)
			if err != nil {
				t.Fatal(err)
			}
			cfg := proxyConfig{origin: origin, self: self, peer: peer}
			handler := newProxy(cfg, func(context.Context) (*workloadapi.X509Context, error) {
				return tlsFixtureContext(tc.client, ca), nil
			})
			request := httptest.NewRequest(http.MethodGet, "http://attacker.invalid/resource", nil)
			request.Header.Set("Authorization", "Bearer example")
			request.Header.Set("Cookie", "session=example")
			request.Header.Set("X-Internal-Signature", "untrusted")
			request.Header.Set("Forwarded", "for=attacker")
			request.Header.Set("X-Forwarded-For", "attacker")
			response := httptest.NewRecorder()
			handler.ServeHTTP(response, request)
			if response.Code != tc.status {
				t.Fatalf("status = %d; want %d", response.Code, tc.status)
			}
			wantCalls := int32(0)
			if tc.status == http.StatusOK {
				wantCalls = 1
			}
			if calls.Load() != wantCalls {
				t.Fatalf("backend dispatches = %d; want %d", calls.Load(), wantCalls)
			}
		})
	}
}

func TestProxyTLSActiveGenerationCancellation(t *testing.T) {
	for _, failure := range []string{"source-error", "renewed-svid", "replaced-bundle"} {
		t.Run(failure, func(t *testing.T) {
			self := spiffeid.RequireFromString("spiffe://university.ecosystem/frontend")
			peer := spiffeid.RequireFromString("spiffe://university.ecosystem/backend")
			ca, key := tlsFixtureCA(t)
			validUntil := time.Now().Add(10 * time.Minute)
			client := tlsFixtureSVID(t, ca, key, self, validUntil)
			renewed := tlsFixtureSVID(t, ca, key, self, validUntil)
			addedCA, _ := tlsFixtureCA(t)
			var changed atomic.Bool
			server := tlsFixtureServer(t, tlsFixtureSVID(t, ca, key, peer, validUntil), ca, self, http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				w.WriteHeader(http.StatusOK)
				w.(http.Flusher).Flush()
				<-r.Context().Done()
			}))
			origin, err := url.Parse(server.URL)
			if err != nil {
				t.Fatal(err)
			}
			cfg := proxyConfig{origin: origin, self: self, peer: peer}
			transport := liveTransport{cfg: cfg, fetch: func(context.Context) (*workloadapi.X509Context, error) {
				if changed.Load() {
					switch failure {
					case "source-error":
						return nil, errors.New("agent unavailable")
					case "renewed-svid":
						return tlsFixtureContext(renewed, ca), nil
					case "replaced-bundle":
						return tlsFixtureContext(client, ca, addedCA), nil
					}
				}
				return tlsFixtureContext(client, ca), nil
			}}
			ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
			defer cancel()
			request, err := http.NewRequestWithContext(ctx, http.MethodGet, server.URL, nil)
			if err != nil {
				t.Fatal(err)
			}
			response, err := transport.RoundTrip(request)
			if err != nil {
				t.Fatal(err)
			}
			defer response.Body.Close()
			changed.Store(true)
			start := time.Now()
			if _, err := io.ReadAll(response.Body); err == nil {
				t.Fatal("stale streaming connection was not terminated")
			}
			if time.Since(start) > 2*time.Second {
				t.Fatal("generation cancellation exceeded bounded refresh window")
			}
		})
	}
}

func TestProxyTLSPeerExpiryBeforeHeaders(t *testing.T) {
	self := spiffeid.RequireFromString("spiffe://university.ecosystem/frontend")
	peer := spiffeid.RequireFromString("spiffe://university.ecosystem/backend")
	ca, key := tlsFixtureCA(t)
	client := tlsFixtureSVID(t, ca, key, self, time.Now().Add(10*time.Minute))
	expiry := time.Now().Add(3 * time.Second).Truncate(time.Second)
	serverSVID := tlsFixtureSVID(t, ca, key, peer, expiry)
	dispatched := make(chan struct{})
	server := tlsFixtureServer(t, serverSVID, ca, self, http.HandlerFunc(func(_ http.ResponseWriter, r *http.Request) {
		close(dispatched)
		<-r.Context().Done()
	}))
	origin, err := url.Parse(server.URL)
	if err != nil {
		t.Fatal(err)
	}
	transport := liveTransport{
		cfg: proxyConfig{origin: origin, self: self, peer: peer},
		fetch: func(context.Context) (*workloadapi.X509Context, error) {
			return tlsFixtureContext(client, ca), nil
		},
	}
	ctx, cancel := context.WithTimeout(context.Background(), 8*time.Second)
	defer cancel()
	request, err := http.NewRequestWithContext(ctx, http.MethodGet, server.URL, nil)
	if err != nil {
		t.Fatal(err)
	}
	response, err := transport.RoundTrip(request)
	if response != nil {
		response.Body.Close()
	}
	if err == nil {
		t.Fatal("accepted response with expired peer")
	}
	select {
	case <-dispatched:
	default:
		t.Fatal("test never established authenticated backend request")
	}
	if time.Now().Before(expiry) {
		t.Fatal("request failed before the peer expired")
	}
	if time.Since(expiry) > time.Second {
		t.Fatal("peer expiry did not cancel the request before response headers")
	}
}
