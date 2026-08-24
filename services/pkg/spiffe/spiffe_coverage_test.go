package spiffe

import (
	"context"
	"errors"
	"testing"
	"time"

	"github.com/spiffe/go-spiffe/v2/bundle/x509bundle"
	"github.com/spiffe/go-spiffe/v2/spiffeid"
	"github.com/spiffe/go-spiffe/v2/svid/x509svid"
	"github.com/spiffe/go-spiffe/v2/workloadapi"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

type stubX509Source struct {
	closed   bool
	closeErr error
}

func (s *stubX509Source) GetX509SVID() (*x509svid.SVID, error) {
	return nil, errors.New("not used by TLS config construction")
}

func (s *stubX509Source) GetX509BundleForTrustDomain(
	spiffeid.TrustDomain,
) (*x509bundle.Bundle, error) {
	return nil, errors.New("not used by TLS config construction")
}

func (s *stubX509Source) Close() error {
	s.closed = true
	return s.closeErr
}

func TestNewClientConstructsDefaultAndExplicitConfigurations(t *testing.T) {
	original := newWorkloadX509Source
	defer func() { newWorkloadX509Source = original }()

	calls := 0
	newWorkloadX509Source = func(
		ctx context.Context,
		opts ...workloadapi.X509SourceOption,
	) (*workloadapi.X509Source, error) {
		calls++
		deadline, ok := ctx.Deadline()
		require.True(t, ok)
		remaining := time.Until(deadline)
		if calls == 1 {
			assert.Empty(t, opts)
			assert.InDelta(t, (10 * time.Second).Seconds(), remaining.Seconds(), 1)
		} else {
			assert.Len(t, opts, 1)
			assert.InDelta(t, (2 * time.Second).Seconds(), remaining.Seconds(), 1)
		}
		return &workloadapi.X509Source{}, nil
	}

	defaultClient, err := NewClient(
		context.Background(),
		Config{
			Enabled:    true,
			MySpiffeID: "spiffe://university.ecosystem/ns/default/sa/api",
		},
		nil,
	)
	require.NoError(t, err)
	require.NotNil(t, defaultClient)
	assert.Equal(t, "university.ecosystem", defaultClient.trustDomain.String())
	assert.NotNil(t, defaultClient.Source())

	explicitClient, err := NewClient(
		context.Background(),
		Config{
			Enabled:        true,
			SocketPath:     "unix:///tmp/spire-agent.sock",
			TrustDomain:    "example.org",
			ConnectTimeout: 2 * time.Second,
		},
		nil,
	)
	require.NoError(t, err)
	require.NotNil(t, explicitClient)
	assert.Equal(t, "example.org", explicitClient.trustDomain.String())
	assert.Equal(t, 2, calls)
}

func TestNewClientWrapsSourceConstructionFailure(t *testing.T) {
	original := newWorkloadX509Source
	defer func() { newWorkloadX509Source = original }()

	newWorkloadX509Source = func(
		context.Context,
		...workloadapi.X509SourceOption,
	) (*workloadapi.X509Source, error) {
		return nil, errors.New("workload API unavailable")
	}

	client, err := NewClient(
		context.Background(),
		Config{Enabled: true, TrustDomain: "example.org"},
		nil,
	)

	assert.Nil(t, client)
	require.Error(t, err)
	assert.Contains(t, err.Error(), "failed to connect to SPIRE Workload API socket")
}

func TestClientBuildsAllTLSAndGRPCCredentials(t *testing.T) {
	trustDomain, err := spiffeid.TrustDomainFromString("example.org")
	require.NoError(t, err)
	source := &stubX509Source{}
	client := &Client{source: source, trustDomain: trustDomain}

	serverConfig, err := client.ServerTLSConfig()
	require.NoError(t, err)
	assert.NotNil(t, serverConfig.GetCertificate)
	assert.NotNil(t, serverConfig.VerifyPeerCertificate)

	serverConfig, err = client.ServerTLSConfig(
		"spiffe://example.org/ns/default/sa/client",
	)
	require.NoError(t, err)
	assert.NotNil(t, serverConfig)

	_, err = client.ServerTLSConfig("not-a-spiffe-id")
	require.Error(t, err)
	assert.Contains(t, err.Error(), "invalid allowed client SPIFFE ID")

	clientConfig, err := client.ClientTLSConfig(
		"spiffe://example.org/ns/default/sa/server",
	)
	require.NoError(t, err)
	assert.NotNil(t, clientConfig.GetClientCertificate)
	assert.NotNil(t, clientConfig.VerifyPeerCertificate)

	_, err = client.ClientTLSConfig("not-a-spiffe-id")
	require.Error(t, err)
	assert.Contains(t, err.Error(), "invalid expected server SPIFFE ID")

	serverCredentials, err := client.GRPCServerCredentials()
	require.NoError(t, err)
	assert.NotNil(t, serverCredentials)

	clientCredentials, err := client.GRPCClientCredentials(
		"spiffe://example.org/ns/default/sa/server",
	)
	require.NoError(t, err)
	assert.NotNil(t, clientCredentials)
}

func TestClientCloseDelegatesToSource(t *testing.T) {
	expected := errors.New("close failed")
	source := &stubX509Source{closeErr: expected}
	client := &Client{source: source}

	assert.ErrorIs(t, client.Close(), expected)
	assert.True(t, source.closed)
}
