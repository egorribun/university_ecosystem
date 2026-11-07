package main

import (
	"context"
	"crypto/tls"
	"crypto/x509"
	"errors"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"sync/atomic"
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"github.com/university-ecosystem/file-processor/internal/config"
	"github.com/university-ecosystem/services/pkg/spiffe"
)

type fakeJWKSIdentitySource struct {
	tlsConfig *tls.Config
	tlsErr    error
	closeErr  error
	closed    int
	target    string
}

func (s *fakeJWKSIdentitySource) ClientTLSConfig(target string) (*tls.Config, error) {
	s.target = target
	return s.tlsConfig, s.tlsErr
}

func (s *fakeJWKSIdentitySource) Close() error {
	s.closed++
	return s.closeErr
}

func jwksMTLSConfig(endpoint string) *config.Config {
	return &config.Config{
		JWKSURL:                 endpoint,
		JWKSRefreshInterval:     1,
		InternalHTTPMTLSEnabled: true,
		BackendSpiffeID:         "spiffe://university.ecosystem/ns/default/sa/backend",
		SpiffeEndpointSocket:    "unix:///run/spire/agent.sock",
		SpiffeTrustDomain:       "university.ecosystem",
		SpiffeMyID:              "spiffe://university.ecosystem/ns/default/sa/file-processor",
	}
}

func TestJWKSHTTPClientConstructionFailures(t *testing.T) {
	ctx := context.Background()
	client, closeClient, err := newJWKSHTTPClient(ctx, nil, nil)
	require.Error(t, err)
	assert.Nil(t, client)
	assert.Nil(t, closeClient)
	// A non-nil config with an insecure endpoint must fail validation before any
	// SPIFFE source is created.
	client, closeClient, err = newJWKSHTTPClient(ctx, &config.Config{
		InternalHTTPMTLSEnabled: true,
		JWKSURL:                 "http://insecure.example/jwks",
		BackendSpiffeID:         "spiffe://university.ecosystem/ns/default/sa/backend",
	}, nil)
	require.Error(t, err)
	assert.Nil(t, client)
	assert.Nil(t, closeClient)
	client, closeClient, err = newJWKSHTTPClient(ctx, &config.Config{}, nil)
	require.NoError(t, err)
	if client == nil || closeClient == nil {
		t.Fatal("missing default JWKS client or cleanup")
	}
	assert.Nil(t, client.Transport)
	require.NoError(t, closeClient())

	defaultSource := newJWKSSPIFFESource
	t.Cleanup(func() { newJWKSSPIFFESource = defaultSource })
	_, err = defaultSource(ctx, spiffe.Config{Enabled: true, TrustDomain: "invalid/domain"}, nil)
	require.Error(t, err)
	disabledSource, err := defaultSource(ctx, spiffe.Config{}, nil)
	require.NoError(t, err)
	if disabledSource == nil {
		t.Fatal("expected nil-safe source adapter")
	}
	require.NoError(t, disabledSource.Close())

	want := errors.New("workload source unavailable")
	for _, tc := range []struct {
		name   string
		source jwksSPIFFESource
		err    error
	}{
		{name: "source error", err: want},
		{name: "missing source"},
		{name: "TLS error", source: &fakeJWKSIdentitySource{tlsErr: want, closeErr: want}},
		{name: "missing TLS", source: &fakeJWKSIdentitySource{}},
	} {
		t.Run(tc.name, func(t *testing.T) {
			newJWKSSPIFFESource = func(context.Context, spiffe.Config, *slog.Logger) (jwksSPIFFESource, error) {
				return tc.source, tc.err
			}
			client, closeClient, err := newJWKSHTTPClient(ctx, jwksMTLSConfig("https://backend/jwks"), nil)
			require.Error(t, err)
			assert.Nil(t, client)
			assert.Nil(t, closeClient)
			if source, ok := tc.source.(*fakeJWKSIdentitySource); ok {
				assert.Equal(t, 1, source.closed)
			}
		})
	}
}

func TestJWKSClientSelectionFailsClosed(t *testing.T) {
	cfg := jwksMTLSConfig("https://backend/jwks")
	for _, clients := range [][]*http.Client{nil, {nil}} {
		_, err := selectJWKSHTTPClient(cfg, clients)
		assert.Error(t, err)
		assert.Equal(t, jwksRequestTimeout, defaultJWKSHTTPClient(clients).Timeout)
	}
	provided := &http.Client{Timeout: time.Second}
	client, err := selectJWKSHTTPClient(cfg, []*http.Client{provided})
	require.NoError(t, err)
	assert.Same(t, provided, client)
	_, err = initializeJWKSKeySet(context.Background(), cfg, nil, nil)
	assert.ErrorContains(t, err, "initialized HTTP client")
	cfg.JWKSURL = "http://backend/jwks"
	_, err = initializeJWKSKeySet(context.Background(), cfg, nil, nil)
	assert.ErrorContains(t, err, "HTTPS")
}

func TestJWKSInitialAndBackgroundFetchPresentClientCertificate(t *testing.T) {
	var handshakes atomic.Int32
	var requests atomic.Int32
	var redirected atomic.Int32
	key := generateRSAKey(t)
	body := marshalJWKS(t, rsaJWK("current", &key.PublicKey))
	target := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		redirected.Add(1)
		w.WriteHeader(http.StatusOK)
	}))
	t.Cleanup(target.Close)
	server := httptest.NewUnstartedServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.TLS != nil && len(r.TLS.PeerCertificates) == 1 {
			requests.Add(1)
		}
		if r.URL.Path == "/redirect" {
			http.Redirect(w, r, target.URL, http.StatusFound)
			return
		}
		_, _ = w.Write(body)
	}))
	server.TLS = &tls.Config{MinVersion: tls.VersionTLS13, ClientAuth: tls.RequireAnyClientCert}
	server.StartTLS()
	t.Cleanup(server.Close)
	roots := x509.NewCertPool()
	roots.AddCert(server.Certificate())
	source := &fakeJWKSIdentitySource{tlsConfig: &tls.Config{
		MinVersion:         tls.VersionTLS13,
		RootCAs:            roots,
		ClientSessionCache: tls.NewLRUClientSessionCache(1),
		GetClientCertificate: func(*tls.CertificateRequestInfo) (*tls.Certificate, error) {
			handshakes.Add(1)
			return &server.TLS.Certificates[0], nil
		},
	}}
	previous := newJWKSSPIFFESource
	t.Cleanup(func() { newJWKSSPIFFESource = previous })
	cfg := jwksMTLSConfig(server.URL)
	newJWKSSPIFFESource = func(_ context.Context, identity spiffe.Config, _ *slog.Logger) (jwksSPIFFESource, error) {
		assert.True(t, identity.Enabled)
		assert.Equal(t, cfg.SpiffeEndpointSocket, identity.SocketPath)
		assert.Equal(t, cfg.SpiffeTrustDomain, identity.TrustDomain)
		assert.Equal(t, cfg.SpiffeMyID, identity.MySpiffeID)
		return source, nil
	}
	ctx, cancel := context.WithCancel(context.Background())
	t.Cleanup(cancel)
	client, closeClient, err := newJWKSHTTPClient(ctx, cfg, nil)
	require.NoError(t, err)
	if client == nil || closeClient == nil {
		t.Fatal("missing managed JWKS client or cleanup")
	}
	t.Cleanup(func() {
		cancel()
		assert.NoError(t, closeClient())
	})
	transport, ok := client.Transport.(*http.Transport)
	if !ok || transport == nil || transport.TLSClientConfig == nil {
		t.Fatal("missing internal HTTP transport")
	}
	assert.Nil(t, transport.Proxy)
	assert.True(t, transport.DisableKeepAlives)
	assert.Nil(t, transport.TLSClientConfig.ClientSessionCache)
	assert.NotNil(t, source.tlsConfig.ClientSessionCache)
	assert.NotSame(t, source.tlsConfig, transport.TLSClientConfig)
	assert.Equal(t, cfg.BackendSpiffeID, source.target)
	assert.False(t, cfg.SpiffeEnabled)
	if client.CheckRedirect == nil {
		t.Fatal("missing internal JWKS redirect guard")
	}
	assert.ErrorIs(t, client.CheckRedirect(nil, nil), http.ErrUseLastResponse)
	store, err := initializeJWKSKeySet(ctx, cfg, nil, slog.New(slog.NewTextHandler(io.Discard, nil)), client)
	require.NoError(t, err)
	assert.Equal(t, 1, store.Len())
	assert.Eventually(t, func() bool { return requests.Load() >= 2 }, 3*time.Second, 10*time.Millisecond)
	assert.GreaterOrEqual(t, handshakes.Load(), int32(2), "each refresh must perform client authentication again")
	_, err = fetchJWKSKeySet(ctx, client, server.URL+"/redirect")
	assert.ErrorContains(t, err, "HTTP status 302")
	assert.Zero(t, redirected.Load())
}

func TestRunMainClosesHTTPSourceAfterInitializationFailure(t *testing.T) {
	t.Setenv("FP_ENVIRONMENT", "development")
	t.Setenv("FP_INTERNAL_HTTP_MTLS_ENABLED", "false")
	t.Setenv("FP_JWKS_URL", "https://backend.invalid/.well-known/jwks.json")
	t.Setenv("FP_RSA_PUBLIC_KEY_PEM", "")
	t.Setenv("FP_RSA_PUBLIC_KEY_FILE", "")
	previous := newJWKSHTTPClientFunc
	t.Cleanup(func() { newJWKSHTTPClientFunc = previous })
	want := errors.New("JWKS source unavailable")
	newJWKSHTTPClientFunc = func(context.Context, *config.Config, *slog.Logger) (*http.Client, func() error, error) {
		return nil, nil, want
	}
	assert.ErrorIs(t, runMain(context.Background()), want)
	closed := false
	newJWKSHTTPClientFunc = func(ctx context.Context, _ *config.Config, _ *slog.Logger) (*http.Client, func() error, error) {
		client := &http.Client{Transport: roundTripFunc(func(*http.Request) (*http.Response, error) {
			return nil, want
		})}
		return client, func() error {
			assert.ErrorIs(t, ctx.Err(), context.Canceled)
			closed = true
			return want
		}, nil
	}
	assert.ErrorIs(t, runMain(context.Background()), want)
	assert.True(t, closed)
}
