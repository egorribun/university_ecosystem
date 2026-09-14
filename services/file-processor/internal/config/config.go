package config

import (
	"errors"
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

const (
	defaultJWKSRefreshIntervalSeconds = 300
	maxJWKSRefreshIntervalSeconds     = 24 * 60 * 60
	maxJWTActiveKIDLength             = 128
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
	// ProcessingCapabilitySecret authenticates backend-issued, object-bound
	// processing capabilities at every ingress (gRPC, GraphQL and NATS).
	ProcessingCapabilitySecret string `mapstructure:"processing_capability_secret"`
	GraphQLPort                string `mapstructure:"graphql_port"`
	JWTSecret                  string `mapstructure:"jwt_secret"`
	// JWTAudience and JWTIssuer must match the backend token issuer. Issuer is
	// mandatory for staging/production; development uses the same local default
	// so every environment exercises the same claim shape.
	JWTAudience string `mapstructure:"jwt_audience"`
	JWTIssuer   string `mapstructure:"jwt_issuer"`
	// JWKSURL is the backend's public RSA key-set endpoint. When configured,
	// file-processor performs a bounded startup fetch and then refreshes the
	// complete key set in the background. The previous accepted snapshot is
	// retained when a later refresh fails (last-known-good semantics).
	JWKSURL string `mapstructure:"jwks_url"`
	// JWKSRefreshInterval is expressed in seconds to keep the FP_ environment
	// contract consistent with the gateway. Values <= 0 use the safe default.
	JWKSRefreshInterval int `mapstructure:"jwks_refresh_interval"`
	// JWTActiveKID names the static PEM fallback key and is also the expected
	// key id when a release has not yet received a JWKS snapshot. It is not used
	// to select a key from a fetched set; every fetched token must resolve its
	// own exact JOSE kid.
	JWTActiveKID       string `mapstructure:"jwt_active_kid"`
	RevocationRedisURL string `mapstructure:"revocation_redis_url"`
	// TD-W18-01 (audit 2026-03-23 Wave 18): RSA public key PEM for RS256
	// verification. When configured, authentication is RS256-only; HS256 remains
	// available only in development/test when no RSA trust root is present.
	// Release deployments must use the bounded JWKS/key-set path or this static
	// public key as an explicitly reviewed trust root.
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
	viper.SetDefault("jwt_audience", "university-ecosystem-api")
	viper.SetDefault("jwt_issuer", "university-ecosystem")
	viper.SetDefault("jwks_url", "")
	viper.SetDefault("jwks_refresh_interval", 300)
	viper.SetDefault("jwt_active_kid", "primary")
	viper.SetDefault("revocation_redis_url", "")
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
		"grpc_port":                    "GRPC_PORT",
		"nats_url":                     "NATS_URL",
		"temporal_host":                "TEMPORAL_HOST",
		"temporal_api_key_file":        "TEMPORAL_API_KEY_FILE",
		"temporal_tls_disabled":        "TEMPORAL_TLS_DISABLED",
		"minio_bucket":                 "MINIO_BUCKET",
		"minio_endpoint":               "MINIO_ENDPOINT",
		"minio_access_key":             "MINIO_ACCESS_KEY",
		"minio_secret_key":             "MINIO_SECRET_KEY",
		"minio_secure":                 "MINIO_SECURE",
		"processing_capability_secret": "PROCESSING_CAPABILITY_SECRET",
		"jwt_secret":                   "JWT_SECRET",
		"jwt_audience":                 "JWT_AUDIENCE",
		"jwt_issuer":                   "JWT_ISSUER",
		"jwks_url":                     "JWKS_URL",
		"jwks_refresh_interval":        "JWKS_REFRESH_INTERVAL",
		"jwt_active_kid":               "JWT_ACTIVE_KID",
		"revocation_redis_url":         "REVOCATION_REDIS_URL",
		"rsa_public_key_pem":           "RSA_PUBLIC_KEY_PEM",
		"rsa_public_key_file":          "RSA_PUBLIC_KEY_FILE",
		"sentry_dsn":                   "SENTRY_DSN",
		"otlp_endpoint":                "OTLP_ENDPOINT",
		"otlp_insecure":                "OTLP_INSECURE",
		"spiffe_enabled":               "SPIFFE_ENABLED",
		"spiffe_endpoint_socket":       "SPIFFE_ENDPOINT_SOCKET",
		"spiffe_trust_domain":          "SPIFFE_TRUST_DOMAIN",
		"spiffe_my_id":                 "SPIFFE_MY_ID",
		"allowed_client_spiffe_ids":    "ALLOWED_CLIENT_SPIFFE_IDS",
		"grpc_tls_cert_file":           "GRPC_TLS_CERT_FILE",
		"grpc_tls_key_file":            "GRPC_TLS_KEY_FILE",
		"grpc_client_ca_file":          "GRPC_CLIENT_CA_FILE",
		"grpc_allowed_client_uris":     "GRPC_ALLOWED_CLIENT_URIS",
	}

	for key, env := range bindEnvs {
		if err := bindEnvFunc(key, env); err != nil {
			return fmt.Errorf("failed to bind env %s: %w", env, err)
		}
	}
	return nil
}

func validateConfig(cfg *Config) error {
	if err := validateJWKSConfig(cfg); err != nil {
		return err
	}
	if cfg.MinioAccessKey == "" || cfg.MinioSecretKey == "" {
		return fmt.Errorf("MINIO_ACCESS_KEY and MINIO_SECRET_KEY are required")
	}

	if cfg.JWTSecret == "" && cfg.RSAPublicKeyPEM == "" && cfg.RSAPublicKeyFile == "" && cfg.JWKSURL == "" {
		return fmt.Errorf(
			"one of FP_JWT_SECRET, FP_RSA_PUBLIC_KEY_PEM, FP_RSA_PUBLIC_KEY_FILE, or FP_JWKS_URL must be set",
		)
	}

	environment := strings.ToLower(strings.TrimSpace(cfg.Environment))
	switch environment {
	case "development", "test", "testing":
		return nil
	case "production", "staging":
		return validateReleaseConfig(cfg, environment)
	default:
		// Unknown values must not silently select the permissive development
		// branch. A typo in a deployment environment would otherwise disable
		// every release-only transport and secret guard.
		return fmt.Errorf("FP_ENVIRONMENT must be one of: development, test, testing, staging, production")
	}
}

func validateReleaseConfig(cfg *Config, environment string) error {
	if err := validateProcessingCapabilitySecret(cfg.ProcessingCapabilitySecret); err != nil {
		return fmt.Errorf("%w in %s", err, environment)
	}
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

// validateJWKSConfig validates only non-secret key-discovery configuration.
// Keeping this check at process startup prevents a malformed endpoint from
// silently disabling refresh, while the fetcher itself still applies strict
// response-size and key-shape limits. An explicitly blank active kid uses the
// canonical local fallback name so static PEM deployments remain compatible
// with the backend's default JWT kid.
func validateJWKSConfig(cfg *Config) error {
	if cfg == nil {
		return fmt.Errorf("file-processor configuration is nil")
	}
	if err := validateJWKSURL(cfg); err != nil {
		return err
	}
	if err := normalizeJWKSRefreshInterval(cfg); err != nil {
		return err
	}
	return normalizeActiveKID(cfg)
}

func validateJWKSURL(cfg *Config) error {
	const message = "FP_JWKS_URL must be an absolute HTTP(S) URL without credentials, query, or fragment"
	if strings.TrimSpace(cfg.JWKSURL) != cfg.JWKSURL {
		return errors.New(message)
	}
	if cfg.JWKSURL == "" {
		return nil
	}
	parsed, err := url.Parse(cfg.JWKSURL)
	if err != nil || !validJWKSURL(parsed) || strings.ContainsAny(cfg.JWKSURL, "\r\n") {
		return errors.New(message)
	}
	return nil
}

func validJWKSURL(parsed *url.URL) bool {
	return parsed != nil && (parsed.Scheme == "http" || parsed.Scheme == "https") && parsed.Host != "" && parsed.User == nil && parsed.RawQuery == "" && parsed.Fragment == ""
}

func normalizeJWKSRefreshInterval(cfg *Config) error {
	if cfg.JWKSRefreshInterval <= 0 {
		cfg.JWKSRefreshInterval = defaultJWKSRefreshIntervalSeconds
	}
	if cfg.JWKSRefreshInterval > maxJWKSRefreshIntervalSeconds {
		return fmt.Errorf("FP_JWKS_REFRESH_INTERVAL must be between 1 and %d seconds", maxJWKSRefreshIntervalSeconds)
	}
	return nil
}

func normalizeActiveKID(cfg *Config) error {
	const message = "FP_JWT_ACTIVE_KID must be a non-empty value of at most %d characters without control characters"
	if strings.TrimSpace(cfg.JWTActiveKID) != cfg.JWTActiveKID {
		return fmt.Errorf(message, maxJWTActiveKIDLength)
	}
	if cfg.JWTActiveKID == "" {
		cfg.JWTActiveKID = "primary"
	}
	if len(cfg.JWTActiveKID) > maxJWTActiveKIDLength || strings.TrimSpace(cfg.JWTActiveKID) != cfg.JWTActiveKID || strings.ContainsAny(cfg.JWTActiveKID, "\r\n\x00") {
		return fmt.Errorf(message, maxJWTActiveKIDLength)
	}
	return nil
}

// validateProcessingCapabilitySecret mirrors the gateway's trust-boundary
// validator. A length check alone accepts predictable values such as repeated
// bytes or copied examples; because the gateway mints and the file processor
// verifies the same MAC, both sides must fail closed on the same weak key
// classes without ever echoing the configured secret in an error.
func validateProcessingCapabilitySecret(secret string) error {
	name := "FP_PROCESSING_CAPABILITY_SECRET"
	normalized := strings.TrimSpace(secret)
	if len([]byte(normalized)) < 32 {
		return fmt.Errorf("%s must contain at least 32 bytes of entropy", name)
	}
	secretBytes := []byte(normalized)
	distinct := make(map[byte]struct{}, len(secretBytes))
	for _, value := range secretBytes {
		distinct[value] = struct{}{}
	}
	lower := strings.ToLower(normalized)
	placeholders := []string{
		"change_me",
		"change-me",
		"changeme",
		"placeholder",
		"example",
		"your-secret",
		"internal_hmac_secret",
		"internal-hmac-secret",
		"file-processing-capability-secret",
		"test-secret",
		"dummy-secret",
	}
	for _, placeholder := range placeholders {
		if strings.Contains(lower, placeholder) {
			return fmt.Errorf("%s must contain at least 32 bytes of entropy; placeholder or repeated values are not allowed", name)
		}
	}
	if len(distinct) < 4 || isRepeatedSecret(secretBytes) {
		return fmt.Errorf("%s must contain at least 32 bytes of entropy; placeholder or repeated values are not allowed", name)
	}
	return nil
}

func isRepeatedSecret(value []byte) bool {
	for blockLen := 1; blockLen <= 8; blockLen++ {
		if len(value)%blockLen != 0 || len(value)/blockLen < 2 {
			continue
		}
		block := value[:blockLen]
		repeated := true
		for offset := blockLen; offset < len(value); offset += blockLen {
			for index := range block {
				if value[offset+index] != block[index] {
					repeated = false
					break
				}
			}
			if !repeated {
				break
			}
		}
		if repeated {
			return true
		}
	}
	return false
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
