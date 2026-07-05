package main

import (
	"bytes"
	"context"
	"errors"
	"fmt"
	"net"
	"os"
	"os/exec"
	"strings"
	"testing"
	"time"

	"github.com/redis/go-redis/v9"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// respondRESP writes a canned RESP reply for the given uppercased request
// fragment, covering only the commands uni-cli exercises. Extracted from the
// accept loop to keep setupMockRedisServer under the cognitive-complexity gate.
func respondRESP(write func(string), upperPart string) {
	switch {
	case strings.Contains(upperPart, "HELLO"):
		write("-ERR unknown command 'HELLO'\r\n")
	case strings.Contains(upperPart, "CLIENT"):
		write("-ERR unknown command 'CLIENT'\r\n")
	case strings.Contains(upperPart, "PING"):
		write("+PONG\r\n")
	case strings.Contains(upperPart, "INFO"):
		if strings.Contains(upperPart, "STATS") {
			s := "# Stats\r\ntotal_connections:42\r\n"
			write(fmt.Sprintf("$%d\r\n%s\r\n", len(s), s))
		} else {
			s := "# Memory\r\nused_memory_human:10.5M\r\n"
			write(fmt.Sprintf("$%d\r\n%s\r\n", len(s), s))
		}
	case strings.Contains(upperPart, "KEYS"):
		if strings.Contains(upperPart, "NONEXISTENT") {
			write("*0\r\n")
		} else {
			write("*2\r\n$11\r\ncache:key_1\r\n$11\r\ncache:key_2\r\n")
		}
	case strings.Contains(upperPart, "DEL"):
		write(":2\r\n")
	case strings.Contains(upperPart, "DBSIZE"):
		write(":5\r\n")
	default:
		write("+OK\r\n")
	}
}

// Setup mock RESP server to simulate Redis without external dependencies.
func setupMockRedisServer(t *testing.T) (string, func()) {
	var lc net.ListenConfig
	ln, err := lc.Listen(context.Background(), "tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("failed to start mock redis server: %v", err)
	}

	go func() {
		for {
			conn, err := ln.Accept()
			if err != nil {
				return
			}
			go func(c net.Conn) {
				defer func() { _ = c.Close() }()                      //nolint:errcheck // mock server cleanup
				write := func(s string) { _, _ = c.Write([]byte(s)) } //nolint:errcheck // mock server best-effort write
				buf := make([]byte, 2048)
				for {
					n, err := c.Read(buf)
					if err != nil {
						return
					}
					// Split pipelined RESP commands (each starts with '*').
					for _, part := range strings.Split(string(buf[:n]), "*") {
						if part == "" {
							continue
						}
						respondRESP(write, strings.ToUpper(part))
					}
				}
			}(conn)
		}
	}()

	addr := ln.Addr().String()
	redisURLStr := fmt.Sprintf("redis://%s", addr)

	return redisURLStr, func() {
		_ = ln.Close() //nolint:errcheck // mock server cleanup
	}
}

func captureStdout(f func() error) (string, error) {
	old := os.Stdout
	r, w, _ := os.Pipe() //nolint:errcheck // os.Pipe failure is not a realistic test condition
	os.Stdout = w

	err := f()

	_ = w.Close() //nolint:errcheck // best-effort close of pipe writer
	os.Stdout = old

	var buf bytes.Buffer
	_, _ = buf.ReadFrom(r) //nolint:errcheck // best-effort read of captured output
	return buf.String(), err
}

// mockRedisClient returns a newRedisClientFunc that connects to the given URL,
// propagating any ParseURL error rather than discarding it.
func mockRedisClient(url string) func() (*redis.Client, error) {
	return func() (*redis.Client, error) {
		opt, err := redis.ParseURL(url)
		if err != nil {
			return nil, err
		}
		return redis.NewClient(opt), nil
	}
}

func TestNewRootCmd(t *testing.T) {
	cmd := newRootCmd()

	assert.Equal(t, "uni-cli", cmd.Use)
	assert.True(t, cmd.HasSubCommands())

	// Check if all expected commands are present
	commands := make(map[string]bool)
	for _, c := range cmd.Commands() {
		commands[c.Name()] = true
	}

	assert.True(t, commands["cache"])
	assert.True(t, commands["health"])
	assert.True(t, commands["metrics"])
}

func TestGetEnv(t *testing.T) {
	t.Run("returns environment variable if set", func(t *testing.T) {
		t.Setenv("TEST_ENV_VAR", "test-value")
		assert.Equal(t, "test-value", getEnv("TEST_ENV_VAR", "default"))
	})

	t.Run("returns default value if not set", func(t *testing.T) {
		assert.Equal(t, "default", getEnv("NON_EXISTENT_VAR", "default"))
	})
}

func TestCacheClearCommand(t *testing.T) {
	redisURLStr, cleanup := setupMockRedisServer(t)
	defer cleanup()

	// Backup original functions
	oldRedisFunc := newRedisClientFunc
	oldConfirmFunc := confirmActionFunc
	defer func() {
		newRedisClientFunc = oldRedisFunc
		confirmActionFunc = oldConfirmFunc
	}()

	newRedisClientFunc = mockRedisClient(redisURLStr)

	t.Run("clear confirmation accepted", func(t *testing.T) {
		confirmActionFunc = func(prompt string) bool {
			return true
		}

		cmd := newRootCmd()
		output, err := captureStdout(func() error {
			cmd.SetArgs([]string{"cache", "clear", "cache:*"})
			return cmd.Execute()
		})

		assert.NoError(t, err)
		assert.Contains(t, output, "Found 2 keys matching")
		assert.Contains(t, output, "Deleted 2 keys")
	})

	t.Run("clear confirmation aborted", func(t *testing.T) {
		confirmActionFunc = func(prompt string) bool {
			return false
		}

		cmd := newRootCmd()
		output, err := captureStdout(func() error {
			cmd.SetArgs([]string{"cache", "clear", "cache:*"})
			return cmd.Execute()
		})

		assert.NoError(t, err)
		assert.Contains(t, output, "Found 2 keys matching")
		assert.Contains(t, output, "Aborted")
	})

	t.Run("clear no keys found", func(t *testing.T) {
		confirmActionFunc = func(prompt string) bool {
			return true
		}

		cmd := newRootCmd()
		output, err := captureStdout(func() error {
			cmd.SetArgs([]string{"cache", "clear", "nonexistent:*"})
			return cmd.Execute()
		})

		assert.NoError(t, err)
		assert.Contains(t, output, "No keys found matching pattern")
	})
}

func TestCacheStatsCommand(t *testing.T) {
	redisURLStr, cleanup := setupMockRedisServer(t)
	defer cleanup()

	oldRedisFunc := newRedisClientFunc
	defer func() { newRedisClientFunc = oldRedisFunc }()

	newRedisClientFunc = mockRedisClient(redisURLStr)

	cmd := newRootCmd()
	output, err := captureStdout(func() error {
		cmd.SetArgs([]string{"cache", "stats"})
		return cmd.Execute()
	})

	assert.NoError(t, err)
	assert.Contains(t, output, "Cache Statistics:")
	assert.Contains(t, output, "used_memory_human:10.5M")
}

func TestHealthCommand(t *testing.T) {
	redisURLStr, cleanup := setupMockRedisServer(t)
	defer cleanup()

	oldRedisFunc := newRedisClientFunc
	defer func() { newRedisClientFunc = oldRedisFunc }()

	newRedisClientFunc = mockRedisClient(redisURLStr)

	cmd := newRootCmd()
	output, err := captureStdout(func() error {
		cmd.SetArgs([]string{"health"})
		return cmd.Execute()
	})

	assert.NoError(t, err)
	assert.Contains(t, output, "System Health Check")
	assert.Contains(t, output, "Connected")
}

func TestMetricsShowCommand(t *testing.T) {
	redisURLStr, cleanup := setupMockRedisServer(t)
	defer cleanup()

	oldRedisFunc := newRedisClientFunc
	defer func() { newRedisClientFunc = oldRedisFunc }()

	newRedisClientFunc = mockRedisClient(redisURLStr)

	t.Run("normal metrics", func(t *testing.T) {
		cmd := newRootCmd()
		output, err := captureStdout(func() error {
			cmd.SetArgs([]string{"metrics", "show"})
			return cmd.Execute()
		})

		assert.NoError(t, err)
		assert.Contains(t, output, "System Metrics")
		assert.Contains(t, output, "Cache keys: 5")
	})

	t.Run("verbose metrics", func(t *testing.T) {
		cmd := newRootCmd()
		output, err := captureStdout(func() error {
			cmd.SetArgs([]string{"metrics", "show", "--verbose"})
			return cmd.Execute()
		})

		assert.NoError(t, err)
		assert.Contains(t, output, "Detailed stats:")
		assert.Contains(t, output, "total_connections:42")
	})
}

// TestCommandsFailWhenRedisUnavailable verifies the failure-path exit codes:
// every Redis-dependent subcommand must return a non-zero exit (an error) when
// the broker is unreachable. This includes `health`, which previously printed
// an error but exited 0 — useless for monitoring/CI.
func TestCommandsFailWhenRedisUnavailable(t *testing.T) {
	oldRedisFunc := newRedisClientFunc
	oldConfirmFunc := confirmActionFunc
	defer func() {
		newRedisClientFunc = oldRedisFunc
		confirmActionFunc = oldConfirmFunc
	}()

	// Port 1 (tcpmux) is effectively never listening → fast ECONNREFUSED.
	newRedisClientFunc = func() (*redis.Client, error) {
		opt, err := redis.ParseURL("redis://127.0.0.1:1/0")
		if err != nil {
			return nil, err
		}
		opt.DialTimeout = 500 * time.Millisecond
		opt.MaxRetries = -1 // fail fast, no backoff retries
		return redis.NewClient(opt), nil
	}
	confirmActionFunc = func(string) bool { return true }

	cases := []struct {
		name string
		args []string
	}{
		{"cache clear", []string{"cache", "clear", "cache:*"}},
		{"cache stats", []string{"cache", "stats"}},
		{"metrics show", []string{"metrics", "show"}},
		{"health", []string{"health"}},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			cmd := newRootCmd()
			_, err := captureStdout(func() error {
				cmd.SetArgs(tc.args)
				return cmd.Execute()
			})
			assert.Error(t, err, "expected non-zero exit (error) when Redis is unavailable")
		})
	}
}

func TestNewRedisClient(t *testing.T) {
	oldURL := redisURL
	defer func() { redisURL = oldURL }()

	// Valid URL
	redisURL = "redis://localhost:6379/0"
	client, err := newRedisClient()
	assert.NoError(t, err)
	assert.NotNil(t, client)
	require.NoError(t, client.Close())

	// Invalid URL
	redisURL = "invalid-url"
	client, err = newRedisClient()
	assert.Error(t, err)
	assert.Nil(t, client)
}

func TestConfirmAction_Stdin(t *testing.T) {
	// Backup original confirmActionFunc
	oldConfirmFunc := confirmActionFunc
	defer func() { confirmActionFunc = oldConfirmFunc }()
	confirmActionFunc = confirmAction

	// Test positive confirmation
	r, w, err := os.Pipe()
	require.NoError(t, err)
	oldStdin := os.Stdin
	os.Stdin = r
	defer func() { os.Stdin = oldStdin }()

	_, err = w.Write([]byte("y\n"))
	require.NoError(t, err)
	assert.True(t, confirmActionFunc("Prompt?"))

	// Test negative confirmation
	r2, w2, err := os.Pipe()
	require.NoError(t, err)
	os.Stdin = r2

	_, err = w2.Write([]byte("N\n"))
	require.NoError(t, err)
	assert.False(t, confirmActionFunc("Prompt?"))

	// Cleanup
	require.NoError(t, w.Close())
	require.NoError(t, r.Close())
	require.NoError(t, w2.Close())
	require.NoError(t, r2.Close())
}

func TestMain_Execute(t *testing.T) {
	oldArgs := os.Args
	defer func() { os.Args = oldArgs }()
	os.Args = []string{"uni-cli", "--help"}

	assert.NotPanics(t, func() {
		main()
	})
}

func TestMain_ExitOnError(t *testing.T) {
	if os.Getenv("BE_CRASHER") == "1" {
		os.Args = []string{"uni-cli", "invalid-subcommand-name"}
		main()
		return
	}
	// #nosec
	cmd := exec.CommandContext(context.Background(), os.Args[0], "-test.run=TestMain_ExitOnError")
	cmd.Env = append(os.Environ(), "BE_CRASHER=1")
	err := cmd.Run()
	var e *exec.ExitError
	if errors.As(err, &e) {
		assert.Equal(t, 1, e.ExitCode())
		return
	}
	t.Fatalf("process ran with err %v, want exit status 1", err)
}

func TestCommandsFailOnConnectionError(t *testing.T) {
	oldRedisFunc := newRedisClientFunc
	defer func() { newRedisClientFunc = oldRedisFunc }()

	newRedisClientFunc = func() (*redis.Client, error) {
		return nil, fmt.Errorf("redis connection error")
	}

	cases := []struct {
		name string
		args []string
	}{
		{"cache clear", []string{"cache", "clear", "cache:*"}},
		{"cache stats", []string{"cache", "stats"}},
		{"metrics show", []string{"metrics", "show"}},
		{"health", []string{"health"}},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			cmd := newRootCmd()
			out, err := captureStdout(func() error {
				cmd.SetArgs(tc.args)
				return cmd.Execute()
			})
			assert.Error(t, err)
			if tc.name == "health" {
				assert.Contains(t, out, "redis connection error")
				assert.Contains(t, err.Error(), "one or more health checks failed")
			} else {
				assert.Contains(t, err.Error(), "redis connection error")
			}
		})
	}
}
