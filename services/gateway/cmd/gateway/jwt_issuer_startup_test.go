package main

import (
	"context"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/alicebob/miniredis/v2"
	"github.com/golang-jwt/jwt/v5"
	"github.com/stretchr/testify/require"

	"github.com/university-ecosystem/gateway/internal/config"
	"github.com/university-ecosystem/gateway/middleware"
)

func TestSetupRouterUsesConfiguredJWTIssuerForRequiredAndOptionalAuth(t *testing.T) {
	const (
		secret         = "gateway-custom-issuer-test-secret-32-bytes"
		customIssuer   = "https://issuer.example.test/custom"
		customAudience = "university-ecosystem-api"
		userID         = "bootstrap-issuer-user"
		hmacKey        = "gateway-internal-hmac-test-key-32-bytes"
	)

	for _, configCase := range []struct {
		name     string
		issuer   string
		audience string
		load     bool
	}{
		{name: "loaded custom issuer", issuer: customIssuer, audience: customAudience, load: true},
		{name: "direct development defaults", issuer: middleware.DefaultJWTIssuer, audience: middleware.DefaultJWTAudience},
	} {
		t.Run(configCase.name, func(t *testing.T) {
			redisServer := miniredis.RunT(t)
			type forwardedRequest struct {
				path      string
				userID    string
				signature string
			}
			observations := make(chan forwardedRequest, 8)
			backend := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				observations <- forwardedRequest{
					path:      r.URL.Path,
					userID:    r.Header.Get("X-User-ID"),
					signature: r.Header.Get("X-Internal-Signature"),
				}
				w.WriteHeader(http.StatusNoContent)
			}))
			defer backend.Close()

			var cfg *config.Config
			if configCase.load {
				t.Setenv("JWT_SECRET", secret)
				t.Setenv("JWT_ISSUER", customIssuer)
				t.Setenv("JWT_AUDIENCE", customAudience)
				t.Setenv("VITE_ENVIRONMENT", "development")
				t.Setenv("GRPC_USE_TLS", "false")
				t.Setenv("SPIFFE_ENABLED", "false")
				var err error
				cfg, err = config.Load()
				require.NoError(t, err)
				require.Equal(t, customIssuer, cfg.JWTIssuer)
				require.Equal(t, customAudience, cfg.JWTAudience)
			} else {
				cfg = &config.Config{JWTSecret: secret}
			}
			redisURL := "redis://" + redisServer.Addr() + "/0"
			cfg.RedisURL = redisURL
			cfg.RevocationRedisURL = redisURL
			cfg.BackendURL = backend.URL
			cfg.WsHubURL = backend.URL
			cfg.InternalHMACSecret = hmacKey
			cfg.RateLimitRPS = 100
			cfg.RateLimitBurst = 100
			cfg.AllowedOrigins = []string{"http://frontend.example.test"}

			ctx, cancel := context.WithCancel(context.Background())
			lifecycle := &routerLifecycle{}
			defer func() {
				cancel()
				require.NoError(t, lifecycle.Close())
			}()
			router, err := setupRouter(cfg, slog.New(slog.NewTextHandler(io.Discard, nil)), nil, nil, ctx, lifecycle)
			require.NoError(t, err)

			for _, tokenCase := range []struct {
				name          string
				issuer        string
				audience      string
				authenticated bool
			}{
				{name: "configured issuer", issuer: configCase.issuer, audience: configCase.audience, authenticated: true},
				{name: "missing issuer", audience: configCase.audience},
				{name: "foreign issuer", issuer: "https://foreign.example.test", audience: configCase.audience},
				{name: "foreign audience", issuer: configCase.issuer, audience: "foreign-audience"},
			} {
				t.Run(tokenCase.name, func(t *testing.T) {
					claims := middleware.Claims{
						RegisteredClaims: jwt.RegisteredClaims{
							Issuer:    tokenCase.issuer,
							Audience:  jwt.ClaimStrings{tokenCase.audience},
							ExpiresAt: jwt.NewNumericDate(time.Now().Add(time.Minute)),
							IssuedAt:  jwt.NewNumericDate(time.Now()),
							ID:        "bootstrap-" + configCase.name + "-" + tokenCase.name,
						},
						UserID:   userID,
						IsActive: true,
					}
					token, err := jwt.NewWithClaims(jwt.SigningMethodHS256, claims).SignedString([]byte(secret))
					require.NoError(t, err)

					requiredRequest := httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/api/admin/bootstrap", nil)
					requiredRequest.Header.Set("Authorization", "Bearer "+token)
					requiredRecorder := httptest.NewRecorder()
					router.ServeHTTP(requiredRecorder, requiredRequest)
					if tokenCase.authenticated {
						require.Equal(t, http.StatusNoContent, requiredRecorder.Code)
						observation := <-observations
						require.Equal(t, "/api/admin/bootstrap", observation.path)
						require.Equal(t, userID, observation.userID)
						require.NotEmpty(t, observation.signature)
					} else {
						require.Equal(t, http.StatusUnauthorized, requiredRecorder.Code)
					}

					optionalRequest := httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/api/v1/auth/bootstrap", nil)
					optionalRequest.Header.Set("Authorization", "Bearer "+token)
					optionalRecorder := httptest.NewRecorder()
					router.ServeHTTP(optionalRecorder, optionalRequest)
					require.Equal(t, http.StatusNoContent, optionalRecorder.Code)
					observation := <-observations
					require.Equal(t, "/api/v1/auth/bootstrap", observation.path)
					if tokenCase.authenticated {
						require.Equal(t, userID, observation.userID)
						require.NotEmpty(t, observation.signature)
					} else {
						require.Empty(t, observation.userID)
						require.Empty(t, observation.signature)
					}
				})
			}
		})
	}
}
