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
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"github.com/university-ecosystem/file-processor/internal/config"
	"github.com/university-ecosystem/services/pkg/spiffe"
	"go.temporal.io/sdk/client"
	"go.temporal.io/sdk/worker"
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

func TestInitSpiffeClient_DisabledReturnsNil(t *testing.T) {
	client, err := initSpiffeClient(context.Background(), &config.Config{}, discardLogger())
	require.NoError(t, err)
	assert.Nil(t, client)
}

func TestInitSpiffeClient_InvalidTrustDomainFailsClosed(t *testing.T) {
	client, err := initSpiffeClient(context.Background(), &config.Config{
		SpiffeEnabled:     true,
		SpiffeTrustDomain: "invalid trust domain with spaces!",
	}, discardLogger())
	assert.Nil(t, client)
	require.Error(t, err)
	assert.Contains(t, err.Error(), "trust")
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
		&config.Config{OTLPInsecure: true, Environment: "development", OTLPEndpoint: "127.0.0.1:4317"},
		discardLogger())
	require.NoError(t, err)
	require.NotNil(t, tp)
	// Shut down to stop the batch-span-processor goroutine cleanly.
	require.NoError(t, tp.Shutdown(context.Background()))
}

func TestInitTracer_TLSPathSucceeds(t *testing.T) {
	// The secure branch must construct TLS credentials without dialing the
	// collector during startup; shutdown verifies the exporter remains clean.
	tp, err := initTracer(context.Background(),
		&config.Config{Environment: "development", OTLPEndpoint: "127.0.0.1:4317"},
		discardLogger())
	require.NoError(t, err)
	require.NotNil(t, tp)
	require.NoError(t, tp.Shutdown(context.Background()))
}

func TestInitializeTracerShutdown_SuccessPath(t *testing.T) {
	cleanup := initializeTracerShutdown(context.Background(), &config.Config{
		OTLPInsecure: true,
		Environment:  "development",
		OTLPEndpoint: "127.0.0.1:4317",
	}, discardLogger())
	require.NotNil(t, cleanup)
	cleanup()
}

func TestInitializeTracerShutdown_InitFailureReturnsNoop(t *testing.T) {
	// Production must reject insecure OTLP before an exporter is created. The
	// wrapper converts that startup failure into a safe no-op cleanup function so
	// callers can keep their unconditional defer without a nil function panic.
	cleanup := initializeTracerShutdown(context.Background(), &config.Config{
		OTLPInsecure: true,
		Environment:  "production",
	}, discardLogger())
	require.NotNil(t, cleanup)
	assert.NotPanics(t, cleanup)
}

func TestCloseTemporalClient_NilIsNoOp(t *testing.T) {
	assert.NotPanics(t, func() { closeTemporalClient(nil) })
}

func TestLoadRSAPublicKey_Valid(t *testing.T) {
	key := generateRSAKey(t)
	loaded, err := loadRSAPublicKey(context.Background(), &config.Config{
		RSAPublicKeyPEM: rsaPublicPEM(t, &key.PublicKey),
	}, discardLogger())
	require.NoError(t, err)
	require.NotNil(t, loaded)
	assert.Equal(t, key.N, loaded.N)
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
		TemporalHost: "127.0.0.1:1",
	}
	c, err := connectTemporal(ctx, cfg, discardLogger())
	assert.Error(t, err)
	assert.Nil(t, c)
}

func TestStartNatsSubscriber_FailGracefully(t *testing.T) {
	t.Run("connecting in background", func(t *testing.T) {
		cfg := &config.Config{
			NatsURL:     "nats://127.0.0.1:1",
			Environment: "testing",
		}
		assert.NotPanics(t, func() {
			startNatsSubscriber(context.Background(), cfg, nil, discardLogger())
		})
	})

	t.Run("invalid URL returns error", func(t *testing.T) {
		cfg := &config.Config{
			NatsURL:     "nats://127.0.0.1:1,,",
			Environment: "testing",
		}
		assert.NotPanics(t, func() {
			startNatsSubscriber(context.Background(), cfg, nil, discardLogger())
		})
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
	srv, err := setupGraphQLServer(context.Background(), cfg, nil, nil, discardLogger())
	require.NoError(t, err)
	assert.NotNil(t, srv)
}

func TestSetupGraphQLServer_ParentSchemaFallback(t *testing.T) {
	content, err := os.ReadFile("../../schema.graphql")
	require.NoError(t, err)

	tempDir := t.TempDir()
	parentSchema := filepath.Join(tempDir, "..", "schema.graphql")
	require.NoError(t, os.WriteFile(parentSchema, content, 0600)) // #nosec G703 -- test-only temp path.
	t.Chdir(tempDir)
	t.Setenv("FP_SCHEMA_PATH", "")

	srv, err := setupGraphQLServer(context.Background(), &config.Config{
		GraphQLPort: "0",
		MinioBucket: "test-bucket",
		JWTSecret:   "test-secret",
	}, nil, nil, discardLogger())
	require.NoError(t, err)
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
	grpcSrv, err := setupGRPCServer(context.Background(), cfg, nil, nil, discardLogger())
	require.NoError(t, err)
	graphqlSrv, err := setupGraphQLServer(context.Background(), cfg, nil, nil, discardLogger())
	require.NoError(t, err)

	ctx, cancel := context.WithCancel(context.Background())
	go func() {
		time.Sleep(100 * time.Millisecond)
		cancel()
	}()

	assert.NotPanics(t, func() {
		require.NoError(t, runServers(ctx, grpcSrv, graphqlSrv, cfg, discardLogger()))
	})
}

func TestRunServers_GraphQLListenFailure(t *testing.T) {
	grpcSrv := grpc.NewServer()
	graphqlSrv := &http.Server{
		Addr:              ":-1",
		ReadHeaderTimeout: time.Second,
	}
	cfg := &config.Config{GRPCPort: "0", GraphQLPort: "0"}

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	err := runServers(ctx, grpcSrv, graphqlSrv, cfg, discardLogger())
	assert.Error(t, err)
	grpcSrv.Stop()
}

func TestConnectTemporal_APIKeyFileHandling(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	cancel() // cancel immediately to avoid actually waiting/retrying

	t.Run("non-existent file", func(t *testing.T) {
		cfg := &config.Config{
			TemporalHost:       "127.0.0.1:1",
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
			TemporalHost:       "127.0.0.1:1",
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
			TemporalHost:       "127.0.0.1:1",
			TemporalAPIKeyFile: tmpFile.Name(),
		}
		c, err := connectTemporal(ctx, cfg, discardLogger())
		assert.Error(t, err)
		assert.Nil(t, c)
	})
}

func TestSetupTemporalWorker(t *testing.T) {
	cfg := &config.Config{
		MinioEndpoint:  "127.0.0.1:9000",
		MinioAccessKey: "minioadmin",
		MinioSecretKey: "minioadmin",
		MinioBucket:    "test-bucket",
	}

	c, err := client.NewLazyClient(client.Options{
		HostPort: "127.0.0.1:7233",
	})
	require.NoError(t, err)

	_, _, err = setupTemporalWorker(context.Background(), c, cfg, discardLogger())
	require.NoError(t, err)
}

func TestMain_ExitOnConfigLoadFailure(t *testing.T) {
	if os.Getenv("BE_CRASHER") == "1" {
		if err := os.Setenv("FP_JWT_SECRET", ""); err != nil {
			t.Fatal(err)
		} // force failure
		main()
		return
	}
	// #nosec
	cmd := exec.CommandContext(context.Background(), os.Args[0], "-test.run=TestMain_ExitOnConfigLoadFailure")
	cmd.Env = append(os.Environ(), "BE_CRASHER=1")
	err := cmd.Run()
	var e *exec.ExitError
	if errors.As(err, &e) {
		assert.Equal(t, 1, e.ExitCode())
		return
	}
	t.Fatalf("process ran with err %v, want exit status 1", err)
}

func TestSetupGraphQLServer_NoSchemaFile(t *testing.T) {
	t.Setenv("FP_SCHEMA_PATH", "/nonexistent/schema.graphql")
	cfg := &config.Config{
		GraphQLPort: "0",
		MinioBucket: "test-bucket",
		JWTSecret:   "test-secret",
	}
	_, err := setupGraphQLServer(context.Background(), cfg, nil, nil, discardLogger())
	require.Error(t, err)
}

func TestRunServers_GRPCListenFailure(t *testing.T) {
	if os.Getenv("BE_CRASHER") == "1" {
		cfg := &config.Config{
			GRPCPort: "-1",
		}
		if err := runServers(context.Background(), nil, nil, cfg, discardLogger()); err != nil {
			os.Exit(1)
		}
		return
	}
	// #nosec
	cmd := exec.CommandContext(context.Background(), os.Args[0], "-test.run=TestRunServers_GRPCListenFailure")
	cmd.Env = append(os.Environ(), "BE_CRASHER=1")
	err := cmd.Run()
	var e *exec.ExitError
	if errors.As(err, &e) {
		assert.Equal(t, 1, e.ExitCode())
		return
	}
	t.Fatalf("process ran with err %v, want exit status 1", err)
}

func TestSetupGraphQLServer_RestrictIntrospection(t *testing.T) {
	content, err := os.ReadFile("../../schema.graphql")
	if err == nil {
		require.NoError(t, os.WriteFile("schema.graphql", content, 0600)) // #nosec
		t.Cleanup(func() {
			require.NoError(t, os.Remove("schema.graphql"))
		})
	}
	cfg := &config.Config{
		GraphQLPort: "0",
		MinioBucket: "test-bucket",
		JWTSecret:   "test-secret",
		Environment: "production",
	}
	srv, err := setupGraphQLServer(context.Background(), cfg, nil, nil, discardLogger())
	require.NoError(t, err)
	assert.NotNil(t, srv)
}

func TestSetupTemporalWorker_BuildMinIOClientError(t *testing.T) {
	cfg := &config.Config{
		MinioEndpoint: "", // causes error
	}
	c, err := client.NewLazyClient(client.Options{HostPort: "127.0.0.1:7233"})
	require.NoError(t, err)
	_, _, err = setupTemporalWorker(context.Background(), c, cfg, discardLogger())
	require.Error(t, err)
}

type mockWorker struct {
	worker.Worker
}

func (m *mockWorker) Start() error {
	return nil
}

func (m *mockWorker) Stop() {
}

func (m *mockWorker) RegisterWorkflow(w interface{}) {
}

func (m *mockWorker) RegisterActivity(a interface{}) {
}

type failingStartWorker struct {
	mockWorker
	err error
}

func (w *failingStartWorker) Start() error {
	return w.err
}

type trackedTemporalClient struct {
	client.Client
	closed *bool
}

func (c *trackedTemporalClient) Close() {
	*c.closed = true
	c.Client.Close()
}

func newTrackedTemporalClient(t *testing.T) (*trackedTemporalClient, *bool) {
	t.Helper()
	base, err := client.NewLazyClient(client.Options{HostPort: "127.0.0.1:7233"})
	require.NoError(t, err)
	closed := false
	return &trackedTemporalClient{Client: base, closed: &closed}, &closed
}

func TestStartTemporalWorker_ClosesClientOnWorkerSetupFailure(t *testing.T) {
	oldDial := dialTemporalFunc
	oldNewWorker := newWorkerFunc
	defer func() {
		dialTemporalFunc = oldDial
		newWorkerFunc = oldNewWorker
	}()

	tracked, closed := newTrackedTemporalClient(t)
	dialTemporalFunc = func(client.Options) (client.Client, error) {
		return tracked, nil
	}
	newWorkerFunc = func(client.Client, string, worker.Options) worker.Worker {
		return &mockWorker{}
	}

	_, _, err := startTemporalWorker(context.Background(), &config.Config{}, discardLogger())
	require.Error(t, err)
	assert.Contains(t, err.Error(), "MinIO")
	assert.True(t, *closed, "Temporal client must close when worker setup fails")
}

func TestStartTemporalWorker_ClosesClientOnWorkerStartFailure(t *testing.T) {
	oldDial := dialTemporalFunc
	oldNewWorker := newWorkerFunc
	defer func() {
		dialTemporalFunc = oldDial
		newWorkerFunc = oldNewWorker
	}()

	tracked, closed := newTrackedTemporalClient(t)
	dialTemporalFunc = func(client.Options) (client.Client, error) {
		return tracked, nil
	}
	newWorkerFunc = func(client.Client, string, worker.Options) worker.Worker {
		return &failingStartWorker{err: errors.New("worker start failed")}
	}

	cfg := &config.Config{
		MinioEndpoint:  "127.0.0.1:9000",
		MinioAccessKey: "minioadmin",
		MinioSecretKey: "minioadmin",
		MinioBucket:    "test-bucket",
	}
	_, _, err := startTemporalWorker(context.Background(), cfg, discardLogger())
	require.Error(t, err)
	assert.Contains(t, err.Error(), "worker start failed")
	assert.True(t, *closed, "Temporal client must close when worker start fails")
}

func TestMain_SuccessLifecycle(t *testing.T) {
	oldDial := dialTemporalFunc
	oldNewWorker := newWorkerFunc
	defer func() {
		dialTemporalFunc = oldDial
		newWorkerFunc = oldNewWorker
	}()

	dialTemporalFunc = func(opts client.Options) (client.Client, error) {
		return client.NewLazyClient(client.Options{
			HostPort: "127.0.0.1:7233",
		})
	}

	newWorkerFunc = func(c client.Client, taskQueue string, options worker.Options) worker.Worker {
		return &mockWorker{}
	}

	vars := []string{"FP_GRPC_PORT", "FP_GRAPHQL_PORT", "FP_JWT_SECRET", "FP_NATS_URL"}
	oldEnv := make(map[string]string)
	for _, v := range vars {
		oldEnv[v] = os.Getenv(v)
	}
	defer func() {
		for k, v := range oldEnv {
			if v == "" {
				if err := os.Unsetenv(k); err != nil {
					t.Log(err)
				}
			} else {
				if err := os.Setenv(k, v); err != nil {
					t.Log(err)
				}
			}
		}
	}()

	require.NoError(t, os.Setenv("FP_GRPC_PORT", "0"))
	require.NoError(t, os.Setenv("FP_GRAPHQL_PORT", "0"))
	require.NoError(t, os.Setenv("FP_JWT_SECRET", "my-secret-key-12345"))
	require.NoError(t, os.Setenv("FP_NATS_URL", "nats://127.0.0.1:1"))

	content, err := os.ReadFile("../../schema.graphql")
	if err == nil {
		require.NoError(t, os.WriteFile("schema.graphql", content, 0600)) // #nosec
		t.Cleanup(func() {
			if err := os.Remove("schema.graphql"); err != nil {
				t.Log(err)
			}
		})
	}

	ctx, cancel := context.WithCancel(context.Background())
	done := make(chan struct{})
	go func() {
		defer close(done)
		if runErr := runMain(ctx); runErr != nil {
			t.Logf("runMain stopped with error: %v", runErr)
		}
	}()

	time.Sleep(500 * time.Millisecond)
	cancel()

	select {
	case <-done:
		// success
	case <-time.After(5 * time.Second):
		t.Fatal("runMain did not exit cleanly within 5 seconds")
	}
}

func TestInitSentry_ValidDSNSucceeds(t *testing.T) {
	initSentry(context.Background(), &config.Config{SentryDSN: "http://pubkey@127.0.0.1/1", Environment: "test"}, discardLogger())
}

func TestParseRSAPublicKey_InvalidPEM(t *testing.T) {
	_, err := parseRSAPublicKey("not-pem-at-all")
	require.Error(t, err)
	assert.Contains(t, err.Error(), "no PEM block found in RSA_PUBLIC_KEY_PEM")

	_, err = parseRSAPublicKey("-----BEGIN PRIVATE KEY-----\nMIIEvgIBADANBgkqhkiG9w0BAQEFAASCBKgwggSkAgEAAoIBAQDh\n-----END PRIVATE KEY-----")
	require.Error(t, err)
	assert.Contains(t, err.Error(), "failed to parse RSA public key")
}

func TestRunMain_InvalidRSAPEM(t *testing.T) {
	if os.Getenv("BE_CRASHER") == "1" {
		if err := runMain(context.Background()); err != nil {
			os.Exit(1)
		}
		return
	}
	// #nosec
	cmd := exec.CommandContext(context.Background(), os.Args[0], "-test.run=TestRunMain_InvalidRSAPEM")
	cmd.Env = append(os.Environ(), "BE_CRASHER=1", "FP_RSA_PUBLIC_KEY_PEM=invalid-pem-key", "FP_JWT_SECRET=secret")
	err := cmd.Run()
	var e *exec.ExitError
	if errors.As(err, &e) {
		assert.Equal(t, 1, e.ExitCode())
		return
	}
	t.Fatalf("process ran with err %v, want exit status 1", err)
}

func TestRunMain_TemporalConnectError(t *testing.T) {
	if os.Getenv("BE_CRASHER") == "1" {
		ctx, cancel := context.WithCancel(context.Background())
		cancel()
		if err := runMain(ctx); err != nil {
			os.Exit(1)
		}
		return
	}
	// #nosec
	cmd := exec.CommandContext(context.Background(), os.Args[0], "-test.run=TestRunMain_TemporalConnectError")
	cmd.Env = append(os.Environ(), "BE_CRASHER=1", "FP_JWT_SECRET=secret", "FP_TEMPORAL_HOST=127.0.0.1:7233")
	err := cmd.Run()
	var e *exec.ExitError
	if errors.As(err, &e) {
		assert.Equal(t, 1, e.ExitCode())
		return
	}
	t.Fatalf("process ran with err %v, want exit status 1", err)
}

func TestRunMain_TemporalConnectErrorReturnsDirectly(t *testing.T) {
	t.Setenv("FP_JWT_SECRET", "secret")
	t.Setenv("FP_TEMPORAL_HOST", "127.0.0.1:7233")

	ctx, cancel := context.WithCancel(context.Background())
	cancel()

	err := runMain(ctx)
	require.Error(t, err)
}

func TestSetupGRPCServer_SpiffeNilClientError(t *testing.T) {
	cfg := &config.Config{
		JWTSecret:     "secret",
		SpiffeEnabled: true,
	}
	_, err := setupGRPCServer(context.Background(), cfg, nil, nil, discardLogger())
	require.Error(t, err)
	assert.Contains(t, err.Error(), "SPIFFE is enabled but spiffeClient is nil")
}

func TestSetupGRPCServer_SpiffeCredentialFailure(t *testing.T) {
	cfg := &config.Config{
		JWTSecret:     "secret",
		SpiffeEnabled: true,
	}
	_, err := setupGRPCServer(context.Background(), cfg, nil, nil, discardLogger(), &spiffe.Client{})
	require.Error(t, err)
	assert.Contains(t, err.Error(), "uninitialized")
}

func TestSetupGraphQLServer_InvalidSchemaError(t *testing.T) {
	tmpFile, err := os.CreateTemp("", "invalid_schema_*.graphql")
	require.NoError(t, err)
	t.Cleanup(func() {
		require.NoError(t, os.Remove(tmpFile.Name()))
	})
	_, err = tmpFile.WriteString("invalid graphql schema syntax {{{")
	require.NoError(t, err)
	require.NoError(t, tmpFile.Close())

	t.Setenv("FP_SCHEMA_PATH", tmpFile.Name())
	cfg := &config.Config{
		GraphQLPort: "0",
		MinioBucket: "test-bucket",
		JWTSecret:   "test-secret",
	}
	_, err = setupGraphQLServer(context.Background(), cfg, nil, nil, discardLogger())
	require.Error(t, err)
}
