package main

import (
	"bytes"
	"fmt"
	"net"
	"os"
	"strings"
	"testing"

	"github.com/redis/go-redis/v9"
	"github.com/stretchr/testify/assert"
)

// Setup mock RESP server to simulate Redis without external dependencies.
func setupMockRedisServer(t *testing.T) (string, func()) {
	ln, err := net.Listen("tcp", "127.0.0.1:0")
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
				defer c.Close()
				buf := make([]byte, 2048)
				for {
					n, err := c.Read(buf)
					if err != nil {
						return
					}
					req := string(buf[:n])
					
					// Split pipelined RESP commands (each starts with '*')
					parts := strings.Split(req, "*")
					for _, part := range parts {
						if part == "" {
							continue
						}
						upperPart := strings.ToUpper(part)
						
						if strings.Contains(upperPart, "HELLO") {
							c.Write([]byte("-ERR unknown command 'HELLO'\r\n"))
						} else if strings.Contains(upperPart, "CLIENT") {
							c.Write([]byte("-ERR unknown command 'CLIENT'\r\n"))
						} else if strings.Contains(upperPart, "PING") {
							c.Write([]byte("+PONG\r\n"))
						} else if strings.Contains(upperPart, "INFO") {
							if strings.Contains(upperPart, "STATS") {
								s := "# Stats\r\ntotal_connections:42\r\n"
								c.Write([]byte(fmt.Sprintf("$%d\r\n%s\r\n", len(s), s)))
							} else {
								s := "# Memory\r\nused_memory_human:10.5M\r\n"
								c.Write([]byte(fmt.Sprintf("$%d\r\n%s\r\n", len(s), s)))
							}
						} else if strings.Contains(upperPart, "KEYS") {
							if strings.Contains(upperPart, "NONEXISTENT") {
								c.Write([]byte("*0\r\n"))
							} else {
								c.Write([]byte("*2\r\n$11\r\ncache:key_1\r\n$11\r\ncache:key_2\r\n"))
							}
						} else if strings.Contains(upperPart, "DEL") {
							c.Write([]byte(":2\r\n"))
						} else if strings.Contains(upperPart, "DBSIZE") {
							c.Write([]byte(":5\r\n"))
						} else {
							c.Write([]byte("+OK\r\n"))
						}
					}
				}
			}(conn)
		}
	}()

	addr := ln.Addr().String()
	redisURLStr := fmt.Sprintf("redis://%s", addr)

	return redisURLStr, func() {
		_ = ln.Close()
	}
}

func captureStdout(f func() error) (string, error) {
	old := os.Stdout
	r, w, _ := os.Pipe()
	os.Stdout = w

	err := f()

	w.Close()
	os.Stdout = old

	var buf bytes.Buffer
	_, _ = buf.ReadFrom(r)
	return buf.String(), err
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

	newRedisClientFunc = func() (*redis.Client, error) {
		opt, _ := redis.ParseURL(redisURLStr)
		return redis.NewClient(opt), nil
	}

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

	newRedisClientFunc = func() (*redis.Client, error) {
		opt, _ := redis.ParseURL(redisURLStr)
		return redis.NewClient(opt), nil
	}

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

	newRedisClientFunc = func() (*redis.Client, error) {
		opt, _ := redis.ParseURL(redisURLStr)
		return redis.NewClient(opt), nil
	}

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

	newRedisClientFunc = func() (*redis.Client, error) {
		opt, _ := redis.ParseURL(redisURLStr)
		return redis.NewClient(opt), nil
	}

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
