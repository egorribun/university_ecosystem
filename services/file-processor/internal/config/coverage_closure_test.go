package config

import (
	"testing"

	"github.com/stretchr/testify/require"
)

func TestValidateConfigRejectsInvalidJWKSBeforeOtherChecks(t *testing.T) {
	cfg := &Config{
		JWKSURL:        " https://issuer.example/jwks",
		MinioAccessKey: "access",
		MinioSecretKey: "secret",
		JWTSecret:      "development-secret",
		Environment:    "development",
	}

	err := validateConfig(cfg)
	require.ErrorContains(t, err, "FP_JWKS_URL")
}

func TestValidateJWKSConfigRejectsNonCanonicalActiveKID(t *testing.T) {
	cfg := &Config{JWTActiveKID: " primary "}

	err := validateJWKSConfig(cfg)
	require.ErrorContains(t, err, "FP_JWT_ACTIVE_KID")
}
