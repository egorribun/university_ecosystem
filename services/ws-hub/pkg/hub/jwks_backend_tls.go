package hub

import (
	"net/http"
	"net/url"
	"strings"
	"time"
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
	if !ok || transport == nil || transport.TLSClientConfig == nil {
		return client
	}
	// Every low-volume refresh reauthenticates the current SVID and bundle.
	clientTLS := transport.TLSClientConfig.Clone()
	clientTLS.ClientSessionCache = nil
	client.Transport = &http.Transport{
		TLSClientConfig:     clientTLS,
		TLSHandshakeTimeout: 5 * time.Second,
		DisableKeepAlives:   true,
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
