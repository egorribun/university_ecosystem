// Gateway router, server, telemetry, and lifecycle contracts.
package main

import (
	"context"
	"errors"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/alicebob/miniredis/v2"
	"github.com/gin-gonic/gin"
	"github.com/prometheus/client_golang/prometheus"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	pb "github.com/university-ecosystem/core/gen/go/file_processor/v1"
	"github.com/university-ecosystem/gateway/internal/config"
	"github.com/university-ecosystem/gateway/middleware"
	"github.com/university-ecosystem/services/pkg/spiffe"
	"go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracegrpc"
	"go.opentelemetry.io/otel/sdk/resource"
	sdktrace "go.opentelemetry.io/otel/sdk/trace"
	"google.golang.org/grpc"
)

func minimalRouterConfig() *config.Config {
	return &config.Config{
		BackendURL:         "http://127.0.0.1:1",
		WsHubURL:           "http://127.0.0.1:1",
		RedisURL:           "not-a-redis-url",
		RevocationRedisURL: "not-a-redis-url",
		JWTSecret:          routeBranchJWTSecret,
		AllowedOrigins:     []string{"http://localhost"},
		InternalHMACSecret: "coverage-closure-internal-secret",
	}
}

func TestSetupRouter_FailsClosedWhenTrustedProxyConfigurationFails(t *testing.T) {
	old := setTrustedProxiesFunc
	t.Cleanup(func() { setTrustedProxiesFunc = old })
	wantErr := errors.New("synthetic trusted proxy failure")
	setTrustedProxiesFunc = func(*gin.Engine, []string) error { return wantErr }

	router, err := setupRouter(
		minimalRouterConfig(),
		slog.New(slog.NewTextHandler(io.Discard, nil)),
		nil,
		nil,
		t.Context(),
	)

	assert.Nil(t, router)
	assert.ErrorIs(t, err, wantErr)
}

func TestSetupRouter_LogsPrometheusCollectorRegistrationFailure(t *testing.T) {
	oldProm := setupGinPrometheusFunc
	t.Cleanup(func() { setupGinPrometheusFunc = oldProm })
	setupGinPrometheusFunc = func(*gin.Engine) {}
	mr := miniredis.RunT(t)
	old := registerPrometheusCollectorFunc
	t.Cleanup(func() { registerPrometheusCollectorFunc = old })
	registerPrometheusCollectorFunc = func(prometheus.Collector) error {
		return errors.New("synthetic collector registration failure")
	}
	cfg := minimalRouterConfig()
	cfg.RedisURL = "redis://" + mr.Addr()

	router, err := setupRouter(
		cfg,
		slog.New(slog.NewTextHandler(io.Discard, nil)),
		nil,
		nil,
		t.Context(),
	)

	require.NoError(t, err)
	assert.NotNil(t, router)
}

func TestSetupRouter_OptionalRouteAbortStopsProxy(t *testing.T) {
	oldProm := setupGinPrometheusFunc
	t.Cleanup(func() { setupGinPrometheusFunc = oldProm })
	setupGinPrometheusFunc = func(*gin.Engine) {}
	old := optionalAuthHandlerFunc
	t.Cleanup(func() { optionalAuthHandlerFunc = old })
	optionalAuthHandlerFunc = func(*middleware.JWTMiddleware, context.Context) gin.HandlerFunc {
		return func(c *gin.Context) { c.AbortWithStatus(http.StatusTeapot) }
	}
	router, err := setupRouter(
		minimalRouterConfig(),
		slog.New(slog.NewTextHandler(io.Discard, nil)),
		nil,
		nil,
		t.Context(),
	)
	require.NoError(t, err)

	for _, path := range []string{"/api/public/config", "/graphql"} {
		recorder := httptest.NewRecorder()
		request := httptest.NewRequestWithContext(t.Context(), http.MethodGet, path, nil)
		router.ServeHTTP(recorder, request)
		assert.Equal(t, http.StatusTeapot, recorder.Code, path)
	}
}

func TestRun_ClosesGRPCConnectionWhenRouterSetupFails(t *testing.T) {
	setValidRunEnvironment(t)
	oldTracer := initTracerFunc
	oldGRPC := initGRPCFunc
	oldSetup := setupRouterFunc
	oldClose := closeGRPCConnFunc
	t.Cleanup(func() {
		initTracerFunc = oldTracer
		initGRPCFunc = oldGRPC
		setupRouterFunc = oldSetup
		closeGRPCConnFunc = oldClose
	})
	initTracerFunc = func(context.Context, *config.Config) (*sdktrace.TracerProvider, error) {
		return nil, errors.New("tracing disabled in test")
	}
	initGRPCFunc = func(*config.Config, *slog.Logger, ...*spiffe.Client) (*grpc.ClientConn, pb.FileProcessingServiceClient, error) {
		return &grpc.ClientConn{}, nil, nil
	}
	wantErr := errors.New("synthetic router setup failure")
	setupRouterFunc = func(*config.Config, *slog.Logger, *grpc.ClientConn, pb.FileProcessingServiceClient, ...any) (*gin.Engine, error) {
		return nil, wantErr
	}
	closeCalled := false
	closeGRPCConnFunc = func(*grpc.ClientConn) error {
		closeCalled = true
		return errors.New("synthetic close failure")
	}

	assert.ErrorIs(t, run(), wantErr)
	assert.True(t, closeCalled)
}

func TestRun_WaitsForRouterCleanupEvenWhenCleanupFails(t *testing.T) {
	setValidRunEnvironment(t)
	t.Setenv("GATEWAY_PORT", "-1")
	t.Setenv("GATEWAY_H3_ENABLED", "false")
	oldTracer := initTracerFunc
	oldGRPC := initGRPCFunc
	oldSetup := setupRouterFunc
	oldCloseGRPC := closeGRPCConnFunc
	oldCloseRateLimiter := closeRateLimiterFunc
	t.Cleanup(func() {
		initTracerFunc = oldTracer
		initGRPCFunc = oldGRPC
		setupRouterFunc = oldSetup
		closeGRPCConnFunc = oldCloseGRPC
		closeRateLimiterFunc = oldCloseRateLimiter
	})
	initTracerFunc = func(context.Context, *config.Config) (*sdktrace.TracerProvider, error) {
		return nil, errors.New("tracing disabled in test")
	}
	initGRPCFunc = func(*config.Config, *slog.Logger, ...*spiffe.Client) (*grpc.ClientConn, pb.FileProcessingServiceClient, error) {
		return &grpc.ClientConn{}, nil, nil
	}
	closeGRPCConnFunc = func(*grpc.ClientConn) error { return nil }
	setupRouterFunc = func(_ *config.Config, _ *slog.Logger, _ *grpc.ClientConn, _ pb.FileProcessingServiceClient, opts ...any) (*gin.Engine, error) {
		for _, opt := range opts {
			if lifecycle, ok := opt.(*routerLifecycle); ok {
				lifecycle.rateLimiter = &middleware.RateLimiter{}
			}
		}
		return gin.New(), nil
	}
	cleanupCalled := false
	closeRateLimiterFunc = func(*middleware.RateLimiter) error {
		cleanupCalled = true
		return errors.New("synthetic router cleanup failure")
	}

	require.Error(t, run())
	require.True(t, cleanupCalled, "run must wait for synchronous router cleanup before returning")
}

type recordingSpanExporter struct {
	shutdownCalled bool
}

func (*recordingSpanExporter) ExportSpans(context.Context, []sdktrace.ReadOnlySpan) error {
	return nil
}

func (exporter *recordingSpanExporter) Shutdown(context.Context) error {
	exporter.shutdownCalled = true
	return nil
}

func TestInitTracer_PropagatesConstructionFailuresAndCleansUpExporter(t *testing.T) {
	oldExporter := newOTLPTraceExporterFunc
	oldResource := newOTelResourceFunc
	t.Cleanup(func() {
		newOTLPTraceExporterFunc = oldExporter
		newOTelResourceFunc = oldResource
	})
	cfg := &config.Config{OtelEndpoint: "localhost:4317"}
	exporterErr := errors.New("synthetic exporter failure")
	newOTLPTraceExporterFunc = func(context.Context, ...otlptracegrpc.Option) (sdktrace.SpanExporter, error) {
		return nil, exporterErr
	}

	tp, err := initTracer(context.Background(), cfg)
	assert.Nil(t, tp)
	assert.ErrorIs(t, err, exporterErr)

	exporter := &recordingSpanExporter{}
	newOTLPTraceExporterFunc = func(context.Context, ...otlptracegrpc.Option) (sdktrace.SpanExporter, error) {
		return exporter, nil
	}
	resourceErr := errors.New("synthetic resource failure")
	newOTelResourceFunc = func(context.Context, ...resource.Option) (*resource.Resource, error) {
		return nil, resourceErr
	}

	tp, err = initTracer(context.Background(), cfg)
	assert.Nil(t, tp)
	assert.ErrorIs(t, err, resourceErr)
	assert.True(t, exporter.shutdownCalled)
}

func TestSetupRouter_ContextCancellationClosesOwnedLifecycle(t *testing.T) {
	oldProm := setupGinPrometheusFunc
	t.Cleanup(func() { setupGinPrometheusFunc = oldProm })
	setupGinPrometheusFunc = func(*gin.Engine) {}
	ctx, cancel := context.WithCancel(context.Background())
	router, err := setupRouter(
		minimalRouterConfig(),
		slog.New(slog.NewTextHandler(io.Discard, nil)),
		nil,
		nil,
		ctx,
	)
	require.NoError(t, err)
	assert.NotNil(t, router)
	cancel()
}
