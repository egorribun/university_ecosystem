package main

import (
	"bytes"
	"context"
	"errors"
	"log/slog"
	"testing"

	"github.com/nats-io/nats.go"
	"github.com/redis/go-redis/v9"
	"github.com/stretchr/testify/require"
	"github.com/university-ecosystem/services/pkg/spiffe"
	"github.com/university-ecosystem/ws-hub/pkg/config"
	"github.com/university-ecosystem/ws-hub/pkg/hub"
)

func TestSetupHubRejectsConstructorErrorsBeforeStartingDependents(t *testing.T) {
	for _, stage := range []string{"auth", "hub"} {
		t.Run(stage, func(t *testing.T) {
			oldAuth := newBackendAuthClientFunc
			oldHub := newRuntimeHubFunc
			oldSPIFFE := configureAuthSPIFFEFunc
			oldJWKS := setupJWKSFunc
			oldSubscribe := subscribeNATSFunc
			t.Cleanup(func() {
				newBackendAuthClientFunc = oldAuth
				newRuntimeHubFunc = oldHub
				configureAuthSPIFFEFunc = oldSPIFFE
				setupJWKSFunc = oldJWKS
				subscribeNATSFunc = oldSubscribe
			})
			ctx := t.Context()
			cfg := &config.Config{BackendURL: "https://backend.test", JWKSURL: "https://backend.test/jwks"}
			rdb, revocationRDB := &redis.Client{}, &redis.Client{}
			nc := &nats.Conn{}
			want := errors.New("injected constructor failure")
			var logs bytes.Buffer
			logger := slog.New(slog.NewTextHandler(&logs, nil))
			authCalls, hubCalls, downstreamCalls := 0, 0, 0
			newBackendAuthClientFunc = func(baseURL, token string, gotRedis *redis.Client) (*hub.InternalAPIAuthClient, error) {
				authCalls++
				require.Equal(t, cfg.BackendURL, baseURL)
				require.Equal(t, cfg.InternalAuthToken, token)
				require.Same(t, rdb, gotRedis)
				if stage == "auth" {
					return nil, want
				}
				return oldAuth(baseURL, token, gotRedis)
			}
			newRuntimeHubFunc = func(gotNATS *nats.Conn, gotLogger *slog.Logger, auth hub.RoomAuthClient, gotConfig *config.Config, gotRedis *redis.Client, revocationClients ...*redis.Client) (*hub.Hub, error) {
				hubCalls++
				require.Same(t, nc, gotNATS)
				require.Same(t, logger, gotLogger)
				require.NotNil(t, auth)
				require.Same(t, cfg, gotConfig)
				require.Same(t, rdb, gotRedis)
				require.Len(t, revocationClients, 1)
				require.Same(t, revocationRDB, revocationClients[0])
				return nil, want
			}
			configureAuthSPIFFEFunc = func(*hub.InternalAPIAuthClient, *spiffe.Client, string) error {
				downstreamCalls++
				return errors.New("unexpected SPIFFE initialization")
			}
			setupJWKSFunc = func(*hub.Hub, context.Context, string) error {
				downstreamCalls++
				return errors.New("unexpected JWKS initialization")
			}
			subscribeNATSFunc = func(*hub.Hub, context.Context) error {
				downstreamCalls++
				return errors.New("unexpected subscription")
			}
			if stage == "auth" {
				cfg.SpiffeEnabled = true
			}

			got, err := setupHubWithRevocation(ctx, cfg, logger, nc, rdb, revocationRDB, &spiffe.Client{})

			require.Nil(t, got)
			require.ErrorIs(t, err, want)
			require.Equal(t, 1, authCalls)
			require.Zero(t, downstreamCalls)
			if stage == "auth" {
				require.Zero(t, hubCalls)
				require.ErrorContains(t, err, "construct backend auth client")
				require.Contains(t, logs.String(), "Failed to construct backend auth client")
			} else {
				require.Equal(t, 1, hubCalls)
				require.ErrorContains(t, err, "construct ws-hub")
				require.Contains(t, logs.String(), "Failed to construct ws-hub")
			}
		})
	}
}
