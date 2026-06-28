package main

// Coverage tests (testing session 16) for cmd bootstrap helpers that don't need
// a live Temporal/NATS/MinIO connection: initLogger, initSentry (no-DSN + bad-DSN),
// initTracer (production-insecure guard + dev success path), and the stream-auth
// error path + authedServerStream.Context() wrapper. The genuinely
// integration-shaped funcs (connectTemporal Dial loop, setupTemporalWorker /
// startNatsSubscriber / runServers / setupGraphQLServer with os.Exit) stay
// covered by the integration suite, not here.

import (
	"context"
	"errors"
	"io"
	"log/slog"
	"os"
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"github.com/university-ecosystem/file-processor/internal/config"
	"go.temporal.io/sdk/client"
	"google.golang.org/grpc"
)

func discardLogger() *slog.Logger {
	return slog.New(slog.NewTextHandler(io.Discard, nil))
}

func TestInitLogger_ReturnsJSONLogger(t *testing.T) {
	logger := initLogger()
	require.NotNil(t, logger)
	// Smoke: a log call must not panic with the custom ReplaceAttr time handler.
	logger.InfoContext(context.Background(), "init-logger-smoke", "k", "v")
}

func TestInitSentry_NoDSNIsNoOp(t *testing.T) {
	// Empty DSN takes the early return — no global Sentry hub is mutated.
	initSentry(context.Background(), &config.Config{SentryDSN: "", Environment: "test"}, discardLogger())
}

func TestInitSentry_MalformedDSNLogsError(t *testing.T) {
	// A malformed DSN makes sentry.Init return an error → the error branch runs.
	// sentry.Init parses the DSN synchronously and does no network on a bad parse.
	initSentry(context.Background(), &config.Config{SentryDSN: "not-a-valid-dsn", Environment: "test"}, discardLogger())
}

func TestInitTracer_ProductionInsecureForbidden(t *testing.T) {
	_, err := initTracer(context.Background(),
		&config.Config{OTLPInsecure: true, Environment: "production"}, discardLogger())
	require.Error(t, err)
	assert.Contains(t, err.Error(), "forbidden in production")
}

func TestInitTracer_DevInsecureSucceeds(t *testing.T) {
	// The OTLP gRPC exporter dials lazily, so New() returns without a collector.
	tp, err := initTracer(context.Background(),
		&config.Config{OTLPInsecure: true, Environment: "development", OTLPEndpoint: "localhost:4317"},
		discardLogger())
	require.NoError(t, err)
	require.NotNil(t, tp)
	// Shut down to stop the batch-span-processor goroutine cleanly.
	require.NoError(t, tp.Shutdown(context.Background()))
}

func TestSelectiveStreamAuth_AuthErrorBlocksHandler(t *testing.T) {
	authFn := func(ctx context.Context) (context.Context, error) {
		return nil, errors.New("invalid stream token")
	}
	interceptor := selectiveStreamAuth(authFn)

	handlerCalled := false
	handler := func(srv interface{}, ss grpc.ServerStream) error {
		handlerCalled = true
		return nil
	}

	ss := &mockServerStream{ctx: context.Background()}
	info := &grpc.StreamServerInfo{FullMethod: "/file_processor.v1.FileProcessingService/Watch"}
	err := interceptor(nil, ss, info, handler)

	require.Error(t, err)
	assert.Contains(t, err.Error(), "invalid stream token")
	assert.False(t, handlerCalled, "handler must NOT run when stream auth fails")
}

type authCtxKey struct{}

func TestSelectiveStreamAuth_WrappedStreamCarriesAuthedContext(t *testing.T) {
	// authFn injects a value; the handler must observe it via the WRAPPED stream's
	// Context() — exercising authedServerStream.Context().
	authFn := func(ctx context.Context) (context.Context, error) {
		return context.WithValue(ctx, authCtxKey{}, "sub-123"), nil
	}
	interceptor := selectiveStreamAuth(authFn)

	var seen interface{}
	handler := func(srv interface{}, ss grpc.ServerStream) error {
		seen = ss.Context().Value(authCtxKey{})
		return nil
	}

	ss := &mockServerStream{ctx: context.Background()}
	info := &grpc.StreamServerInfo{FullMethod: "/file_processor.v1.FileProcessingService/Watch"}
	require.NoError(t, interceptor(nil, ss, info, handler))
	assert.Equal(t, "sub-123", seen, "wrapped stream must carry the authed context value")
}

func TestConnectTemporal_CancelledContext(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	cancel() // cancel immediately
	cfg := &config.Config{
		TemporalHost: "localhost:1",
	}
	c, err := connectTemporal(ctx, cfg, discardLogger())
	assert.Error(t, err)
	assert.Nil(t, c)
}

func TestStartNatsSubscriber_FailGracefully(t *testing.T) {
	cfg := &config.Config{
		NatsURL: "nats://127.0.0.1:1",
	}
	assert.NotPanics(t, func() {
		startNatsSubscriber(context.Background(), cfg, nil, discardLogger())
	})
}

func TestSetupGraphQLServer(t *testing.T) {
	content, err := os.ReadFile("../../schema.graphql")
	if err == nil {
		require.NoError(t, os.WriteFile("schema.graphql", content, 0600)) // #nosec G703 -- test-only fixed schema path.
		t.Cleanup(func() {
			require.NoError(t, os.Remove("schema.graphql"))
		})
	}

	cfg := &config.Config{
		GraphQLPort: "0",
		MinioBucket: "test-bucket",
		JWTSecret:   "test-secret",
	}
	srv := setupGraphQLServer(context.Background(), cfg, nil, nil, discardLogger())
	assert.NotNil(t, srv)
}

func TestRunServers_CleanShutdown(t *testing.T) {
	content, err := os.ReadFile("../../schema.graphql")
	if err == nil {
		require.NoError(t, os.WriteFile("schema.graphql", content, 0600)) // #nosec G703 -- test-only fixed schema path.
		t.Cleanup(func() {
			require.NoError(t, os.Remove("schema.graphql"))
		})
	}

	cfg := &config.Config{
		GRPCPort:    "0",
		GraphQLPort: "0",
		MinioBucket: "test-bucket",
		JWTSecret:   "test-secret",
	}
	grpcSrv := setupGRPCServer(context.Background(), cfg, nil, nil, discardLogger())
	graphqlSrv := setupGraphQLServer(context.Background(), cfg, nil, nil, discardLogger())

	ctx, cancel := context.WithCancel(context.Background())
	go func() {
		time.Sleep(100 * time.Millisecond)
		cancel()
	}()

	assert.NotPanics(t, func() {
		runServers(ctx, grpcSrv, graphqlSrv, cfg, discardLogger())
	})
}

func TestConnectTemporal_APIKeyFileHandling(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	cancel() // cancel immediately to avoid actually waiting/retrying

	t.Run("non-existent file", func(t *testing.T) {
		cfg := &config.Config{
			TemporalHost:       "localhost:1",
			TemporalAPIKeyFile: "non-existent-key-file.txt",
		}
		c, err := connectTemporal(ctx, cfg, discardLogger())
		assert.Error(t, err)
		assert.Nil(t, c)
	})

	t.Run("empty file", func(t *testing.T) {
		tmpFile, err := os.CreateTemp("", "empty-key")
		require.NoError(t, err)
		t.Cleanup(func() {
			require.NoError(t, os.Remove(tmpFile.Name()))
		})
		require.NoError(t, tmpFile.Close())

		cfg := &config.Config{
			TemporalHost:       "localhost:1",
			TemporalAPIKeyFile: tmpFile.Name(),
		}
		c, err := connectTemporal(ctx, cfg, discardLogger())
		assert.Error(t, err)
		assert.Nil(t, c)
	})

	t.Run("valid key file", func(t *testing.T) {
		tmpFile, err := os.CreateTemp("", "valid-key")
		require.NoError(t, err)
		t.Cleanup(func() {
			require.NoError(t, os.Remove(tmpFile.Name()))
		})
		_, err = tmpFile.WriteString("my-secret-temporal-token")
		require.NoError(t, err)
		require.NoError(t, tmpFile.Close())

		cfg := &config.Config{
			TemporalHost:       "localhost:1",
			TemporalAPIKeyFile: tmpFile.Name(),
		}
		c, err := connectTemporal(ctx, cfg, discardLogger())
		assert.Error(t, err)
		assert.Nil(t, c)
	})
}

func TestSetupTemporalWorker(t *testing.T) {
	cfg := &config.Config{
		MinioEndpoint:  "localhost:9000",
		MinioAccessKey: "minioadmin",
		MinioSecretKey: "minioadmin",
		MinioBucket:    "test-bucket",
	}

	c, err := client.NewLazyClient(client.Options{
		HostPort: "localhost:7233",
	})
	require.NoError(t, err)

	assert.NotPanics(t, func() {
		setupTemporalWorker(context.Background(), c, cfg, discardLogger())
	})
}
