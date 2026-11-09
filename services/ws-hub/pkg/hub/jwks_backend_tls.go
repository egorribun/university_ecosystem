package hub

import (
	"net/http"
	"net/url"
	"strings"
)

// newJWKSHTTPClient reuses the authenticated backend's TLS identity only for
// the exact same HTTPS origin. Public JWKS endpoints retain system-root TLS.
// Auth transport configuration is complete before the Hub starts any workers.
func (h *Hub) newJWKSHTTPClient(endpoint string) *http.Client {
	client := &http.Client{Timeout: jwksRefreshTimeout}
	authClient, ok := h.authClient.(*InternalAPIAuthClient)
	if !ok || authClient == nil || authClient.httpClient == nil ||
		!sameHTTPSOrigin(endpoint, authClient.baseURL) {
		return client
	}
	transport, ok := authClient.httpClient.Transport.(*http.Transport)
	if !ok || transport == nil {
		return client
	}
	// Every low-volume refresh reauthenticates the current SVID and bundle.
	// Clone returns nil when no TLS configuration is installed.
	clientTLS := transport.TLSClientConfig.Clone()
	if clientTLS == nil {
		return client
	}
	clientTLS.ClientSessionCache = nil
	// Handshake and response-header waits share the refresh deadline, matching the
	// file-processor JWKS transport: a stalled backend cannot hold a refresh past it.
	client.Transport = &http.Transport{
		TLSClientConfig:       clientTLS,
		TLSHandshakeTimeout:   jwksRefreshTimeout,
		ResponseHeaderTimeout: jwksRefreshTimeout,
		DisableKeepAlives:     true,
	}
	// A redirect must never send the workload identity to a different origin.
	client.CheckRedirect = func(_ *http.Request, _ []*http.Request) error {
		return http.ErrUseLastResponse
	}
	return client
}

func sameHTTPSOrigin(endpoint, backend string) bool {
	left, err := url.Parse(endpoint)
	if err != nil {
		return false
	}
	if left.Scheme != "https" || left.Host == "" || left.User != nil {
		return false
	}
	right, err := url.Parse(backend)
	if err != nil {
		return false
	}
	return right.Scheme == "https" && right.Host != "" && right.User == nil &&
		strings.EqualFold(left.Host, right.Host)
}
