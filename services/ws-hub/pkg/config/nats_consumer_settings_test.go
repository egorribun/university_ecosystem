package config

import (
	"testing"

	"github.com/stretchr/testify/require"
)

// The defaults are the contract the Helm chart renders under wsHub.config.natsConsumer.
// Changing one here without the chart fails the chart contract test.
func TestNATSConsumerDefaultsArePinned(t *testing.T) {
	require.Equal(t, NATSConsumerSettings{
		AckPolicy:                "explicit",
		AckWaitSeconds:           60,
		MaxDeliver:               20,
		InactiveThresholdSeconds: 300,
	}, DefaultNATSConsumerSettings())
	require.NoError(t, DefaultNATSConsumerSettings().Validate())
}

func TestNATSConsumerSettingsValidate(t *testing.T) {
	valid := DefaultNATSConsumerSettings()
	cases := []struct {
		name    string
		mutate  func(*NATSConsumerSettings)
		wantErr bool
	}{
		{name: "defaults are valid", mutate: func(*NATSConsumerSettings) {}},
		{name: "ack wait at the lower bound", mutate: func(s *NATSConsumerSettings) { s.AckWaitSeconds = 31 }},
		{name: "ack wait at the upper bound", mutate: func(s *NATSConsumerSettings) { s.AckWaitSeconds = 600 }},
		{name: "ack wait equal to the callback timeout", mutate: func(s *NATSConsumerSettings) { s.AckWaitSeconds = 30 }, wantErr: true},
		{name: "ack wait above the bound", mutate: func(s *NATSConsumerSettings) { s.AckWaitSeconds = 601 }, wantErr: true},
		{name: "ack wait unset", mutate: func(s *NATSConsumerSettings) { s.AckWaitSeconds = 0 }, wantErr: true},
		{name: "max deliver at the lower bound", mutate: func(s *NATSConsumerSettings) { s.MaxDeliver = 5 }},
		{name: "max deliver at the upper bound", mutate: func(s *NATSConsumerSettings) { s.MaxDeliver = 100 }},
		{name: "max deliver of one drops invalidations on a transient NAK", mutate: func(s *NATSConsumerSettings) { s.MaxDeliver = 1 }, wantErr: true},
		{name: "max deliver unlimited is rejected", mutate: func(s *NATSConsumerSettings) { s.MaxDeliver = -1 }, wantErr: true},
		{name: "max deliver above the bound", mutate: func(s *NATSConsumerSettings) { s.MaxDeliver = 101 }, wantErr: true},
		{name: "inactive threshold at the lower bound", mutate: func(s *NATSConsumerSettings) { s.InactiveThresholdSeconds = 60 }},
		{name: "inactive threshold at the upper bound", mutate: func(s *NATSConsumerSettings) { s.InactiveThresholdSeconds = 86400 }},
		{name: "inactive threshold below the bound", mutate: func(s *NATSConsumerSettings) { s.InactiveThresholdSeconds = 59 }, wantErr: true},
		{name: "inactive threshold above the bound", mutate: func(s *NATSConsumerSettings) { s.InactiveThresholdSeconds = 86401 }, wantErr: true},
		{name: "none ack policy is rejected", mutate: func(s *NATSConsumerSettings) { s.AckPolicy = "none" }, wantErr: true},
		{name: "all ack policy is rejected", mutate: func(s *NATSConsumerSettings) { s.AckPolicy = "all" }, wantErr: true},
		{name: "empty ack policy is rejected", mutate: func(s *NATSConsumerSettings) { s.AckPolicy = "" }, wantErr: true},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			settings := valid
			tc.mutate(&settings)
			err := settings.Validate()
			if tc.wantErr {
				require.Error(t, err)
				return
			}
			require.NoError(t, err)
		})
	}
}

func TestNATSConsumerSettingsFromEnvFailsClosed(t *testing.T) {
	cases := []struct {
		name    string
		env     map[string]string
		wantErr string
		want    NATSConsumerSettings
	}{
		{name: "unset environment yields the defaults", env: map[string]string{}, want: DefaultNATSConsumerSettings()},
		{
			name: "valid overrides are read",
			env: map[string]string{
				"WS_NATS_ACK_WAIT_SECONDS":           "120",
				"WS_NATS_MAX_DELIVER":                "7",
				"WS_NATS_INACTIVE_THRESHOLD_SECONDS": "900",
			},
			want: NATSConsumerSettings{AckPolicy: "explicit", AckWaitSeconds: 120, MaxDeliver: 7, InactiveThresholdSeconds: 900},
		},
		{name: "non-numeric ack wait is an error, not a silent default", env: map[string]string{"WS_NATS_ACK_WAIT_SECONDS": "sixty"}, wantErr: "WS_NATS_ACK_WAIT_SECONDS must be an integer"},
		{name: "non-numeric max deliver is an error", env: map[string]string{"WS_NATS_MAX_DELIVER": "1.5"}, wantErr: "WS_NATS_MAX_DELIVER must be an integer"},
		{name: "non-numeric inactive threshold is an error", env: map[string]string{"WS_NATS_INACTIVE_THRESHOLD_SECONDS": "x"}, wantErr: "WS_NATS_INACTIVE_THRESHOLD_SECONDS must be an integer"},
		{name: "out-of-range value is rejected", env: map[string]string{"WS_NATS_MAX_DELIVER": "1"}, wantErr: "invalid NATS consumer settings"},
		{name: "unsupported ack policy is rejected", env: map[string]string{"WS_NATS_ACK_POLICY": "none"}, wantErr: "invalid NATS consumer settings"},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			for _, key := range []string{
				"WS_NATS_ACK_POLICY", "WS_NATS_ACK_WAIT_SECONDS", "WS_NATS_MAX_DELIVER", "WS_NATS_INACTIVE_THRESHOLD_SECONDS",
			} {
				t.Setenv(key, "")
			}
			for key, value := range tc.env {
				t.Setenv(key, value)
			}
			settings, err := natsConsumerSettingsFromEnv()
			if tc.wantErr != "" {
				require.ErrorContains(t, err, tc.wantErr)
				return
			}
			require.NoError(t, err)
			require.Equal(t, tc.want, settings)
		})
	}
}

func TestLoadConfigRejectsInvalidNATSConsumerSettings(t *testing.T) {
	t.Setenv("WS_NATS_MAX_DELIVER", "not-a-number")
	_, err := LoadConfig()
	require.ErrorContains(t, err, "WS_NATS_MAX_DELIVER must be an integer")
}

func TestLoadConfigCarriesNATSConsumerDefaults(t *testing.T) {
	for _, key := range []string{
		"WS_NATS_ACK_POLICY", "WS_NATS_ACK_WAIT_SECONDS", "WS_NATS_MAX_DELIVER", "WS_NATS_INACTIVE_THRESHOLD_SECONDS",
	} {
		t.Setenv(key, "")
	}
	cfg, err := LoadConfig()
	require.NoError(t, err)
	require.Equal(t, DefaultNATSConsumerSettings(), cfg.NATSConsumer)
}
