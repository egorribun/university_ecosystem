package spiffe

import (
	"context"
	"crypto/tls"
	"fmt"
	"log/slog"
	"time"

	"github.com/spiffe/go-spiffe/v2/bundle/x509bundle"
	"github.com/spiffe/go-spiffe/v2/spiffeid"
	"github.com/spiffe/go-spiffe/v2/spiffetls/tlsconfig"
	"github.com/spiffe/go-spiffe/v2/svid/x509svid"
	"github.com/spiffe/go-spiffe/v2/workloadapi"
	"google.golang.org/grpc/credentials"
)

// Config defines parameters for SPIFFE Workload API integration.
type Config struct {
	Enabled        bool          `mapstructure:"spiffe_enabled"`
	SocketPath     string        `mapstructure:"spiffe_endpoint_socket"`
	TrustDomain    string        `mapstructure:"spiffe_trust_domain"`
	MySpiffeID     string        `mapstructure:"spiffe_my_id"`
	ConnectTimeout time.Duration `mapstructure:"spiffe_connect_timeout"`
}

// Client manages the lifecycle of the SPIFFE X.509 source and builds mTLS configs.
type Client struct {
	source         x509Source
	workloadSource *workloadapi.X509Source
	trustDomain    spiffeid.TrustDomain
}

type x509Source interface {
	x509svid.Source
	x509bundle.Source
	Close() error
}

var newWorkloadX509Source = workloadapi.NewX509Source

// NewClient initializes an X509Source connected to the SPIRE Workload API.
func NewClient(ctx context.Context, cfg Config, logger *slog.Logger) (*Client, error) {
	if logger == nil {
		logger = slog.Default()
	}

	if !cfg.Enabled {
		logger.InfoContext(ctx, "SPIFFE is disabled; using fallback non-SPIFFE transports")
		return nil, nil
	}

	if cfg.TrustDomain == "" {
		cfg.TrustDomain = "university.ecosystem"
	}

	td, err := spiffeid.TrustDomainFromString(cfg.TrustDomain)
	if err != nil {
		return nil, fmt.Errorf("invalid SPIFFE trust domain %q: %w", cfg.TrustDomain, err)
	}

	if cfg.MySpiffeID != "" {
		_, err = spiffeid.FromString(cfg.MySpiffeID)
		if err != nil {
			return nil, fmt.Errorf("invalid self SPIFFE ID %q: %w", cfg.MySpiffeID, err)
		}
	}

	opts := []workloadapi.X509SourceOption{}
	if cfg.SocketPath != "" {
		opts = append(opts, workloadapi.WithClientOptions(workloadapi.WithAddr(cfg.SocketPath)))
	}

	timeout := cfg.ConnectTimeout
	if timeout == 0 {
		timeout = 10 * time.Second
	}

	initCtx, cancel := context.WithTimeout(ctx, timeout)
	defer cancel()

	source, err := newWorkloadX509Source(initCtx, opts...)
	if err != nil {
		return nil, fmt.Errorf("failed to connect to SPIRE Workload API socket: %w", err)
	}

	logger.InfoContext(ctx, "SPIFFE X509Source initialized successfully",
		"trust_domain", cfg.TrustDomain,
		"my_id", cfg.MySpiffeID,
	)

	return &Client{
		source:         source,
		workloadSource: source,
		trustDomain:    td,
	}, nil
}

// Close gracefully closes the X509Source connection.
func (c *Client) Close() error {
	if c == nil || c.source == nil {
		return nil
	}
	return c.source.Close()
}

// Source returns the underlying X509Source instance.
func (c *Client) Source() *workloadapi.X509Source {
	if c == nil {
		return nil
	}
	return c.workloadSource
}

// ServerTLSConfig creates a *tls.Config for mTLS servers that verifies client SVIDs.
func (c *Client) ServerTLSConfig(allowedClientIDs ...string) (*tls.Config, error) {
	if c == nil || c.source == nil {
		return nil, fmt.Errorf("spiffe client is uninitialized")
	}

	var authorizer tlsconfig.Authorizer
	if len(allowedClientIDs) == 0 {
		authorizer = tlsconfig.AuthorizeMemberOf(c.trustDomain)
	} else {
		spiffeIDs := make([]spiffeid.ID, 0, len(allowedClientIDs))
		for _, idStr := range allowedClientIDs {
			id, err := spiffeid.FromString(idStr)
			if err != nil {
				return nil, fmt.Errorf("invalid allowed client SPIFFE ID %q: %w", idStr, err)
			}
			spiffeIDs = append(spiffeIDs, id)
		}
		authorizer = tlsconfig.AuthorizeOneOf(spiffeIDs...)
	}

	return tlsconfig.MTLSServerConfig(c.source, c.source, authorizer), nil
}

// ClientTLSConfig creates a *tls.Config for mTLS clients verifying target server SVIDs.
func (c *Client) ClientTLSConfig(expectedServerID string) (*tls.Config, error) {
	if c == nil || c.source == nil {
		return nil, fmt.Errorf("spiffe client is uninitialized")
	}

	targetID, err := spiffeid.FromString(expectedServerID)
	if err != nil {
		return nil, fmt.Errorf("invalid expected server SPIFFE ID %q: %w", expectedServerID, err)
	}

	authorizer := tlsconfig.AuthorizeID(targetID)
	return tlsconfig.MTLSClientConfig(c.source, c.source, authorizer), nil
}

// GRPCServerCredentials returns gRPC transport credentials configured for mTLS server authentication.
func (c *Client) GRPCServerCredentials(allowedClientIDs ...string) (credentials.TransportCredentials, error) {
	tlsCfg, err := c.ServerTLSConfig(allowedClientIDs...)
	if err != nil {
		return nil, err
	}
	return credentials.NewTLS(tlsCfg), nil
}

// GRPCClientCredentials returns gRPC transport credentials configured for mTLS client authentication.
func (c *Client) GRPCClientCredentials(expectedServerID string) (credentials.TransportCredentials, error) {
	tlsCfg, err := c.ClientTLSConfig(expectedServerID)
	if err != nil {
		return nil, err
	}
	return credentials.NewTLS(tlsCfg), nil
}
