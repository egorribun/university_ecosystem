package main

import (
	"bytes"
	"errors"
	"net/url"
	"strings"
	"testing"

	"github.com/redis/go-redis/v9"
	"github.com/stretchr/testify/require"
)

func TestRedisConfigurationErrorsDoNotExposeCredentials(t *testing.T) {
	commands := [][]string{{"health"}, {"cache", "stats"}, {"cache", "clear"}, {"metrics", "show"}}
	for _, command := range commands {
		for _, source := range []string{"environment", "flag"} {
			for _, malformed := range []string{"port", "escape"} {
				t.Run(strings.Join(command, "-")+"/"+source+"/"+malformed, func(t *testing.T) {
					isolateRedisConfiguration(t)
					endpoint, marker := syntheticRedisURL(t, "redis", source)
					if malformed == "port" {
						endpoint = strings.Replace(endpoint, ":6380", ":invalid-port", 1)
					} else {
						endpoint += "/%zz"
					}
					// Real pinned parser reproduces the disclosure without any network IO.
					_, rawErr := redis.ParseURL(endpoint)
					require.Error(t, rawErr)
					require.Contains(t, rawErr.Error(), marker)

					t.Setenv("REDIS_URL", endpoint)
					args := append([]string(nil), command...)
					if source == "flag" {
						t.Setenv("REDIS_URL", "redis://localhost:6379/0")
						args = append(args, "--redis", endpoint)
					}
					newRedisClientFunc = newRedisClient
					cmd := newRootCmd()
					var output bytes.Buffer
					cmd.SetOut(&output)
					cmd.SetErr(&output)
					cmd.SetArgs(args)
					stdout, err := captureStdout(cmd.Execute)

					require.Error(t, err)
					text := output.String() + stdout + err.Error()
					require.Contains(t, text, "invalid Redis connection URL")
					require.Contains(t, text, "REDIS_URL or --redis")
					require.NotContains(t, text, endpoint)
					require.NotContains(t, text, marker)
					require.NotContains(t, text, "cli-test")
					var parseErr *url.Error
					require.False(t, errors.As(err, &parseErr))
				})
			}
		}
	}
}

func TestValidRedisCredentialsRemainAvailableOnlyToClient(t *testing.T) {
	isolateRedisConfiguration(t)
	endpoint, marker := syntheticRedisURL(t, "rediss", "valid")
	redisURL = endpoint

	client, err := newRedisClient()

	require.NoError(t, err)
	require.NotNil(t, client)
	t.Cleanup(func() { require.NoError(t, client.Close()) })
	require.Equal(t, "cli-test", client.Options().Username)
	require.Equal(t, marker+":@", client.Options().Password)
	require.Equal(t, "redis.example.test:6380", client.Options().Addr)
	require.Equal(t, 2, client.Options().DB)
	require.NotNil(t, client.Options().TLSConfig)
}
