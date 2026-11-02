package main

import (
	"bytes"
	"context"
	"errors"
	"log/slog"
	"strings"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"github.com/university-ecosystem/file-processor/internal/config"
	"github.com/university-ecosystem/services/pkg/spiffe"
)

func TestInitRevocationAndReplayWithoutRedisUsesLocalRegistry(t *testing.T) {
	cfg := &config.Config{Environment: "development"}
	opts, guard, closeRevocation, err := initRevocationAndReplay(context.Background(), cfg, nil, nil, slog.Default())
	require.NoError(t, err)
	assert.Nil(t, opts.Revocations)
	assert.NotNil(t, guard)
	require.NotNil(t, closeRevocation)
	closeRevocation()
}

func TestInitRevocationAndReplayReturnsNoCleanupWhenJWTConfigIsInvalid(t *testing.T) {
	// Production requires an issuer, so strict validation rejects the config.
	// The error path must hand back no replay guard and no cleanup to defer.
	cfg := &config.Config{Environment: "production"}
	opts, guard, closeRevocation, err := initRevocationAndReplay(context.Background(), cfg, nil, nil, slog.Default())
	require.Error(t, err)
	assert.ErrorContains(t, err, "FP_JWT_ISSUER is required")
	assert.Nil(t, guard)
	assert.Nil(t, closeRevocation)
	assert.Empty(t, opts.Issuer)
}

func TestInitRevocationAndReplayRejectsMalformedRedisURL(t *testing.T) {
	cfg := &config.Config{Environment: "development", RevocationRedisURL: "://bad redis url"}
	_, guard, closeRevocation, err := initRevocationAndReplay(context.Background(), cfg, nil, nil, slog.Default())
	require.Error(t, err)
	assert.Nil(t, guard)
	assert.Nil(t, closeRevocation)
}

func TestLogCloseErrorRecordsFailureWithoutPropagating(t *testing.T) {
	var buf bytes.Buffer
	logger := slog.New(slog.NewTextHandler(&buf, nil))

	logCloseError(context.Background(), logger, "close failed", func() error { return nil })
	assert.Empty(t, buf.String())

	logCloseError(context.Background(), logger, "close failed", func() error { return errors.New("boom") })
	assert.True(t, strings.Contains(buf.String(), "close failed"))
	assert.True(t, strings.Contains(buf.String(), "boom"))
}

func TestCloseSpiffeClientOnExitHandlesDisabledAndActiveClients(t *testing.T) {
	ctx := context.Background()
	logger := slog.New(slog.NewTextHandler(&bytes.Buffer{}, nil))

	original := closeSpiffeClientFunc
	t.Cleanup(func() { closeSpiffeClientFunc = original })
	var closed []*spiffe.Client
	closeSpiffeClientFunc = func(client *spiffe.Client) error {
		closed = append(closed, client)
		return nil
	}

	closeSpiffeClientOnExit(ctx, logger, nil)
	assert.Empty(t, closed, "a disabled SPIFFE client has nothing to close")

	active := &spiffe.Client{}
	closeSpiffeClientOnExit(ctx, logger, active)
	assert.Equal(t, []*spiffe.Client{active}, closed)
}
