package hub

import (
	"testing"

	"github.com/stretchr/testify/require"

	"github.com/university-ecosystem/ws-hub/pkg/config"
)

func TestWSUpgradeRatePerMinuteKeepsTheDefaultUnlessConfigured(t *testing.T) {
	require.Equal(t, 120, wsUpgradeRatePerMinute(nil))
	require.Equal(t, 120, wsUpgradeRatePerMinute(&config.Config{}))
	require.Equal(t, 120, wsUpgradeRatePerMinute(&config.Config{WSUpgradeRatePerMinute: -5}))
	require.Equal(t, 600, wsUpgradeRatePerMinute(&config.Config{WSUpgradeRatePerMinute: 600}))
}

func TestConfiguredUpgradeRateIsTheBurstOfOneClient(t *testing.T) {
	limiter := NewWSUpgradeRateLimiter(wsUpgradeRatePerMinute(&config.Config{WSUpgradeRatePerMinute: 2}), 60)
	defer limiter.Stop()
	require.True(t, limiter.Allow("203.0.113.1"))
	require.True(t, limiter.Allow("203.0.113.1"))
	require.False(t, limiter.Allow("203.0.113.1"))
	require.True(t, limiter.Allow("203.0.113.2"))
}
