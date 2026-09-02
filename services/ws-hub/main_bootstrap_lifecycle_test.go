// Bootstrap lifecycle and resource-cleanup contracts.
package main

import (
	"context"
	"crypto/tls"
	"errors"
	"io"
	"log/slog"
	"net"
	"net/http"
	"net/http/httptest"
	"os"
	"strconv"
	"testing"

	"github.com/nats-io/nats.go"
	"github.com/quic-go/quic-go/http3"
	"github.com/quic-go/webtransport-go"
	"github.com/redis/go-redis/v9"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"github.com/university-ecosystem/services/pkg/spiffe"
	"github.com/university-ecosystem/ws-hub/pkg/config"
	"github.com/university-ecosystem/ws-hub/pkg/hub"
	sdktrace "go.opentelemetry.io/otel/sdk/trace"
)

func resetBootstrapSeams(t *testing.T) {
	t.Helper()
	oldTracer := initTracerFunc
	oldRedis := initRedisFunc
	oldRevocationRedis := initRevocationRedisFunc
	oldSpiffe := initSpiffeClientFunc
	oldSetupHub := setupHubFunc
	oldRunServer := runServerFunc
	oldNewSpiffe := newSpiffeClientFunc
	oldCloseRedis := closeRedisFunc
	oldCloseSpiffe := closeSpiffeClientFunc
	oldSetupJWKS := setupJWKSFunc
	oldSubscribe := subscribeNATSFunc
	oldConfigureSPIFFE := configureAuthSPIFFEFunc
	oldNATSConnected := healthNATSConnectedFunc
	oldRedisConfigured := healthRedisConfiguredFunc
	oldRedisPing := healthRedisPingFunc
	oldJWKSReady := healthJWKSReadyFunc
	oldLoadTLS := loadTLSCertFunc
	oldListenUDP := listenUDPFunc
	oldCloseUDP := closeUDPFunc
	oldServeWT := webTransportServeFunc
	oldShutdown := shutdownHTTPServerFunc
	t.Cleanup(func() {
		initTracerFunc = oldTracer
		initRedisFunc = oldRedis
		initRevocationRedisFunc = oldRevocationRedis
		initSpiffeClientFunc = oldSpiffe
		setupHubFunc = oldSetupHub
		runServerFunc = oldRunServer
		newSpiffeClientFunc = oldNewSpiffe
		closeRedisFunc = oldCloseRedis
		closeSpiffeClientFunc = oldCloseSpiffe
		setupJWKSFunc = oldSetupJWKS
		subscribeNATSFunc = oldSubscribe
		configureAuthSPIFFEFunc = oldConfigureSPIFFE
		healthNATSConnectedFunc = oldNATSConnected
		healthRedisConfiguredFunc = oldRedisConfigured
		healthRedisPingFunc = oldRedisPing
		healthJWKSReadyFunc = oldJWKSReady
		loadTLSCertFunc = oldLoadTLS
		listenUDPFunc = oldListenUDP
		closeUDPFunc = oldCloseUDP
		webTransportServeFunc = oldServeWT
		shutdownHTTPServerFunc = oldShutdown
	})
	initTracerFunc = func(context.Context, *config.Config) (*sdktrace.TracerProvider, error) {
		return nil, errors.New("tracer disabled for test")
	}
	initRedisFunc = func(context.Context, *config.Config, *slog.Logger) *redis.Client { return nil }
	initRevocationRedisFunc = func(context.Context, *config.Config, *slog.Logger) (*redis.Client, error) {
		return nil, nil
	}
	setTestInitNATS(t, func(context.Context, *config.Config, *slog.Logger) (*nats.Conn, error) {
		return nil, nil
	})
}

func setTestInitNATS(t *testing.T, fn func(context.Context, *config.Config, *slog.Logger) (*nats.Conn, error)) {
	t.Helper()
	initNatsMu.Lock()
	previous := initNats
	initNats = fn
	initNatsMu.Unlock()
	t.Cleanup(func() {
		initNatsMu.Lock()
		initNats = previous
		initNatsMu.Unlock()
	})
}

func TestRun_BootstrapFailureStagesArePropagated(t *testing.T) {
	t.Setenv("WS_HUB_INTERNAL_SECRET", "test-secret-at-least-32-characters-long")

	t.Run("revocation Redis initialization", func(t *testing.T) {
		resetBootstrapSeams(t)
		want := errors.New("revocation Redis unavailable")
		initRevocationRedisFunc = func(context.Context, *config.Config, *slog.Logger) (*redis.Client, error) {
			return nil, want
		}
		assert.ErrorIs(t, run(), want)
	})

	t.Run("spiffe initialization", func(t *testing.T) {
		resetBootstrapSeams(t)
		want := errors.New("spiffe unavailable")
		initSpiffeClientFunc = func(context.Context, *config.Config, *slog.Logger) (*spiffe.Client, error) {
			return nil, want
		}
		assert.ErrorIs(t, run(), want)
	})

	t.Run("hub setup", func(t *testing.T) {
		resetBootstrapSeams(t)
		want := errors.New("hub setup failed")
		initSpiffeClientFunc = func(context.Context, *config.Config, *slog.Logger) (*spiffe.Client, error) {
			return nil, nil
		}
		setupHubFunc = func(context.Context, *config.Config, *slog.Logger, *nats.Conn, *redis.Client, *redis.Client, ...*spiffe.Client) (*hub.Hub, error) {
			return nil, want
		}
		assert.ErrorIs(t, run(), want)
	})

	t.Run("server", func(t *testing.T) {
		resetBootstrapSeams(t)
		want := errors.New("server failed")
		initSpiffeClientFunc = func(context.Context, *config.Config, *slog.Logger) (*spiffe.Client, error) {
			return nil, nil
		}
		setupHubFunc = func(context.Context, *config.Config, *slog.Logger, *nats.Conn, *redis.Client, *redis.Client, ...*spiffe.Client) (*hub.Hub, error) {
			return nil, nil
		}
		runServerFunc = func(*config.Config, *slog.Logger, *hub.Hub, *http.ServeMux, ...chan os.Signal) error {
			return want
		}
		assert.ErrorIs(t, run(), want)
	})
}

func TestRun_InvalidListenPortsFailBeforeExternalInitialization(t *testing.T) {
	t.Setenv("WS_HUB_INTERNAL_SECRET", "test-secret-at-least-32-characters-long")

	for _, testCase := range []struct {
		name     string
		envName  string
		envValue string
	}{
		{name: "websocket negative", envName: "WS_HUB_PORT", envValue: "-1"},
		{name: "webtransport above range", envName: "WS_HUB_WT_PORT", envValue: "65536"},
	} {
		t.Run(testCase.name, func(t *testing.T) {
			resetBootstrapSeams(t)
			t.Setenv("WS_HUB_PORT", "0")
			t.Setenv("WS_HUB_WT_PORT", "0")
			t.Setenv(testCase.envName, testCase.envValue)
			natsCalled := false
			setTestInitNATS(t, func(context.Context, *config.Config, *slog.Logger) (*nats.Conn, error) {
				natsCalled = true
				return nil, errors.New("NATS must not initialize for an invalid listen port")
			})

			err := run()

			assert.ErrorContains(t, err, "listen port must be between 0 and 65535")
			assert.False(t, natsCalled)
		})
	}
}

func TestInitializeTracerShutdown_InitializesNoopOnError(t *testing.T) {
	resetBootstrapSeams(t)
	cleanup := initializeTracerShutdown(context.Background(), &config.Config{}, slog.New(slog.NewTextHandler(io.Discard, nil)))
	assert.NotPanics(t, cleanup)
}

func TestCleanupHelpers_ReportCloseErrors(t *testing.T) {
	resetBootstrapSeams(t)
	closeRedisFunc = func(*redis.Client) error { return errors.New("redis close failed") }
	closeSpiffeClientFunc = func(*spiffe.Client) error { return errors.New("spiffe close failed") }
	assert.NotPanics(t, func() {
		closeRedisConnection(context.Background(), redis.NewClient(&redis.Options{Addr: "127.0.0.1:1"}), slog.New(slog.NewTextHandler(io.Discard, nil)))
		closeSPIFFEClient(context.Background(), &spiffe.Client{}, slog.New(slog.NewTextHandler(io.Discard, nil)))
	})
}

func TestInitSpiffeClient_EnabledNilClientIsRejected(t *testing.T) {
	resetBootstrapSeams(t)
	newSpiffeClientFunc = func(context.Context, spiffe.Config, *slog.Logger) (*spiffe.Client, error) {
		return nil, nil
	}
	client, err := initSpiffeClient(context.Background(), &config.Config{SpiffeEnabled: true}, slog.New(slog.NewTextHandler(io.Discard, nil)))
	assert.Nil(t, client)
	assert.EqualError(t, err, "SPIFFE is enabled but client initialization returned nil")
}

func TestInitSpiffeClient_DisabledErrorFallsBackToNil(t *testing.T) {
	resetBootstrapSeams(t)
	newSpiffeClientFunc = func(context.Context, spiffe.Config, *slog.Logger) (*spiffe.Client, error) {
		return nil, errors.New("optional SPIFFE unavailable")
	}
	client, err := initSpiffeClient(context.Background(), &config.Config{SpiffeEnabled: false}, slog.New(slog.NewTextHandler(io.Discard, nil)))
	assert.Nil(t, client)
	assert.NoError(t, err)
}

func TestInitRedis_ReportsCloseFailureAfterPingFailure(t *testing.T) {
	resetBootstrapSeams(t)
	closeRedisFunc = func(*redis.Client) error { return errors.New("close after ping failed") }
	assert.Nil(t, initRedis(context.Background(), &config.Config{RedisURL: "127.0.0.1:1"}, slog.New(slog.NewTextHandler(io.Discard, nil))))
}

func TestSetupHub_CleansUpOnJWKSAndSubscriptionFailures(t *testing.T) {
	resetBootstrapSeams(t)
	setupJWKSFunc = func(*hub.Hub, context.Context, string) error { return errors.New("jwks setup failed") }
	h, err := setupHub(context.Background(), &config.Config{JWKSURL: "http://jwks.test"}, slog.New(slog.NewTextHandler(io.Discard, nil)), nil, nil)
	assert.Nil(t, h)
	assert.EqualError(t, err, "jwks setup failed")

	resetBootstrapSeams(t)
	subscribeNATSFunc = func(*hub.Hub, context.Context) error {
		return errors.New("subscription failed")
	}
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	h, err = setupHub(ctx, &config.Config{}, slog.New(slog.NewTextHandler(io.Discard, nil)), &nats.Conn{}, nil)
	assert.Nil(t, h)
	assert.EqualError(t, err, "subscription failed")
}

func TestSetupHub_ConfiguresSPIFFEAuthClient(t *testing.T) {
	resetBootstrapSeams(t)
	// Exercise the production default wrapper with a disabled SPIFFE client
	// before replacing it with the deterministic success seam below.
	configureAuthSPIFFEFunc(hub.NewInternalAPIAuthClient("http://auth.test", nil), nil, "")
	configured := false
	configureAuthSPIFFEFunc = func(*hub.InternalAPIAuthClient, *spiffe.Client, string) {
		configured = true
	}
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	h, err := setupHub(ctx, &config.Config{SpiffeEnabled: true, BackendSpiffeID: "spiffe://backend"}, slog.New(slog.NewTextHandler(io.Discard, nil)), nil, nil, &spiffe.Client{})
	require.NoError(t, err)
	require.NotNil(t, h)
	h.Stop()
	assert.True(t, configured)
}

func TestRunServer_UsesDefaultWebTransportPortAndReportsHTTPShutdownError(t *testing.T) {
	resetBootstrapSeams(t)
	wantShutdown := errors.New("http shutdown failed")
	webTransportServeFunc = func(*webtransport.Server, net.PacketConn) error {
		return errors.New("webtransport stopped")
	}
	shutdownHTTPServerFunc = func(*http.Server, context.Context) error { return wantShutdown }
	quit := make(chan os.Signal, 1)
	quit <- os.Interrupt
	cfg := &config.Config{Port: "0", WebTransportPort: ""}
	h := hub.NewHub(nil, slog.New(slog.NewTextHandler(io.Discard, nil)), nil, cfg, nil)
	assert.NoError(t, runServer(cfg, slog.New(slog.NewTextHandler(io.Discard, nil)), h, http.NewServeMux(), quit))
}

type errorResponseWriter struct {
	header http.Header
	status int
}

func (w *errorResponseWriter) Header() http.Header { return w.header }

func (w *errorResponseWriter) WriteHeader(status int) { w.status = status }

func (w *errorResponseWriter) Write([]byte) (int, error) {
	return 0, errors.New("response write failed")
}

func TestSetupHandlers_EncoderAndTransportBranches(t *testing.T) {
	h := hub.NewHub(nil, slog.New(slog.NewTextHandler(io.Discard, nil)), nil, &config.Config{}, nil)
	mux := http.NewServeMux()
	setupHandlers(mux, h, &config.Config{}, slog.New(slog.NewTextHandler(io.Discard, nil)), nil, nil)

	for _, path := range []string{"/health/live", "/health", "/health/ready", "/wt"} {
		writer := &errorResponseWriter{header: make(http.Header)}
		req := httptest.NewRequest(http.MethodGet, path, nil)
		mux.ServeHTTP(writer, req)
	}
}

func TestSetupHandlers_ReadinessReadyEncodeFailure(t *testing.T) {
	resetBootstrapSeams(t)
	assert.NoError(t, healthRedisPingFunc(context.Background(), nil))
	healthNATSConnectedFunc = func(*nats.Conn) bool { return true }
	healthRedisConfiguredFunc = func(*redis.Client) bool { return true }
	healthRedisPingFunc = func(context.Context, *redis.Client) error { return nil }
	healthJWKSReadyFunc = func(*hub.Hub) bool { return true }

	h := hub.NewHub(nil, slog.New(slog.NewTextHandler(io.Discard, nil)), nil, &config.Config{}, nil)
	mux := http.NewServeMux()
	setupHandlers(mux, h, &config.Config{}, slog.New(slog.NewTextHandler(io.Discard, nil)), nil, nil)
	writer := &errorResponseWriter{header: make(http.Header)}
	mux.ServeHTTP(writer, httptest.NewRequest(http.MethodGet, "/health/ready", nil))
}

func TestServeWebTransport_LoadsConfiguredTLSCertificate(t *testing.T) {
	resetBootstrapSeams(t)
	loadTLSCertFunc = func(string, string) (tls.Certificate, error) { return tls.Certificate{}, nil }
	webTransportServeFunc = func(*webtransport.Server, net.PacketConn) error { return errors.New("serve stopped") }
	cfg := &config.Config{TLSCertFile: "cert.pem", TLSKeyFile: "key.pem"}
	err := serveWebTransport(&webtransport.Server{H3: &http3.Server{}}, "0", cfg, slog.New(slog.NewTextHandler(io.Discard, nil)), make(chan struct{}))
	assert.EqualError(t, err, "serve stopped")
}

func TestServeWebTransport_ReportsUDPCloseFailure(t *testing.T) {
	resetBootstrapSeams(t)
	closeUDPFunc = func(*net.UDPConn) error { return errors.New("udp close failed") }
	webTransportServeFunc = func(*webtransport.Server, net.PacketConn) error { return errors.New("serve stopped") }
	err := serveWebTransport(&webtransport.Server{H3: &http3.Server{}}, "0", &config.Config{}, slog.New(slog.NewTextHandler(io.Discard, nil)), make(chan struct{}))
	assert.EqualError(t, err, "serve stopped")
}

func TestServeWebTransport_RejectsOccupiedPort(t *testing.T) {
	listener, err := net.ListenUDP("udp", &net.UDPAddr{IP: net.IPv4zero, Port: 0})
	require.NoError(t, err)
	t.Cleanup(func() { _ = listener.Close() }) //nolint:errcheck
	port := listener.LocalAddr().(*net.UDPAddr).Port
	err = serveWebTransport(&webtransport.Server{H3: &http3.Server{}}, strconv.Itoa(port), &config.Config{}, slog.New(slog.NewTextHandler(io.Discard, nil)), make(chan struct{}))
	assert.Error(t, err)
}
