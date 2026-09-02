package config

import (
	"fmt"
	"net/url"
	"path"
	"regexp"
	"strings"

	"github.com/spf13/viper"
)

var (
	bindEnvFunc         = func(input ...string) error { return viper.BindEnv(input...) }
	unmarshalConfigFunc = func(rawVal any) error { return viper.Unmarshal(rawVal) }
	spiffePathPattern   = regexp.MustCompile(`^/[A-Za-z0-9._~-]+(?:/[A-Za-z0-9._~-]+)*$`)
)

// Config holds processor configuration.
type Config struct {
	GRPCPort     string `mapstructure:"grpc_port"`
	NatsURL      string `mapstructure:"nats_url"`
	TemporalHost string `mapstructure:"temporal_host"`
	// TemporalTLSDisabled is true only for the plaintext local development
	// server. Managed/staging/production Temporal endpoints must use TLS.
	TemporalTLSDisabled bool `mapstructure:"temporal_tls_disabled"`
	// Wave 141 SW5 — Path (a-auth): path to file containing the Temporal service
	// token (RS256 JWT minted by start-docker.ps1's New-TemporalServiceToken at
	// W141 SW4). Read once at startup in connectTemporal. Empty value = no auth
	// (development fallback; pre-W141 W139 SW2 behavior). Closes W137 §Honesty
	// #5 + W140 NEW #6 (Path (a-auth) full closure with SW3 image swap + SW4
	// token mint).
	TemporalAPIKeyFile string `mapstructure:"temporal_api_key_file"`
	MinioBucket        string `mapstructure:"minio_bucket"`
	MinioEndpoint      string `mapstructure:"minio_endpoint"`
	MinioAccessKey     string `mapstructure:"minio_access_key"`
	MinioSecretKey     string `mapstructure:"minio_secret_key"`
	MinioSecure        bool   `mapstructure:"minio_secure"`
	GraphQLPort        string `mapstructure:"graphql_port"`
	JWTSecret          string `mapstructure:"jwt_secret"`
	// TD-W18-01 (audit 2026-03-23 Wave 18): RSA public key PEM for RS256 verification.
	// When set, both RS256 and HS256 tokens are accepted (RS256 preferred).
	// This brings file-processor into parity with ws-hub and gateway.
	RSAPublicKeyPEM  string `mapstructure:"rsa_public_key_pem"`
	RSAPublicKeyFile string `mapstructure:"rsa_public_key_file"`
	SentryDSN        string `mapstructure:"sentry_dsn"`
	Environment      string `mapstructure:"environment"`

	// OTLPEndpoint is the OpenTelemetry collector gRPC endpoint.
	// Defaults to the Tempo service shipped by the local Compose stack.
	OTLPEndpoint string `mapstructure:"otlp_endpoint"`
	// OTLPInsecure disables TLS for the OTLP exporter.
	// MUST be false in production — use TLS with a trusted CA or mTLS.
	OTLPInsecure bool `mapstructure:"otlp_insecure"`

	// SPIFFE Workload API & mTLS configuration
	SpiffeEnabled          bool     `mapstructure:"spiffe_enabled"`
	SpiffeEndpointSocket   string   `mapstructure:"spiffe_endpoint_socket"`
	SpiffeTrustDomain      string   `mapstructure:"spiffe_trust_domain"`
	SpiffeMyID             string   `mapstructure:"spiffe_my_id"`
	AllowedClientSpiffeIDs []string `mapstructure:"allowed_client_spiffe_ids"`

	GRPCTLSCertFile  string `mapstructure:"grpc_tls_cert_file"`
	GRPCTLSKeyFile   string `mapstructure:"grpc_tls_key_file"`
	GRPCClientCAFile string `mapstructure:"grpc_client_ca_file"`
	// GRPCAllowedClientURIs is the exact URI SAN allowlist for conventional
	// certificate-backed mTLS clients. CA membership alone is not a workload
	// identity because a CA can issue certificates to multiple services.
	GRPCAllowedClientURIs []string `mapstructure:"grpc_allowed_client_uris"`
}

// Load loads the configuration from environment variables using Viper.
func Load() (*Config, error) {
	configureViper()
	if err := bindConfigEnvironment(); err != nil {
		return nil, err
	}

	var cfg Config
	if err := unmarshalConfigFunc(&cfg); err != nil {
		return nil, err
	}
	if err := validateConfig(&cfg); err != nil {
		return nil, err
	}
	return &cfg, nil
}

func configureViper() {
	viper.Reset()
	viper.AllowEmptyEnv(true)
	// LOW-W19: set prefix "FP" so this service reads FP_GRPC_PORT etc. and does
	// not accidentally consume unrelated env vars from the host environment.
	// Existing deployments that use un-prefixed vars must be updated to add "FP_".
	viper.SetEnvPrefix("FP")
	viper.AutomaticEnv()

	// Default values
	viper.SetDefault("grpc_port", "50051")
	viper.SetDefault("graphql_port", "8080")
	viper.SetDefault("nats_url", "nats://nats:4222")
	viper.SetDefault("temporal_host", "temporal:7233")
	viper.SetDefault("temporal_tls_disabled", true)
	viper.SetDefault("minio_bucket", "uploads")
	viper.SetDefault("minio_endpoint", "minio:9000")
	viper.SetDefault("minio_access_key", "minioadmin")
	viper.SetDefault("minio_secret_key", "minioadmin")
	viper.SetDefault("minio_secure", false)
	viper.SetDefault("spiffe_enabled", false)
	viper.SetDefault("environment", "development")
	viper.SetDefault("spiffe_endpoint_socket", "unix:///run/spire/sockets/agent.sock")
	viper.SetDefault("spiffe_trust_domain", "university.ecosystem")
	viper.SetDefault("spiffe_my_id", "spiffe://university.ecosystem/ns/default/sa/file-processor")
	viper.SetDefault("allowed_client_spiffe_ids", []string{"spiffe://university.ecosystem/ns/default/sa/gateway"})
	viper.SetDefault("grpc_allowed_client_uris", []string{})

	viper.SetDefault("otlp_endpoint", "tempo:4317")
	// Default to insecure only in development; production deployments must
	// set OTLP_INSECURE=false and provide a valid TLS CA / cert-manager cert.
	viper.SetDefault("otlp_insecure", true)
}

func bindConfigEnvironment() error {
	bindEnvs := map[string]string{
		"grpc_port":                 "GRPC_PORT",
		"nats_url":                  "NATS_URL",
		"temporal_host":             "TEMPORAL_HOST",
		"temporal_api_key_file":     "TEMPORAL_API_KEY_FILE",
		"temporal_tls_disabled":     "TEMPORAL_TLS_DISABLED",
		"minio_bucket":              "MINIO_BUCKET",
		"minio_endpoint":            "MINIO_ENDPOINT",
		"minio_access_key":          "MINIO_ACCESS_KEY",
		"minio_secret_key":          "MINIO_SECRET_KEY",
		"minio_secure":              "MINIO_SECURE",
		"jwt_secret":                "JWT_SECRET",
		"rsa_public_key_pem":        "RSA_PUBLIC_KEY_PEM",
		"rsa_public_key_file":       "RSA_PUBLIC_KEY_FILE",
		"sentry_dsn":                "SENTRY_DSN",
		"otlp_endpoint":             "OTLP_ENDPOINT",
		"otlp_insecure":             "OTLP_INSECURE",
		"spiffe_enabled":            "SPIFFE_ENABLED",
		"spiffe_endpoint_socket":    "SPIFFE_ENDPOINT_SOCKET",
		"spiffe_trust_domain":       "SPIFFE_TRUST_DOMAIN",
		"spiffe_my_id":              "SPIFFE_MY_ID",
		"allowed_client_spiffe_ids": "ALLOWED_CLIENT_SPIFFE_IDS",
		"grpc_tls_cert_file":        "GRPC_TLS_CERT_FILE",
		"grpc_tls_key_file":         "GRPC_TLS_KEY_FILE",
		"grpc_client_ca_file":       "GRPC_CLIENT_CA_FILE",
		"grpc_allowed_client_uris":  "GRPC_ALLOWED_CLIENT_URIS",
	}

	for key, env := range bindEnvs {
		if err := bindEnvFunc(key, env); err != nil {
			return fmt.Errorf("failed to bind env %s: %w", env, err)
		}
	}
	return nil
}

func validateConfig(cfg *Config) error {
	if cfg.MinioAccessKey == "" || cfg.MinioSecretKey == "" {
		return fmt.Errorf("MINIO_ACCESS_KEY and MINIO_SECRET_KEY are required")
	}

	if cfg.JWTSecret == "" && cfg.RSAPublicKeyPEM == "" && cfg.RSAPublicKeyFile == "" {
		return fmt.Errorf(
			"one of FP_JWT_SECRET, FP_RSA_PUBLIC_KEY_PEM, or FP_RSA_PUBLIC_KEY_FILE must be set",
		)
	}

	environment := strings.ToLower(strings.TrimSpace(cfg.Environment))
	if environment != "production" && environment != "staging" {
		return nil
	}
	return validateReleaseConfig(cfg, environment)
}

func validateReleaseConfig(cfg *Config, environment string) error {
	if !cfg.MinioSecure {
		return fmt.Errorf("FP_MINIO_SECURE=true is required in %s", environment)
	}
	if cfg.TemporalTLSDisabled {
		return fmt.Errorf("FP_TEMPORAL_TLS_DISABLED=false is required in %s", environment)
	}
	if cfg.OTLPInsecure {
		return fmt.Errorf("FP_OTLP_INSECURE=false is required in %s", environment)
	}
	if cfg.SpiffeEnabled {
		return nil
	}
	required := []struct {
		name  string
		value string
	}{
		{name: "FP_GRPC_TLS_CERT_FILE", value: cfg.GRPCTLSCertFile},
		{name: "FP_GRPC_TLS_KEY_FILE", value: cfg.GRPCTLSKeyFile},
		{name: "FP_GRPC_CLIENT_CA_FILE", value: cfg.GRPCClientCAFile},
	}
	for _, item := range required {
		if strings.TrimSpace(item.value) == "" {
			return fmt.Errorf("%s is required for conventional gRPC mTLS in %s", item.name, environment)
		}
	}
	return ValidateGRPCAllowedClientURIs(cfg.GRPCAllowedClientURIs)
}

// ValidateGRPCAllowedClientURIs rejects ambiguous or aliasable identities.
// URI SANs are compared byte-for-byte during the TLS handshake, so release
// configuration must use a canonical absolute URI with an authority and path.
func ValidateGRPCAllowedClientURIs(values []string) error {
	if len(values) == 0 {
		return fmt.Errorf("FP_GRPC_ALLOWED_CLIENT_URIS must contain at least one exact URI SAN")
	}
	seen := make(map[string]struct{}, len(values))
	for _, value := range values {
		if err := validateCanonicalClientURI(value); err != nil {
			return err
		}
		if _, duplicate := seen[value]; duplicate {
			return fmt.Errorf("FP_GRPC_ALLOWED_CLIENT_URIS contains duplicate URI %q", value)
		}
		seen[value] = struct{}{}
	}
	return nil
}

func validateCanonicalClientURI(value string) error {
	if value == "" || strings.TrimSpace(value) != value {
		return fmt.Errorf("FP_GRPC_ALLOWED_CLIENT_URIS contains a blank or non-canonical URI")
	}
	parsed, err := url.Parse(value)
	if err != nil || !hasCanonicalSPIFFEAuthority(parsed) || !hasCanonicalSPIFFEPath(parsed, value) {
		return fmt.Errorf("FP_GRPC_ALLOWED_CLIENT_URIS contains invalid exact URI %q", value)
	}
	return nil
}

func hasCanonicalSPIFFEAuthority(parsed *url.URL) bool {
	return parsed.Scheme == "spiffe" && parsed.Host != "" &&
		parsed.Host == strings.ToLower(parsed.Host) && parsed.Host == parsed.Hostname() &&
		validSPIFFETrustDomain(parsed.Host) && parsed.User == nil && parsed.Opaque == "" &&
		parsed.RawQuery == "" && parsed.Fragment == "" && parsed.RawFragment == "" && !parsed.ForceQuery
}

func hasCanonicalSPIFFEPath(parsed *url.URL, value string) bool {
	return !strings.Contains(value, "%") && path.Clean(parsed.Path) == parsed.Path &&
		spiffePathPattern.MatchString(parsed.Path) && parsed.String() == value
}

func validSPIFFETrustDomain(value string) bool {
	if len(value) > 253 {
		return false
	}
	for _, label := range strings.Split(value, ".") {
		if len(label) == 0 || len(label) > 63 || !isLowerAlphaNumeric(label[0]) || !isLowerAlphaNumeric(label[len(label)-1]) {
			return false
		}
		for index := 1; index < len(label)-1; index++ {
			if !isLowerAlphaNumeric(label[index]) && label[index] != '-' {
				return false
			}
		}
	}
	return true
}

func isLowerAlphaNumeric(value byte) bool {
	return value >= 'a' && value <= 'z' || value >= '0' && value <= '9'
}
