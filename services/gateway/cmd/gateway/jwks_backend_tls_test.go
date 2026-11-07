package main

import (
	"crypto/tls"
	"testing"

	"github.com/stretchr/testify/assert"

	"github.com/university-ecosystem/gateway/internal/config"
	"github.com/university-ecosystem/gateway/middleware"
)

// AUD-373: the SPIFFE client identity may only be presented to the internal
// backend origin; a public JWKS endpoint must not receive it.
func TestConfigureJWKSBackendTLSPresentsIdentityOnlyToBackendOrigin(t *testing.T) {
	backendTLS := &tls.Config{MinVersion: tls.VersionTLS13}

	cases := []struct {
		name    string
		jwks    string
		backend string
		tlsCfg  *tls.Config
		wantTLS bool
	}{
		{name: "same origin", jwks: "https://backend:8000/.well-known/jwks.json", backend: "https://backend:8000", tlsCfg: backendTLS, wantTLS: true},
		{name: "same origin case insensitive", jwks: "HTTPS://Backend:8000/.well-known/jwks.json", backend: "https://backend:8000", tlsCfg: backendTLS, wantTLS: true},
		{name: "public endpoint", jwks: "https://api.university.example/.well-known/jwks.json", backend: "https://backend:8000", tlsCfg: backendTLS, wantTLS: false},
		{name: "different port", jwks: "https://backend:9443/.well-known/jwks.json", backend: "https://backend:8000", tlsCfg: backendTLS, wantTLS: false},
		{name: "no SPIFFE transport", jwks: "https://backend:8000/.well-known/jwks.json", backend: "https://backend:8000", tlsCfg: nil, wantTLS: false},
		{name: "empty endpoint", jwks: "", backend: "https://backend:8000", tlsCfg: backendTLS, wantTLS: false},
		{name: "malformed endpoint", jwks: "://broken", backend: "https://backend:8000", tlsCfg: backendTLS, wantTLS: false},
		{name: "malformed backend", jwks: "https://backend:8000/jwks", backend: "://broken", tlsCfg: backendTLS, wantTLS: false},
		{name: "host missing", jwks: "https:///jwks", backend: "https://backend:8000", tlsCfg: backendTLS, wantTLS: false},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			cfg := &config.Config{JWKSEndpoint: tc.jwks, BackendURL: tc.backend}
			var jwt middleware.JWTMiddleware

			configureJWKSBackendTLS(&jwt, cfg, tc.tlsCfg)

			if tc.wantTLS {
				assert.Same(t, tc.tlsCfg, jwt.JWKSTLSConfig())
				return
			}
			assert.Nil(t, jwt.JWKSTLSConfig())
		})
	}
}
