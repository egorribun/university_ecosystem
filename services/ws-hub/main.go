package main

import (
	"context"
	"crypto/tls"
	"encoding/json"
	"errors"
	"log/slog"
	"net"
	"net/http"
	"os"
	"os/signal"
	"sync"
	"syscall"
	"time"

	"github.com/nats-io/nats.go"
	"github.com/prometheus/client_golang/prometheus/promhttp"
	"github.com/quic-go/quic-go/http3"
	"github.com/quic-go/webtransport-go"
	"github.com/redis/go-redis/v9"
	"go.opentelemetry.io/contrib/instrumentation/net/http/otelhttp"

	"github.com/university-ecosystem/services/pkg/spiffe"
	"github.com/university-ecosystem/ws-hub/internal/telemetry"
	"github.com/university-ecosystem/ws-hub/pkg/config"
	"github.com/university-ecosystem/ws-hub/pkg/hub"
)

// Bootstrap seams keep failure handling deterministic in unit tests while
// production continues to use the concrete implementations below.
var (
	initTracerFunc          = telemetry.InitTracer
	initRedisFunc           = initRedis
	initSpiffeClientFunc    = initSpiffeClient
	setupHubFunc            = setupHub
	runServerFunc           = runServer
	newSpiffeClientFunc     = spiffe.NewClient
	closeRedisFunc          = func(client *redis.Client) error { return client.Close() }
	closeSpiffeClientFunc   = func(client *spiffe.Client) error { return client.Close() }
	setupJWKSFunc           = func(h *hub.Hub, ctx context.Context, url string) error { return h.SetupJWKS(ctx, url) }
	subscribeNATSFunc       = func(h *hub.Hub, ctx context.Context) error { return h.SubscribeToNATS(ctx) }
	configureAuthSPIFFEFunc = func(client *hub.InternalAPIAuthClient, spiffeClient *spiffe.Client, serverID string) {
		client.WithSPIFFE(spiffeClient, serverID)
	}
	healthNATSConnectedFunc   = func(conn *nats.Conn) bool { return conn != nil && conn.IsConnected() }
	healthRedisConfiguredFunc = func(client *redis.Client) bool { return client != nil }
	healthRedisPingFunc       = func(ctx context.Context, client *redis.Client) error {
		if client == nil {
			return nil
		}
		return client.Ping(ctx).Err()
	}
	healthJWKSReadyFunc    = func(h *hub.Hub) bool { return h.HasJWKSCache() }
	loadTLSCertFunc        = tls.LoadX509KeyPair
	listenUDPFunc          = net.ListenUDP
	closeUDPFunc           = func(conn *net.UDPConn) error { return conn.Close() }
	webTransportServeFunc  = func(server *webtransport.Server, conn net.PacketConn) error { return server.Serve(conn) }
	shutdownHTTPServerFunc = func(server *http.Server, ctx context.Context) error { return server.Shutdown(ctx) }
)

func main() {
	if err := run(); err != nil {
		os.Exit(1)
	}
}

func run() error {
	logger := initLogger()

	cfg := config.LoadConfig()
	if cfg.InternalSecret == "" {
		logger.ErrorContext(context.Background(), "WS_HUB_INTERNAL_SECRET is not set — generate with: openssl rand -hex 32")
		return errors.New("WS_HUB_INTERNAL_SECRET is not set")
	}

	if err := telemetry.InitSentry(cfg); err != nil {
		logger.ErrorContext(context.Background(), "Sentry initialization failed", "err", err)
	}

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	defer initializeTracerShutdown(ctx, cfg, logger)()

	nc, err := getInitNats()(ctx, cfg, logger)
	if err != nil {
		logger.ErrorContext(ctx, "NATS initialization returned error", "err", err)
		return err
	}
	defer closeNATSConnection(nc)

	rdb := initRedisFunc(ctx, cfg, logger)
	defer closeRedisConnection(ctx, rdb, logger)

	spiffeClient, err := initSpiffeClientFunc(ctx, cfg, logger)
	if err != nil {
		return err
	}
	defer closeSPIFFEClient(ctx, spiffeClient, logger)

	h, err := setupHubFunc(ctx, cfg, logger, nc, rdb, spiffeClient)
	if err != nil {
		logger.ErrorContext(ctx, "Hub setup failed", "err", err)
		return err
	}
	mux := http.NewServeMux()
	setupHandlers(mux, h, cfg, logger, nc, rdb)
	return runServerFunc(cfg, logger, h, mux)
}

func initializeTracerShutdown(ctx context.Context, cfg *config.Config, logger *slog.Logger) func() {
	tp, err := initTracerFunc(ctx, cfg)
	if err != nil {
		logger.ErrorContext(ctx, "OpenTelemetry initialization failed", "err", err)
		return func() {}
	}
	return func() {
		if err := tp.Shutdown(ctx); err != nil {
			logger.ErrorContext(ctx, "Failed to shutdown tracer provider", "err", err)
		}
	}
}

func closeNATSConnection(nc *nats.Conn) {
	if nc == nil {
		return
	}
	nc.Close()
}

func closeRedisConnection(ctx context.Context, rdb *redis.Client, logger *slog.Logger) {
	if rdb == nil {
		return
	}
	if err := closeRedisFunc(rdb); err != nil {
		logger.ErrorContext(ctx, "Failed to close Redis connection", "err", err)
	}
}

func closeSPIFFEClient(ctx context.Context, spiffeClient *spiffe.Client, logger *slog.Logger) {
	if spiffeClient == nil {
		return
	}
	if err := closeSpiffeClientFunc(spiffeClient); err != nil {
		logger.WarnContext(ctx, "Failed to close SPIFFE client", "err", err)
	}
}

func initSpiffeClient(ctx context.Context, cfg *config.Config, logger *slog.Logger) (*spiffe.Client, error) {
	client, err := newSpiffeClientFunc(ctx, spiffe.Config{
		Enabled:     cfg.SpiffeEnabled,
		SocketPath:  cfg.SpiffeEndpointSocket,
		TrustDomain: cfg.SpiffeTrustDomain,
		MySpiffeID:  cfg.SpiffeMyID,
	}, logger)
	if err != nil {
		logger.ErrorContext(ctx, "SPIFFE initialization failed", "err", err)
		if cfg.SpiffeEnabled {
			return nil, err
		}
		return nil, nil
	}
	if cfg.SpiffeEnabled && client == nil {
		logger.ErrorContext(ctx, "SPIFFE is enabled but client initialization returned nil")
		return nil, errors.New("SPIFFE is enabled but client initialization returned nil")
	}
	return client, nil
}

func initLogger() *slog.Logger {
	handler := slog.NewJSONHandler(os.Stdout, &slog.HandlerOptions{
		Level: slog.LevelInfo,
		ReplaceAttr: func(_ []string, a slog.Attr) slog.Attr {
			if a.Key == slog.TimeKey {
				a.Value = slog.StringValue(a.Value.Time().UTC().Format(time.RFC3339Nano))
			}
			return a
		},
	})
	return slog.New(handler)
}

var (
	initNatsMu sync.RWMutex
	initNats   = defaultInitNats
)

func getInitNats() func(context.Context, *config.Config, *slog.Logger) (*nats.Conn, error) {
	initNatsMu.RLock()
	defer initNatsMu.RUnlock()
	return initNats
}

func defaultInitNats(ctx context.Context, cfg *config.Config, logger *slog.Logger) (*nats.Conn, error) {
	natsOpts := []nats.Option{
		nats.RetryOnFailedConnect(true),
		nats.MaxReconnects(-1),
		nats.ReconnectWait(2 * time.Second),
	}
	if cfg.NatsUser != "" || cfg.NatsPassword != "" {
		natsOpts = append(natsOpts, nats.UserInfo(cfg.NatsUser, cfg.NatsPassword))
	}
	nc, err := nats.Connect(cfg.NatsURL, natsOpts...)
	if err != nil {
		logger.ErrorContext(ctx, "Failed to connect to NATS", "err", err)
		return nil, err
	}
	return nc, nil
}

func initRedis(ctx context.Context, cfg *config.Config, logger *slog.Logger) *redis.Client {
	rdb := redis.NewClient(&redis.Options{
		Addr:     cfg.RedisURL,
		Password: cfg.RedisPassword,
		DB:       cfg.RedisDB,
	})
	if err := rdb.Ping(ctx).Err(); err != nil {
		logger.WarnContext(ctx, "Redis connection failed, continuing without L2 cache", "err", err)
		if closeErr := closeRedisFunc(rdb); closeErr != nil {
			logger.WarnContext(ctx, "Failed to close Redis client after failed ping", "err", closeErr)
		}
		return nil
	}
	logger.InfoContext(ctx, "Redis connected (L2 Cache enabled)", "addr", cfg.RedisURL)
	return rdb
}

func setupHub(ctx context.Context, cfg *config.Config, logger *slog.Logger, nc *nats.Conn, rdb *redis.Client, spiffeClients ...*spiffe.Client) (*hub.Hub, error) {
	var spiffeClient *spiffe.Client
	if len(spiffeClients) > 0 {
		spiffeClient = spiffeClients[0]
	}
	authClient := hub.NewInternalAPIAuthClient(cfg.BackendURL, rdb)
	if cfg.SpiffeEnabled {
		if spiffeClient == nil {
			logger.ErrorContext(ctx, "SPIFFE is enabled but spiffeClient is nil")
			return nil, http.ErrServerClosed
		}
		configureAuthSPIFFEFunc(authClient, spiffeClient, cfg.BackendSpiffeID)
	}
	authClient.StartEviction(ctx)
	// RZ-W14-01: pass rdb so the Hub can validate one-time WS upgrade tickets
	//nolint:contextcheck
	h := hub.NewHub(nc, logger, authClient, cfg, rdb)

	if cfg.JWKSURL != "" {
		if err := setupJWKSFunc(h, ctx, cfg.JWKSURL); err != nil {
			logger.ErrorContext(ctx, "Failed to setup JWKS", "err", err)
			h.Stop()
			return nil, err
		}
	}

	limiterCtx, cancelLimiter := context.WithCancel(ctx)
	h.StartLimiterCleanup(limiterCtx)
	go h.Run(ctx)
	if nc != nil {
		if err := subscribeNATSFunc(h, ctx); err != nil {
			cancelLimiter()
			h.Stop()
			return nil, err
		}
	}
	hub.SetAllowedOrigins(cfg.AllowedOrigins)
	return h, nil
}

func setupHandlers(mux *http.ServeMux, h *hub.Hub, cfg *config.Config, logger *slog.Logger, nc *nats.Conn, rdb *redis.Client) {
	mux.Handle("/ws", otelhttp.NewHandler(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		h.HandleWebSocket(w, r, cfg)
	}), "websocket_upgrade"))

	mux.Handle("/wt", otelhttp.NewHandler(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		h.HandleWebTransport(w, r, cfg)
	}), "webtransport_upgrade"))

	// MOD-W17-05 (Wave 17): Separated liveness from readiness.
	// /health/live — always returns 200 if the process is running (K8s liveness).
	// /health/ready — checks NATS, Redis, and JWKS (K8s readiness).
	// /health — backward-compatible alias for /health/live.
	mux.Handle("/health/live", otelhttp.NewHandler(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if err := json.NewEncoder(w).Encode(map[string]string{"status": "alive"}); err != nil {
			logger.ErrorContext(r.Context(), "Failed to encode liveness response", "err", err)
		}
	}), "health_live"))

	// LOW-W19: cache the Redis ping result for 5 s so that rapid K8s readiness
	// probes (default 10 s interval, sometimes 1 s) do not open a new Redis
	// round-trip on every probe.  NATS and JWKS checks are in-memory and cheap.
	var (
		redisCacheMu      sync.Mutex
		redisCacheErr     error
		redisCacheUpdated time.Time
	)
	const redisCacheTTL = 5 * time.Second

	mux.Handle("/health/ready", otelhttp.NewHandler(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		checks := map[string]string{}
		if !healthNATSConnectedFunc(nc) {
			checks["nats"] = "disconnected"
		}
		if healthRedisConfiguredFunc(rdb) {
			redisCacheMu.Lock()
			if time.Since(redisCacheUpdated) > redisCacheTTL {
				redisCacheErr = healthRedisPingFunc(r.Context(), rdb)
				redisCacheUpdated = time.Now()
			}
			cachedErr := redisCacheErr
			redisCacheMu.Unlock()
			if cachedErr != nil {
				checks["redis"] = cachedErr.Error()
			}
		} else {
			checks["redis"] = "not configured"
		}
		if !healthJWKSReadyFunc(h) {
			checks["jwks"] = "not initialized"
		}
		if len(checks) > 0 {
			w.WriteHeader(http.StatusServiceUnavailable)
			if err := json.NewEncoder(w).Encode(map[string]interface{}{
				"status": "degraded", "checks": checks,
			}); err != nil {
				logger.ErrorContext(r.Context(), "Failed to encode readiness response", "err", err)
			}
			return
		}
		if err := json.NewEncoder(w).Encode(map[string]string{"status": "ready"}); err != nil {
			logger.ErrorContext(r.Context(), "Failed to encode readiness response", "err", err)
		}
	}), "health_ready"))

	// Backward-compatible /health (alias for /health/live).
	mux.Handle("/health", otelhttp.NewHandler(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if err := json.NewEncoder(w).Encode(map[string]string{"status": "healthy"}); err != nil {
			logger.ErrorContext(r.Context(), "Failed to encode health check response", "err", err)
		}
	}), "health_check"))

	mux.Handle("/metrics", promhttp.Handler())
}

// startupPacketConn exposes a readiness barrier after webtransport.Server.Serve
// has registered its internal shutdown wait group. webtransport-go's Serve and
// Close must not be called concurrently before that registration completes.
type startupPacketConn struct {
	net.PacketConn
	ready     chan<- struct{}
	readyOnce sync.Once
}

func (c *startupPacketConn) signalReady() {
	c.readyOnce.Do(func() { close(c.ready) })
}

func (c *startupPacketConn) LocalAddr() net.Addr {
	c.signalReady()
	return c.PacketConn.LocalAddr()
}

func (c *startupPacketConn) ReadFrom(p []byte) (int, net.Addr, error) {
	c.signalReady()
	return c.PacketConn.ReadFrom(p)
}

func (c *startupPacketConn) WriteTo(p []byte, addr net.Addr) (int, error) {
	c.signalReady()
	return c.PacketConn.WriteTo(p, addr)
}

func serveWebTransport(wtServer *webtransport.Server, wtPort string, cfg *config.Config, logger *slog.Logger, ready chan<- struct{}) error {
	addr, err := net.ResolveUDPAddr("udp", ":"+wtPort)
	if err != nil {
		return err
	}
	conn, err := listenUDPFunc("udp", addr)
	if err != nil {
		return err
	}
	defer func() {
		if err := closeUDPFunc(conn); err != nil {
			logger.WarnContext(context.Background(), "WebTransport UDP socket close failed", "err", err)
		}
	}()

	if cfg.TLSCertFile != "" && cfg.TLSKeyFile != "" {
		cert, err := loadTLSCertFunc(cfg.TLSCertFile, cfg.TLSKeyFile)
		if err != nil {
			return err
		}
		wtServer.H3.TLSConfig = &tls.Config{
			Certificates: []tls.Certificate{cert},
			MinVersion:   tls.VersionTLS13,
		}
	} else {
		logger.WarnContext(context.Background(), "WebTransport TLS cert files not configured; attempting ListenAndServe fallback")
	}

	return webTransportServeFunc(wtServer, &startupPacketConn{PacketConn: conn, ready: ready})
}

func setupSignalChannel(signalChannels ...chan os.Signal) (<-chan os.Signal, func()) {
	if len(signalChannels) > 0 && signalChannels[0] != nil {
		return signalChannels[0], func() {}
	}

	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)
	return quit, func() { signal.Stop(quit) }
}

func waitForWebTransportStartup(quit <-chan os.Signal, ready <-chan struct{}, done <-chan struct{}, errChan <-chan error, logger *slog.Logger) (error, bool) {
	select {
	case <-ready:
		return nil, false
	case <-done:
		return nil, false
	case err := <-errChan:
		logger.ErrorContext(context.Background(), "Server error", "err", err)
		select {
		case <-ready:
		case <-done:
		}
		return err, true
	case <-quit:
		select {
		case <-ready:
		case <-done:
		}
		return nil, true
	}
}

func waitForShutdown(quit <-chan os.Signal, errChan <-chan error, logger *slog.Logger) error {
	select {
	case err := <-errChan:
		logger.ErrorContext(context.Background(), "Server error", "err", err)
		return err
	case <-quit:
		return nil
	}
}

func shutdownWebTransport(wtServer *webtransport.Server, done <-chan struct{}) {
	select {
	case <-done:
		return
	default:
		//nolint:errcheck
		_ = wtServer.Close()
		<-done
	}
}

func runServer(cfg *config.Config, logger *slog.Logger, h *hub.Hub, mux *http.ServeMux, signalChannels ...chan os.Signal) error {
	server := &http.Server{
		Addr:              ":" + cfg.Port,
		Handler:           mux,
		ReadTimeout:       10 * time.Second,
		WriteTimeout:      10 * time.Second,
		IdleTimeout:       120 * time.Second,
		ReadHeaderTimeout: 5 * time.Second,
		MaxHeaderBytes:    1 << 13,
	}

	wtPort := cfg.WebTransportPort
	if wtPort == "" {
		wtPort = "8443"
	}

	wtServer := &webtransport.Server{
		H3: &http3.Server{
			Addr: ":" + wtPort,
		},
		CheckOrigin: func(r *http.Request) bool {
			return true
		},
	}

	quit, stopSignals := setupSignalChannel(signalChannels...)
	defer stopSignals()

	// RZ-33-07: Use channel-based error propagation instead of os.Exit in
	// goroutine — ensures deferred cleanup (NATS close, Redis close, tracer
	// shutdown) always executes. Matches gateway pattern (RZ-31-01).
	errChan := make(chan error, 2)
	go func() {
		logger.InfoContext(context.Background(), "Starting WebSocket Hub (TCP)", "port", cfg.Port)
		if err := server.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			errChan <- err
		}
	}()

	wtReady := make(chan struct{})
	wtDone := make(chan struct{})
	go func() {
		defer close(wtDone)
		logger.InfoContext(context.Background(), "Starting WebTransport Hub (UDP HTTP/3)", "port", wtPort)
		err := serveWebTransport(wtServer, wtPort, cfg, logger, wtReady)
		if err != nil && err != http.ErrServerClosed {
			logger.WarnContext(context.Background(), "WebTransport HTTP/3 listener stopped", "err", err)
		}
	}()

	runErr, shutdownRequested := waitForWebTransportStartup(quit, wtReady, wtDone, errChan, logger)
	if !shutdownRequested {
		runErr = waitForShutdown(quit, errChan, logger)
	}

	logger.InfoContext(context.Background(), "Shutting down...")
	shutdownCtx, shutdownCancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer shutdownCancel()

	h.Stop()
	shutdownWebTransport(wtServer, wtDone)
	if err := shutdownHTTPServerFunc(server, shutdownCtx); err != nil {
		logger.ErrorContext(context.Background(), "Server forced to shutdown", "err", err)
	}
	return runErr
}
