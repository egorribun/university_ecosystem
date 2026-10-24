package main

import (
	"bytes"
	"errors"
	"net/url"
	"os"
	"strings"
	"testing"

	"github.com/redis/go-redis/v9"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func isolateRedisConfiguration(t *testing.T) {
	t.Helper()
	oldURL, oldVerbose, oldClient := redisURL, verbose, newRedisClientFunc
	t.Cleanup(func() {
		redisURL, verbose, newRedisClientFunc = oldURL, oldVerbose, oldClient
	})
	newRedisClientFunc = func() (*redis.Client, error) {
		t.Error("help or flag parsing unexpectedly requested a Redis connection")
		return nil, errors.New("Redis connection forbidden in this test")
	}
}

func syntheticRedisURL(t *testing.T, scheme, source string) (string, string) {
	t.Helper()
	marker := strings.ReplaceAll(t.Name()+"/"+source, "/", "_")
	endpoint := url.URL{
		Scheme: scheme,
		User:   url.UserPassword("cli-test", marker+":@"),
		Host:   "redis.example.test:6380",
		Path:   "/2",
	}
	return endpoint.String(), marker
}

func TestRedisHelpDoesNotExposeEnvironment(t *testing.T) {
	cases := []struct {
		name    string
		args    []string
		wantErr bool
	}{
		{name: "root", args: []string{"--help"}},
		{name: "short help", args: []string{"-h"}},
		{name: "implicit root help", args: []string{}},
		{name: "cache group", args: []string{"cache", "--help"}},
		{name: "cache clear", args: []string{"cache", "clear", "--help"}},
		{name: "cache stats", args: []string{"cache", "stats", "--help"}},
		{name: "health", args: []string{"health", "--help"}},
		{name: "metrics group", args: []string{"metrics", "--help"}},
		{name: "metrics show", args: []string{"metrics", "show", "--help"}},
		{name: "help command", args: []string{"help", "cache", "clear"}},
		{name: "root parse error", args: []string{"--unknown-test-flag"}, wantErr: true},
		{name: "descendant parse error", args: []string{"cache", "stats", "--verbose=not-a-bool"}, wantErr: true},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			isolateRedisConfiguration(t)
			endpoint, marker := syntheticRedisURL(t, "rediss", "environment")
			t.Setenv("REDIS_URL", endpoint)
			cmd := newRootCmd()
			var output bytes.Buffer
			cmd.SetOut(&output)
			cmd.SetErr(&output)
			cmd.SetArgs(tc.args)

			err := cmd.Execute()

			if tc.wantErr {
				require.Error(t, err)
			} else {
				require.NoError(t, err)
			}
			assert.Contains(t, output.String(), "Usage:")
			assert.Contains(t, output.String(), "--redis string")
			assert.Contains(t, output.String(), "--verbose")
			assert.NotContains(t, output.String(), endpoint)
			assert.NotContains(t, output.String(), marker)
		})
	}
}

func TestRedisHelpDoesNotExposeExplicitFlag(t *testing.T) {
	isolateRedisConfiguration(t)
	endpoint, marker := syntheticRedisURL(t, "redis", "environment")
	t.Setenv("REDIS_URL", endpoint)
	flagURL, flagMarker := syntheticRedisURL(t, "rediss", "flag")
	cmd := newRootCmd()
	var output bytes.Buffer
	cmd.SetOut(&output)
	cmd.SetErr(&output)
	cmd.SetArgs([]string{"health", "--redis", flagURL, "--help"})

	require.NoError(t, cmd.Execute())

	assert.Equal(t, flagURL, redisURL)
	assert.Contains(t, output.String(), "--redis string")
	assert.NotContains(t, output.String(), endpoint)
	assert.NotContains(t, output.String(), marker)
	assert.NotContains(t, output.String(), flagURL)
	assert.NotContains(t, output.String(), flagMarker)
}

func TestRedisHelpAcceptsMalformedEnvironment(t *testing.T) {
	isolateRedisConfiguration(t)
	endpoint := "not-a-redis-url-" + t.Name()
	t.Setenv("REDIS_URL", endpoint)
	cmd := newRootCmd()
	var output bytes.Buffer
	cmd.SetOut(&output)
	cmd.SetErr(&output)
	cmd.SetArgs([]string{"--help"})

	require.NoError(t, cmd.Execute())

	assert.Contains(t, output.String(), "--redis string")
	assert.NotContains(t, output.String(), endpoint)
}

func TestRedisFlagDefaultDoesNotExposeEnvironment(t *testing.T) {
	isolateRedisConfiguration(t)
	endpoint, marker := syntheticRedisURL(t, "rediss", "environment")
	t.Setenv("REDIS_URL", endpoint)

	cmd := newRootCmd()

	flag := cmd.PersistentFlags().Lookup("redis")
	require.NotNil(t, flag)
	assert.Equal(t, endpoint, flag.Value.String())
	assert.NotContains(t, flag.DefValue, endpoint)
	assert.NotContains(t, flag.DefValue, marker)
}

func TestRedisURLPrecedence(t *testing.T) {
	cases := []struct {
		name     string
		env      string
		unsetEnv bool
		args     []string
		want     string
	}{
		{name: "unset environment", unsetEnv: true, args: []string{"--help"}, want: "redis://localhost:6379/0"},
		{name: "empty environment", args: []string{"--help"}, want: "redis://localhost:6379/0"},
		{name: "environment", env: "rediss://environment.example.test:6380/2", args: []string{"--help"}, want: "rediss://environment.example.test:6380/2"},
		{name: "explicit flag", env: "redis://environment.example.test:6379/2", args: []string{"--redis", "redis://flag.example.test:6379/3", "--help"}, want: "redis://flag.example.test:6379/3"},
		{name: "explicit empty flag", env: "redis://environment.example.test:6379/2", args: []string{"--redis=", "--help"}, want: ""},
		{name: "flag before descendant", env: "redis://environment.example.test:6379/2", args: []string{"--redis", "redis://flag.example.test:6379/3", "cache", "stats", "--help"}, want: "redis://flag.example.test:6379/3"},
		{name: "flag after descendant", env: "redis://environment.example.test:6379/2", args: []string{"cache", "stats", "--redis", "redis://flag.example.test:6379/3", "--help"}, want: "redis://flag.example.test:6379/3"},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			isolateRedisConfiguration(t)
			t.Setenv("REDIS_URL", tc.env)
			if tc.unsetEnv {
				require.NoError(t, os.Unsetenv("REDIS_URL"))
			}
			cmd := newRootCmd()
			var output bytes.Buffer
			cmd.SetOut(&output)
			cmd.SetErr(&output)
			cmd.SetArgs(tc.args)

			require.NoError(t, cmd.Execute())

			assert.Equal(t, tc.want, redisURL)
			flag := cmd.PersistentFlags().Lookup("redis")
			require.NotNil(t, flag)
			assert.Equal(t, tc.want, flag.Value.String())
		})
	}
}

func TestRedisEnvironmentIsReadAtCommandConstruction(t *testing.T) {
	isolateRedisConfiguration(t)
	t.Setenv("REDIS_URL", "redis://original.example.test:6379/2")
	cmd := newRootCmd()
	t.Setenv("REDIS_URL", "redis://changed.example.test:6379/3")
	var output bytes.Buffer
	cmd.SetOut(&output)
	cmd.SetErr(&output)
	cmd.SetArgs([]string{"health", "--help"})

	require.NoError(t, cmd.Execute())

	assert.Equal(t, "redis://original.example.test:6379/2", redisURL)
	flag := cmd.PersistentFlags().Lookup("redis")
	require.NotNil(t, flag)
	assert.Equal(t, "redis://original.example.test:6379/2", flag.Value.String())
}
