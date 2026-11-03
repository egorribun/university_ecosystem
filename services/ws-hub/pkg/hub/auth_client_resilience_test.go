// Internal API authentication client resilience contracts.
package hub

import (
	"context"
	"crypto/tls"
	"errors"
	"net/http"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"github.com/university-ecosystem/services/pkg/spiffe"
)

type failingResponseBody struct{}

func (failingResponseBody) Read([]byte) (int, error) { return 0, errors.New("body read failed") }

func (failingResponseBody) Close() error { return nil }

func TestInternalAPIAuthClient_DoRequestResponseGuards(t *testing.T) {
	userID := "550e8400-e29b-41d4-a716-446655440000"
	roomID := "660e8400-e29b-41d4-a716-446655441111"

	t.Run("nil response is rejected", func(t *testing.T) {
		client := mustNewTestAuthClient(t, "http://auth.test", "", nil)
		previous := authHTTPDoFunc
		t.Cleanup(func() { authHTTPDoFunc = previous })
		authHTTPDoFunc = func(*http.Client, *http.Request) (*http.Response, error) {
			return nil, nil
		}
		allowed, err := client.doRequest(context.Background(), userID, roomID)
		assert.False(t, allowed)
		assert.EqualError(t, err, "nil response from auth backend")
	})

	t.Run("body read failure is non-fatal", func(t *testing.T) {
		client := mustNewTestAuthClient(t, "http://auth.test", "", nil)
		previous := authHTTPDoFunc
		t.Cleanup(func() { authHTTPDoFunc = previous })
		authHTTPDoFunc = func(_ *http.Client, req *http.Request) (*http.Response, error) {
			return &http.Response{StatusCode: http.StatusOK, Body: failingResponseBody{}, Request: req}, nil
		}
		allowed, err := client.doRequest(context.Background(), userID, roomID)
		assert.True(t, allowed)
		assert.NoError(t, err)
	})
}

func TestInternalAPIAuthClient_WithSPIFFEConfiguresTransport(t *testing.T) {
	client := mustNewTestAuthClient(t, "https://auth.test", "", nil)
	previous := authClientTLSConfigFunc
	t.Cleanup(func() { authClientTLSConfigFunc = previous })
	configured := &tls.Config{MinVersion: tls.VersionTLS13}
	authClientTLSConfigFunc = func(*spiffe.Client, string) (*tls.Config, error) {
		return configured, nil
	}

	require.NoError(t, client.WithSPIFFE(&spiffe.Client{}, "spiffe://backend"))
	transport, ok := client.httpClient.Transport.(*http.Transport)
	require.True(t, ok)
	assert.Same(t, configured, transport.TLSClientConfig)
}

func TestInternalAPIAuthClient_WithSPIFFERejectsTLSConfigurationFailure(t *testing.T) {
	client := mustNewTestAuthClient(t, "https://auth.test", "", nil)
	previous := authClientTLSConfigFunc
	t.Cleanup(func() { authClientTLSConfigFunc = previous })
	authClientTLSConfigFunc = func(*spiffe.Client, string) (*tls.Config, error) {
		return nil, errors.New("workload identity unavailable")
	}

	require.EqualError(t,
		client.WithSPIFFE(&spiffe.Client{}, "spiffe://backend"),
		"failed to create SPIFFE client TLS config for auth client: workload identity unavailable",
	)
	transport, ok := client.httpClient.Transport.(*http.Transport)
	require.True(t, ok)
	assert.Nil(t, transport.TLSClientConfig)
}

func TestInternalAPIAuthClient_WithSPIFFERejectsUninitializedIdentity(t *testing.T) {
	client := mustNewTestAuthClient(t, "https://auth.test", "", nil)
	transport, ok := client.httpClient.Transport.(*http.Transport)
	require.True(t, ok)
	originalTLS := &tls.Config{MinVersion: tls.VersionTLS13}
	transport.TLSClientConfig = originalTLS

	// Exercise the production TLS-config delegate rather than replacing its seam.
	// An unavailable workload identity must fail before changing the transport.
	err := client.WithSPIFFE(&spiffe.Client{}, "spiffe://university.ecosystem/ns/default/sa/app")

	require.EqualError(t, err,
		"failed to create SPIFFE client TLS config for auth client: spiffe client is uninitialized",
	)
	assert.Same(t, transport, client.httpClient.Transport)
	assert.Same(t, originalTLS, transport.TLSClientConfig)
}
