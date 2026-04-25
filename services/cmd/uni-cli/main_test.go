package main

import (
	"testing"

	"github.com/stretchr/testify/assert"
)

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
