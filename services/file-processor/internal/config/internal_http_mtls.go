package config

import (
	"errors"
	"net/url"
	"strings"
)

// ValidateInternalHTTPMTLS validates HTTP workload identity independently of
// SPIFFE-enabled gRPC, preserving the existing conventional gRPC probe contract.
func ValidateInternalHTTPMTLS(cfg *Config) error {
	if cfg == nil {
		return errors.New("file-processor configuration is nil")
	}
	if !cfg.InternalHTTPMTLSEnabled {
		return nil
	}
	endpoint, err := url.Parse(cfg.JWKSURL)
	if err != nil {
		return errors.New("FP_JWKS_URL is malformed")
	}
	if !validJWKSURL(endpoint) || endpoint.Scheme != "https" || endpoint.Hostname() == "" || strings.TrimSpace(cfg.JWKSURL) != cfg.JWKSURL || strings.ContainsAny(cfg.JWKSURL, "\r\n") {
		return errors.New("FP_JWKS_URL must use HTTPS when FP_INTERNAL_HTTP_MTLS_ENABLED=true")
	}
	if err := validateCanonicalClientURI(cfg.BackendSpiffeID); err != nil {
		return errors.New("FP_BACKEND_SPIFFE_ID must be an exact canonical SPIFFE ID")
	}
	return nil
}
