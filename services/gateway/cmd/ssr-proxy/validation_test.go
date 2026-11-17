package main

import (
	"context"
	"crypto/tls"
	"crypto/x509"
	"errors"
	"testing"
	"time"

	"github.com/spiffe/go-spiffe/v2/bundle/x509bundle"
	"github.com/spiffe/go-spiffe/v2/spiffeid"
	"github.com/spiffe/go-spiffe/v2/svid/x509svid"
	"github.com/spiffe/go-spiffe/v2/workloadapi"
	"github.com/stretchr/testify/require"
)

type failingIdentity struct{}

func (failingIdentity) GetX509SVID() (*x509svid.SVID, error) {
	return nil, errors.New("source closed")
}

func TestProxyIdentityAndCertificateFailures(t *testing.T) {
	self := spiffeid.RequireFromString("spiffe://university.ecosystem/frontend")
	_, err := (checkedIdentity{source: failingIdentity{}, id: self}).GetX509SVID()
	require.Error(t, err)
	for _, svid := range []*x509svid.SVID{
		nil,
		{ID: self},
		{ID: self, Certificates: []*x509.Certificate{nil}},
		{ID: self, Certificates: []*x509.Certificate{{}}},
	} {
		_, err := (checkedIdentity{source: svid, id: self}).GetX509SVID()
		require.Error(t, err)
	}
	now := time.Now()
	for _, certs := range [][]*x509.Certificate{
		nil,
		{nil},
		{{NotBefore: now.Add(time.Hour), NotAfter: now.Add(2 * time.Hour)}},
		{{NotBefore: now.Add(-time.Hour), NotAfter: now.Add(-time.Second)}},
	} {
		_, err := certificateDeadline(certs)
		require.Error(t, err)
	}
	deadline, err := certificateDeadline([]*x509.Certificate{
		{NotBefore: now.Add(-time.Hour), NotAfter: now.Add(time.Hour)},
		{NotBefore: now.Add(-time.Hour), NotAfter: now.Add(time.Minute)},
	})
	require.NoError(t, err)
	require.Equal(t, now.Add(time.Minute), deadline)
}

func TestProxySnapshotRejectsUnavailableOrInvalidMaterial(t *testing.T) {
	values := proxyEnvironment()
	cfg, err := readConfig(func(key string) string { return values[key] })
	require.NoError(t, err)
	ca, key := tlsFixtureCA(t)
	foreign, _ := tlsFixtureCA(t)
	svid := tlsFixtureSVID(t, ca, key, cfg.self, time.Now().Add(time.Hour))
	expired := *ca
	expired.NotAfter = time.Now().Add(-time.Second)
	contexts := []*workloadapi.X509Context{
		nil,
		{},
		{SVIDs: []*x509svid.SVID{svid}},
		{SVIDs: []*x509svid.SVID{nil}, Bundles: x509bundle.NewSet()},
		{SVIDs: []*x509svid.SVID{svid}, Bundles: x509bundle.NewSet()},
		tlsFixtureContext(svid),
		tlsFixtureContext(svid, &expired),
		tlsFixtureContext(svid, foreign),
	}
	for _, current := range contexts {
		_, _, _, err := snapshot(context.Background(), cfg, func(context.Context) (*workloadapi.X509Context, error) {
			return current, nil
		})
		require.Error(t, err)
	}
	_, _, _, err = snapshot(context.Background(), cfg, func(context.Context) (*workloadapi.X509Context, error) {
		return nil, errors.New("agent unavailable")
	})
	require.Error(t, err)
}

func TestProxyPeerDeadlineCoversHandshakeWait(t *testing.T) {
	now := time.Now()
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	verify, stop := peerDeadline(ctx, cancel, now.Add(time.Hour))
	defer stop()
	require.Error(t, verify(tls.ConnectionState{}))
	require.NoError(t, verify(tls.ConnectionState{PeerCertificates: []*x509.Certificate{{
		NotBefore: now.Add(-time.Hour), NotAfter: now.Add(50 * time.Millisecond),
	}}}))
	select {
	case <-ctx.Done():
	case <-time.After(time.Second):
		t.Fatal("peer expiry did not cancel request before response headers")
	}
	require.Error(t, verify(tls.ConnectionState{PeerCertificates: []*x509.Certificate{{
		NotBefore: now.Add(-time.Hour), NotAfter: now.Add(time.Hour),
	}}}))
	stop()
}
