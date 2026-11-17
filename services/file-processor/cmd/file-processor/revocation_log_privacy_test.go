package main

import (
	"bytes"
	"testing"

	"github.com/stretchr/testify/require"
	"github.com/university-ecosystem/file-processor/internal/config"
	"github.com/university-ecosystem/services/pkg/logging"
)

func TestRevocationRedisParseFailureDoesNotLogURLCredentials(t *testing.T) {
	secret := "opaqueCredentialCanary"
	var output bytes.Buffer
	logger := logging.NewJSONLogger(&output, nil)
	_, _, cleanup, err := initRevocationAndReplay(t.Context(), &config.Config{
		RevocationRedisURL: "redis://reader:" + secret + "@localhost:bad",
	}, nil, nil, logger)
	require.Error(t, err)
	require.Nil(t, cleanup)
	// Prove the fixture reaches the real parser error, not a masked mock.
	require.Contains(t, err.Error(), secret)
	require.Contains(t, output.String(), "Failed to initialize session revocation Redis")
	require.Contains(t, output.String(), "REDACTED")
	require.NotContains(t, output.String(), secret)
	require.NotContains(t, output.String(), "reader")
}
