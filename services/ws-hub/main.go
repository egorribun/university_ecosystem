package main

import (
	"context"
	"encoding/json"
	"log/slog"
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

func main() {
	logger := initLogger()

	cfg := config.LoadConfig()
	if cfg.InternalSecret == "" {
		logger.ErrorContext(context.Background(), "WS_HUB_INTERNAL_SECRET is not set — generate with: openssl rand -hex 32")
		os.Exit(1)
	}

	if err := telemetry.InitSentry(cfg); err != nil {
		logger.ErrorContext(context.Background(), "Sentry initialization failed", "err", err)
	}

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	tp, err := telemetry.InitTracer(ctx, cfg)
	if err == nil {
		defer func() {
			if err := tp.Shutdown(ctx); err != nil {
				logger.ErrorContext(ctx, "Failed to shutdown tracer provider", "err", err)
			}
		}()
	} else {
		logger.ErrorContext(ctx, "OpenTelemetry initialization failed", "err", err)
	}

	nc := initNats(ctx, cfg, logger)
	if nc != nil {
		defer nc.Close()
	}

	rdb := initRedis(ctx, cfg, logger)
	if rdb != nil {
		defer func() {
			if err := rdb.Close(); err != nil {
				logger.ErrorContext(context.Background(), "Failed to close Redis connection", "err", err)
			}
		}()
	}

	spiffeClient, err := spiffe.NewClient(ctx, spiffe.Config{
		Enabled:     cfg.SpiffeEnabled,
		SocketPath:  cfg.SpiffeEndpointSocket,
		TrustDomain: cfg.SpiffeTrustDomain,
		MySpiffeID:  cfg.SpiffeMyID,
	}, logger)
	if err != nil {
		logger.ErrorContext(ctx, "SPIFFE initialization failed", "err", err)
		if cfg.SpiffeEnabled {
			os.Exit(1)
		}
	} else if cfg.SpiffeEnabled && spiffeClient == nil {
		logger.ErrorContext(ctx, "SPIFFE is enabled but client initialization returned nil")
		os.Exit(1)
	} else if spiffeClient != nil {
		defer func() {
			if err := spiffeClient.Close(); err != nil {
				logger.WarnContext(ctx, "Failed to close SPIFFE client", "err", err)
			}
		}()
	}

	h := setupHub(ctx, cfg, logger, nc, rdb, spiffeClient)
	mux := http.NewServeMux()
	setupHandlers(mux, h, cfg, logger, nc, rdb)
	runServer(cfg, logger, h, mux)
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

var initNats = func(ctx context.Context, cfg *config.Config, logger *slog.Logger) *nats.Conn {
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
		os.Exit(1)
	}
	return nc
}

func initRedis(ctx context.Context, cfg *config.Config, logger *slog.Logger) *redis.Client {
	rdb := redis.NewClient(&redis.Options{
		Addr:     cfg.RedisURL,
		Password: cfg.RedisPassword,
		DB:       cfg.RedisDB,
	})
	if err := rdb.Ping(ctx).Err(); err != nil {
		logger.WarnContext(ctx, "Redis connection failed, continuing without L2 cache", "err", err)
		return nil
	}
	logger.InfoContext(ctx, "Redis connected (L2 Cache enabled)", "addr", cfg.RedisURL)
	return rdb
}

func setupHub(ctx context.Context, cfg *config.Config, logger *slog.Logger, nc *nats.Conn, rdb *redis.Client, spiffeClients ...*spiffe.Client) *hub.Hub {
	var spiffeClient *spiffe.Client
	if len(spiffeClients) > 0 {
		spiffeClient = spiffeClients[0]
	}
	authClient := hub.NewInternalAPIAuthClient(cfg.BackendURL, rdb)
	if cfg.SpiffeEnabled {
		if spiffeClient == nil {
			logger.ErrorContext(ctx, "SPIFFE is enabled but spiffeClient is nil")
			os.Exit(1)
		}
		authClient.WithSPIFFE(spiffeClient, cfg.BackendSpiffeID)
	}
	authClient.StartEviction(ctx)
	// RZ-W14-01: pass rdb so the Hub can validate one-time WS upgrade tickets
	//nolint:contextcheck
	h := hub.NewHub(nc, logger, authClient, cfg, rdb)

	if cfg.JWKSURL != "" {
		if err := h.SetupJWKS(ctx, cfg.JWKSURL); err != nil {
			logger.ErrorContext(ctx, "Failed to setup JWKS", "err", err)
			os.Exit(1)
		}
	}

	h.StartLimiterCleanup(ctx)
	go h.Run(ctx)
	if nc != nil {
		h.SubscribeToNATS(ctx)
	}
	hub.SetAllowedOrigins(cfg.AllowedOrigins)
	return h
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
		if nc == nil || !nc.IsConnected() {
			checks["nats"] = "disconnected"
		}
		if rdb != nil {
			redisCacheMu.Lock()
			if time.Since(redisCacheUpdated) > redisCacheTTL {
				redisCacheErr = rdb.Ping(r.Context()).Err()
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
		if !h.HasJWKSCache() {
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

func runServer(cfg *config.Config, logger *slog.Logger, h *hub.Hub, mux *http.ServeMux) {
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

	var wtWg sync.WaitGroup
	wtWg.Add(1)
	go func() {
		defer wtWg.Done()
		logger.InfoContext(context.Background(), "Starting WebTransport Hub (UDP HTTP/3)", "port", wtPort)
		var err error
		if cfg.TLSCertFile != "" && cfg.TLSKeyFile != "" {
			err = wtServer.ListenAndServeTLS(cfg.TLSCertFile, cfg.TLSKeyFile)
		} else {
			logger.WarnContext(context.Background(), "WebTransport TLS cert files not configured; attempting ListenAndServe fallback")
			err = wtServer.ListenAndServe()
		}
		if err != nil && err != http.ErrServerClosed {
			logger.WarnContext(context.Background(), "WebTransport HTTP/3 listener stopped", "err", err)
		}
	}()

	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)

	select {
	case err := <-errChan:
		logger.ErrorContext(context.Background(), "Server error", "err", err)
	case <-quit:
	}

	logger.InfoContext(context.Background(), "Shutting down...")
	shutdownCtx, shutdownCancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer shutdownCancel()

	h.Stop()
	//nolint:errcheck
	_ = wtServer.Close()
	wtWg.Wait()
	if err := server.Shutdown(shutdownCtx); err != nil {
		logger.ErrorContext(context.Background(), "Server forced to shutdown", "err", err)
	}
}
