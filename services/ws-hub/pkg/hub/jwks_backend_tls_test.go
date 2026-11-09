package hub

import (
	"context"
	"crypto/tls"
	"crypto/x509"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"sync/atomic"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

type unexpectedJWKSTransport struct{}

func (unexpectedJWKSTransport) RoundTrip(*http.Request) (*http.Response, error) {
	return nil, http.ErrNotSupported
}

func TestBackendJWKSClientKeepsPublicTransportUnchanged(t *testing.T) {
	var nilAuth *InternalAPIAuthClient
	var nilTransport *http.Transport
	for name, auth := range map[string]RoomAuthClient{
		"no auth client":      nil,
		"typed nil auth":      nilAuth,
		"missing HTTP client": &InternalAPIAuthClient{},
		"different origin": &InternalAPIAuthClient{
			baseURL: "https://other.test", httpClient: &http.Client{},
		},
		"default transport": &InternalAPIAuthClient{
			baseURL: "https://backend.test", httpClient: &http.Client{},
		},
		"custom transport": &InternalAPIAuthClient{
			baseURL: "https://backend.test", httpClient: &http.Client{Transport: unexpectedJWKSTransport{}},
		},
		"nil transport": &InternalAPIAuthClient{
			baseURL: "https://backend.test", httpClient: &http.Client{Transport: nilTransport},
		},
		"no TLS configuration": &InternalAPIAuthClient{
			baseURL: "https://backend.test", httpClient: &http.Client{Transport: &http.Transport{}},
		},
	} {
		t.Run(name, func(t *testing.T) {
			h := &Hub{authClient: auth}
			client := h.newJWKSHTTPClient("https://backend.test/.well-known/jwks.json")
			assert.Nil(t, client.Transport)
			assert.Nil(t, client.CheckRedirect)
			assert.Equal(t, jwksRefreshTimeout, client.Timeout)
		})
	}
}

func TestSameHTTPSOrigin(t *testing.T) {
	for _, pair := range [][2]string{
		{"https://%zz", "https://backend.test"},
		{"http://backend.test", "https://backend.test"},
		{"https://", "https://backend.test"},
		{"https://user@backend.test", "https://backend.test"},
		{"https://backend.test", "https://%zz"},
		{"https://backend.test", "http://backend.test"},
		{"https://backend.test", "https://"},
		{"https://backend.test", "https://user@backend.test"},
		{"https://backend.test", "https://other.test"},
		{"https://backend.test:443", "https://backend.test:8443"},
	} {
		assert.False(t, sameHTTPSOrigin(pair[0], pair[1]), "%v", pair)
	}
	assert.True(t, sameHTTPSOrigin("https://BACKEND.test:8000/.well-known/jwks.json", "https://backend.test:8000"))
}

func TestSetupJWKSUsesBackendClientCertificate(t *testing.T) {
	var authenticatedRequests atomic.Int32
	var redirectedRequests atomic.Int32
	redirectTarget := httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		redirectedRequests.Add(1)
		w.WriteHeader(http.StatusOK)
	}))
	t.Cleanup(redirectTarget.Close)
	server := httptest.NewUnstartedServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.TLS != nil && len(r.TLS.PeerCertificates) == 1 {
			authenticatedRequests.Add(1)
		}
		if r.URL.Path == "/redirect" {
			http.Redirect(w, r, redirectTarget.URL, http.StatusFound)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = io.WriteString(w, "{\"keys\":[]}")
	}))
	server.TLS = &tls.Config{MinVersion: tls.VersionTLS13, ClientAuth: tls.RequireAnyClientCert}
	server.StartTLS()
	t.Cleanup(server.Close)
	roots := x509.NewCertPool()
	roots.AddCert(server.Certificate())
	configured := &tls.Config{
		MinVersion:         tls.VersionTLS13,
		RootCAs:            roots,
		ClientSessionCache: tls.NewLRUClientSessionCache(1),
		Certificates:       server.TLS.Certificates,
	}
	auth := &InternalAPIAuthClient{
		baseURL:    server.URL,
		httpClient: &http.Client{Transport: &http.Transport{TLSClientConfig: configured}},
	}
	h := mustNewTestHub(t, nil, slog.New(slog.NewTextHandler(io.Discard, nil)), auth, nil, nil)
	t.Cleanup(h.Stop)

	client := h.newJWKSHTTPClient(server.URL)
	transport, ok := client.Transport.(*http.Transport)
	require.True(t, ok, "internal JWKS client must carry a custom transport")
	require.NotNil(t, transport.TLSClientConfig, "internal JWKS client has no TLS configuration")
	assert.NotSame(t, configured, transport.TLSClientConfig)
	assert.True(t, transport.DisableKeepAlives)
	// Parity with the file-processor JWKS transport: both the handshake and the
	// response headers share the refresh deadline, so a stalled backend cannot
	// hold a refresh past its bound.
	assert.Equal(t, jwksRefreshTimeout, transport.TLSHandshakeTimeout)
	assert.Equal(t, jwksRefreshTimeout, transport.ResponseHeaderTimeout)
	assert.Nil(t, transport.TLSClientConfig.ClientSessionCache)
	assert.NotNil(t, configured.ClientSessionCache)
	require.NoError(t, h.SetupJWKS(context.Background(), server.URL))
	require.NoError(t, h.refreshJWKS(context.Background()))
	assert.Positive(t, authenticatedRequests.Load())
	require.NotNil(t, client.CheckRedirect)
	assert.ErrorIs(t, client.CheckRedirect(nil, nil), http.ErrUseLastResponse)
	response, err := client.Get(server.URL + "/redirect")
	require.NoError(t, err)
	require.NotNil(t, response)
	assert.Equal(t, http.StatusFound, response.StatusCode)
	require.NoError(t, response.Body.Close())
	assert.Zero(t, redirectedRequests.Load(), "redirect must not reach another origin")

	publicClient := h.newJWKSHTTPClient(redirectTarget.URL)
	assert.Nil(t, publicClient.Transport, "a different origin must not receive the workload identity")
}
