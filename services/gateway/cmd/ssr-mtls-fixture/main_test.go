package main

import (
	"context"
	"crypto/ecdsa"
	"crypto/elliptic"
	"crypto/rand"
	"crypto/x509"
	"encoding/json"
	"errors"
	"io"
	"math/big"
	"net"
	"net/http"
	"net/http/httptest"
	"net/url"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	"github.com/spiffe/go-spiffe/v2/bundle/x509bundle"
	"github.com/spiffe/go-spiffe/v2/spiffeid"
	"github.com/spiffe/go-spiffe/v2/svid/x509svid"
	"github.com/spiffe/go-spiffe/v2/workloadapi"
	"github.com/stretchr/testify/require"
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

func fixtureEnvironment() map[string]string {
	return map[string]string{
		"SPIFFE_ENDPOINT_SOCKET": "unix:///tmp/agent.sock",
		"FIXTURE_SELF_ID":        "spiffe://proof.test/server",
		"FIXTURE_PEER_ID":        "spiffe://proof.test/client",
		"FIXTURE_URL":            "https://backend:8000/health/ready",
	}
}

func TestFixtureConfiguration(t *testing.T) {
	for _, mode := range []string{"serve", "inspect", "check", "peer", "idle"} {
		env := fixtureEnvironment()
		cfg, err := readFixtureConfig([]string{mode}, func(k string) string { return env[k] })
		require.NoError(t, err)
		require.Equal(t, mode, cfg.mode)
	}
	for _, change := range [][2]string{
		{"SPIFFE_ENDPOINT_SOCKET", "tcp://agent:8081"},
		{"SPIFFE_ENDPOINT_SOCKET", "unix://host/tmp/sock"},
		{"FIXTURE_SELF_ID", "invalid"},
		{"FIXTURE_PEER_ID", "spiffe://other.test/client"},
		{"FIXTURE_PEER_ID", "spiffe://proof.test/server"},
		{"FIXTURE_URL", "http://backend/health/ready"},
		{"FIXTURE_URL", "https://user:password@backend/health/ready"},
		{"FIXTURE_URL", "https://backend/arbitrary"},
		{"FIXTURE_URL", "https://backend/health/ready?"},
	} {
		env := fixtureEnvironment()
		env[change[0]] = change[1]
		_, err := readFixtureConfig([]string{"check"}, func(k string) string { return env[k] })
		require.Error(t, err)
	}
	_, err := readFixtureConfig(nil, func(string) string { return "" })
	require.Error(t, err)
}

func TestFixtureSnapshotReceiptAndRejection(t *testing.T) {
	self := spiffeid.RequireFromString("spiffe://proof.test/server")
	ca, key := tlsFixtureCA(t)
	svid := tlsFixtureSVID(t, ca, key, self, time.Now().Add(time.Minute))
	current := tlsFixtureContext(svid, ca)
	cfg := fixtureConfig{self: self}
	fetch := func(context.Context) (*workloadapi.X509Context, error) { return current, nil }
	gotSVID, gotBundle, receipt, err := fixtureSnapshot(context.Background(), cfg, fetch)
	require.NoError(t, err)
	require.Same(t, svid, gotSVID)
	require.NotNil(t, gotBundle)
	require.Equal(t, self.String(), receipt.SelfID)
	require.Len(t, receipt.LeafSHA256, 64)
	require.Equal(t, svid.Certificates[0].NotAfter.Unix(), receipt.LeafNotAfterUnix)
	require.Len(t, receipt.Roots, 1)
	require.Equal(t, receipt.IssuerKeyID, receipt.Roots[0])
	encoded, err := json.Marshal(receipt)
	require.NoError(t, err)
	var fields map[string]any
	require.NoError(t, json.Unmarshal(encoded, &fields))
	require.Len(t, fields, 5)
	require.NotContains(t, string(encoded), "PRIVATE")
	require.NotContains(t, string(encoded), "CERTIFICATE")

	cfg.self = spiffeid.RequireFromString("spiffe://proof.test/other")
	_, _, _, err = fixtureSnapshot(context.Background(), cfg, fetch)
	require.Error(t, err)
	cfg.self = self
	current = nil
	_, _, _, err = fixtureSnapshot(context.Background(), cfg, fetch)
	require.Error(t, err)
	current = tlsFixtureContext(tlsFixtureSVID(t, ca, key, self, time.Now().Add(-time.Minute)), ca)
	_, _, _, err = fixtureSnapshot(context.Background(), cfg, fetch)
	require.Error(t, err)
	foreign, _ := tlsFixtureCA(t)
	current = tlsFixtureContext(svid, foreign)
	_, _, _, err = fixtureSnapshot(context.Background(), cfg, fetch)
	require.Error(t, err)
	_, _, _, err = fixtureSnapshot(context.Background(), cfg, func(ctx context.Context) (*workloadapi.X509Context, error) {
		_, ok := ctx.Deadline()
		require.True(t, ok)
		return nil, errors.New("unavailable")
	})
	require.Error(t, err)
}

func TestFixtureRealTLSExactPeer(t *testing.T) {
	self := spiffeid.RequireFromString("spiffe://proof.test/server")
	peer := spiffeid.RequireFromString("spiffe://proof.test/client")
	ca, key := tlsFixtureCA(t)
	server := tlsFixtureSVID(t, ca, key, self, time.Now().Add(time.Minute))
	client := tlsFixtureSVID(t, ca, key, peer, time.Now().Add(time.Minute))
	bundle := x509bundle.FromX509Authorities(self.TrustDomain(), []*x509.Certificate{ca})
	listener, err := net.Listen("tcp", "127.0.0.1:0")
	require.NoError(t, err)
	ctx, cancel := context.WithCancel(context.Background())
	done := make(chan error, 1)
	go func() { done <- serveFixture(ctx, listener, server, bundle, peer) }()
	t.Cleanup(func() {
		cancel()
		select {
		case err := <-done:
			require.NoError(t, err)
		case <-time.After(3 * time.Second):
			t.Error("fixture did not stop")
		}
	})
	cfg := fixtureConfig{self: peer, peer: self, target: "https://" + listener.Addr().String() + "/health/ready"}
	require.NoError(t, checkFixture(context.Background(), cfg, client, bundle))
	cfg.peer = spiffeid.RequireFromString("spiffe://proof.test/wrong")
	require.Error(t, checkFixture(context.Background(), cfg, client, bundle))
	cfg.peer = self
	wrong := tlsFixtureSVID(t, ca, key, spiffeid.RequireFromString("spiffe://proof.test/wrong"), time.Now().Add(time.Minute))
	require.Error(t, checkFixture(context.Background(), cfg, wrong, bundle))
}

func TestFixtureHandlerAndIdle(t *testing.T) {
	for _, tc := range []struct {
		method string
		path   string
		status int
	}{
		{http.MethodGet, "/health/ready", http.StatusOK},
		{http.MethodPost, "/health/ready", http.StatusMethodNotAllowed},
		{http.MethodGet, "/other", http.StatusNotFound},
	} {
		recorder := httptest.NewRecorder()
		fixtureHandler().ServeHTTP(recorder, httptest.NewRequest(tc.method, tc.path, nil))
		require.Equal(t, tc.status, recorder.Code)
	}
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	recorder := httptest.NewRecorder()
	fixtureHandler().ServeHTTP(recorder, httptest.NewRequest(http.MethodGet, "/stream", nil).WithContext(ctx))
	require.Equal(t, "OPEN\n", recorder.Body.String())
	require.True(t, recorder.Flushed)
	require.NoError(t, runFixture(ctx, fixtureConfig{mode: "idle"}, io.Discard))
	require.False(t, strings.Contains(recorder.Body.String(), "PRIVATE"))
}

func TestFixtureFrozenPeerRefreshesClientTrust(t *testing.T) {
	self := spiffeid.RequireFromString("spiffe://proof.test/server")
	peer := spiffeid.RequireFromString("spiffe://proof.test/client")
	oldCA, oldKey := tlsFixtureCA(t)
	newCA, newKey := tlsFixtureCA(t)
	expiry := time.Now().Add(time.Minute)
	frozen := tlsFixtureSVID(t, oldCA, oldKey, self, expiry)
	renewed := tlsFixtureSVID(t, newCA, newKey, self, expiry)
	oldClient := tlsFixtureSVID(t, oldCA, oldKey, peer, expiry)
	newClient := tlsFixtureSVID(t, newCA, newKey, peer, expiry)
	var current atomic.Pointer[workloadapi.X509Context]
	current.Store(tlsFixtureContext(frozen, oldCA))
	var failed atomic.Bool
	ctx, cancel := context.WithCancel(context.Background())
	source := fixtureBundleSource{
		ctx: ctx, cfg: fixtureConfig{self: self},
		fetch: func(context.Context) (*workloadapi.X509Context, error) {
			if failed.Load() {
				return nil, errors.New("source unavailable")
			}
			return current.Load(), nil
		},
	}
	_, err := source.GetX509BundleForTrustDomain(spiffeid.RequireFromString("spiffe://foreign.test/client").TrustDomain())
	require.Error(t, err)
	listener, err := net.Listen("tcp", "127.0.0.1:0")
	require.NoError(t, err)
	done := make(chan error, 1)
	go func() { done <- serveFixture(ctx, listener, frozen, source, peer) }()
	t.Cleanup(func() {
		cancel()
		select {
		case err := <-done:
			require.NoError(t, err)
		case <-time.After(3 * time.Second):
			t.Error("fixture did not stop")
		}
	})
	cfg := fixtureConfig{self: peer, peer: self, target: "https://" + listener.Addr().String() + "/health/ready"}
	oldBundle := x509bundle.FromX509Authorities(self.TrustDomain(), []*x509.Certificate{oldCA})
	overlap := x509bundle.FromX509Authorities(self.TrustDomain(), []*x509.Certificate{oldCA, newCA})
	newOnly := x509bundle.FromX509Authorities(self.TrustDomain(), []*x509.Certificate{newCA})
	before, err := inspectPeer(context.Background(), cfg, oldClient, oldBundle)
	require.NoError(t, err)
	current.Store(tlsFixtureContext(renewed, oldCA, newCA))
	after, err := inspectPeer(context.Background(), cfg, newClient, overlap)
	require.NoError(t, err)
	require.Equal(t, before.LeafSHA256, after.LeafSHA256)
	require.Equal(t, before.IssuerKeyID, after.IssuerKeyID)
	require.Equal(t, self.String(), after.SelfID)
	require.Equal(t, frozen.Certificates[0].NotAfter.Unix(), after.LeafNotAfterUnix)
	require.Len(t, after.Roots, 2)
	// Old peer is rejected only after the client removes its root, even though
	// the server now accepts the new client through its refreshed trust bundle.
	current.Store(tlsFixtureContext(renewed, newCA))
	require.NoError(t, checkFixture(context.Background(), cfg, newClient, overlap))
	require.Error(t, checkFixture(context.Background(), cfg, newClient, newOnly))
	failed.Store(true)
	require.Error(t, checkFixture(context.Background(), cfg, newClient, overlap))
}
