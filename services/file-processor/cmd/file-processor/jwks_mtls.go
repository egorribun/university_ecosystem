package main

import (
	"context"
	"crypto/tls"
	"errors"
	"fmt"
	"log/slog"
	"net/http"

	"github.com/university-ecosystem/file-processor/internal/config"
	"github.com/university-ecosystem/services/pkg/spiffe"
)

type jwksSPIFFESource interface {
	ClientTLSConfig(string) (*tls.Config, error)
	Close() error
}

func defaultJWKSHTTPClient(clients []*http.Client) *http.Client {
	if len(clients) > 0 && clients[0] != nil {
		return clients[0]
	}
	return &http.Client{Timeout: jwksRequestTimeout}
}

func selectJWKSHTTPClient(cfg *config.Config, clients []*http.Client) (*http.Client, error) {
	if cfg.InternalHTTPMTLSEnabled && (len(clients) == 0 || clients[0] == nil) {
		return nil, errors.New("internal JWKS mTLS requires an initialized HTTP client")
	}
	return defaultJWKSHTTPClient(clients), nil
}

var newJWKSSPIFFESource = func(ctx context.Context, cfg spiffe.Config, logger *slog.Logger) (jwksSPIFFESource, error) {
	client, err := spiffe.NewClient(ctx, cfg, logger)
	if err != nil {
		return nil, err
	}
	return client, nil
}

// newJWKSHTTPClient owns an HTTP-only Workload API source. It never toggles
// the independent gRPC listener or sends a workload certificate over plaintext.
// The returned cleanup must run after cancelling the refresher's context.
func newJWKSHTTPClient(ctx context.Context, cfg *config.Config, logger *slog.Logger) (*http.Client, func() error, error) {
	if err := config.ValidateInternalHTTPMTLS(cfg); err != nil {
		return nil, nil, err
	}
	client := &http.Client{Timeout: jwksRequestTimeout}
	if !cfg.InternalHTTPMTLSEnabled {
		return client, func() error { return nil }, nil
	}
	source, err := newJWKSSPIFFESource(ctx, spiffe.Config{
		Enabled:     true,
		SocketPath:  cfg.SpiffeEndpointSocket,
		TrustDomain: cfg.SpiffeTrustDomain,
		MySpiffeID:  cfg.SpiffeMyID,
	}, logger)
	if err != nil {
		return nil, nil, fmt.Errorf("initialize JWKS SPIFFE source: %w", err)
	}
	if source == nil {
		return nil, nil, errors.New("JWKS SPIFFE source is missing")
	}
	tlsConfig, err := source.ClientTLSConfig(cfg.BackendSpiffeID)
	if err != nil {
		return nil, nil, errors.Join(err, source.Close())
	}
	if tlsConfig == nil {
		return nil, nil, errors.Join(errors.New("JWKS SPIFFE TLS configuration is missing"), source.Close())
	}
	// Each low-volume key refresh must authenticate the current SVID and bundle.
	// Do not carry a live TLS connection or resumed session across rotation.
	clientTLS := tlsConfig.Clone()
	clientTLS.ClientSessionCache = nil
	transport := &http.Transport{
		TLSClientConfig:       clientTLS,
		TLSHandshakeTimeout:   jwksRequestTimeout,
		ResponseHeaderTimeout: jwksRequestTimeout,
		DisableKeepAlives:     true,
	}
	// Workload identities and bundles are read by the source's TLS callbacks
	// on each new handshake. No certificate snapshot or proxy-environment hop.
	client.Transport = transport
	client.CheckRedirect = func(_ *http.Request, _ []*http.Request) error {
		return http.ErrUseLastResponse
	}
	return client, func() error {
		transport.CloseIdleConnections()
		return source.Close()
	}, nil
}
