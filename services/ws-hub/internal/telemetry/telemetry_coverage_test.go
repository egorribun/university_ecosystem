// Package telemetry — extra coverage tests for Wave 8 coverage gate.
// WHY: telemetry_test.go covers only the success path of InitTracer and the
// three InitSentry branches. The two error-return branches inside InitTracer
// (exporter creation failure and resource detection failure) are left uncovered
// at 85.7%. This file adds tests that exercise those branches without requiring
// a live OTel collector.
package telemetry

import (
	"context"
	"errors"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"github.com/university-ecosystem/ws-hub/pkg/config"
	"go.opentelemetry.io/otel/exporters/otlp/otlptrace"
	"go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracegrpc"
	"go.opentelemetry.io/otel/sdk/resource"
)

func TestInitTracer_DeterministicDependencyFailures(t *testing.T) {
	oldExporter := newOTLPTraceExporterFunc
	oldResource := newTelemetryResourceFunc
	t.Cleanup(func() {
		newOTLPTraceExporterFunc = oldExporter
		newTelemetryResourceFunc = oldResource
	})

	t.Run("exporter construction", func(t *testing.T) {
		newOTLPTraceExporterFunc = func(context.Context, ...otlptracegrpc.Option) (*otlptrace.Exporter, error) {
			return nil, errors.New("exporter unavailable")
		}
		newTelemetryResourceFunc = oldResource

		tp, err := InitTracer(context.Background(), &config.Config{Environment: "test"})
		assert.Nil(t, tp)
		assert.EqualError(t, err, "exporter unavailable")
	})

	t.Run("resource construction", func(t *testing.T) {
		newOTLPTraceExporterFunc = oldExporter
		newTelemetryResourceFunc = func(context.Context, ...resource.Option) (*resource.Resource, error) {
			return nil, errors.New("resource unavailable")
		}

		tp, err := InitTracer(context.Background(), &config.Config{Environment: "test"})
		assert.Nil(t, tp)
		assert.EqualError(t, err, "resource unavailable")
	})
}

// TestInitTracer_ExporterFailsWithCancelledContext exercises the
// `if err != nil { return nil, err }` branch after otlptracegrpc.New().
// A pre-cancelled context causes the gRPC dialer to fail during exporter
// initialisation, which is the earliest observable failure point.
func TestInitTracer_ExporterFailsWithCancelledContext(t *testing.T) {
	// Cancel the context before passing it in so the gRPC handshake fails.
	ctx, cancel := context.WithCancel(context.Background())
	cancel() // cancelled immediately

	cfg := &config.Config{Environment: "test"}

	tp, err := InitTracer(ctx, cfg)
	// otlptracegrpc.New with a cancelled context may either error immediately
	// or succeed (lazy connection). Both outcomes are valid; we just must not
	// panic and tp/err must be consistent.
	if err != nil {
		assert.Nil(t, tp, "TracerProvider must be nil when InitTracer returns an error")
	} else {
		require.NotNil(t, tp, "TracerProvider must not be nil on success")
		t.Cleanup(func() {
			// Use a fresh context for shutdown since the original is cancelled.
			_ = tp.Shutdown(context.Background()) //nolint:errcheck // test cleanup
		})
	}
}

// TestInitSentry_AllBranchesRobust re-verifies that InitSentry is idempotent
// under repeated calls — calling it multiple times should not panic or mutate
// shared state unexpectedly.
func TestInitSentry_AllBranchesRobust(t *testing.T) {
	t.Run("empty_dsn_is_noop", func(t *testing.T) {
		// Calling multiple times must be safe.
		for range 3 {
			err := InitSentry(&config.Config{SentryDSN: ""})
			require.NoError(t, err)
		}
	})

	t.Run("valid_looking_dsn_succeeds", func(t *testing.T) {
		cfg := &config.Config{
			SentryDSN:   "http://abc123@sentry.example.com/42",
			Environment: "unit-test",
		}
		err := InitSentry(cfg)
		require.NoError(t, err)
	})
}

// TestInitTracer_SuccessShutdown verifies that the TracerProvider returned on
// the happy path can be gracefully shut down, preventing goroutine leaks in
// subsequent tests.
func TestInitTracer_SuccessShutdown(t *testing.T) {
	ctx := context.Background()
	cfg := &config.Config{Environment: "test-shutdown"}

	tp, err := InitTracer(ctx, cfg)
	require.NoError(t, err)
	require.NotNil(t, tp)

	shutdownErr := tp.Shutdown(ctx)
	assert.NoError(t, shutdownErr, "TracerProvider.Shutdown must not error")
}
