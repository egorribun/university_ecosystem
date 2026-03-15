package main

import (
	"context"
	"encoding/json"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/nats-io/nats.go"
	"github.com/prometheus/client_golang/prometheus/promhttp"
	"github.com/redis/go-redis/v9"
	"go.opentelemetry.io/contrib/instrumentation/net/http/otelhttp"
	"go.uber.org/zap"

	"github.com/university-ecosystem/ws-hub/internal/telemetry"
	"github.com/university-ecosystem/ws-hub/pkg/config"
	"github.com/university-ecosystem/ws-hub/pkg/hub"
)

func main() {
	// MOD-02 (audit 2026-03-08 Wave 5): Enable log sampling to cap throughput.
	// At 10,000 concurrent connections each ReadPump can emit DEBUG logs;
	// without sampling this can reach ~100K log events/sec and overwhelm log
	// aggregators. Sampling: first 100 events/s at each level pass through,
	// then every 100th thereafter.
	zapCfg := zap.NewProductionConfig()
	zapCfg.Sampling = &zap.SamplingConfig{
		Initial:    100,
		Thereafter: 100,
	}
	logger, err := zapCfg.Build()
	if err != nil {
		panic(err)
	}
	defer func() { _ = logger.Sync() }()

	cfg := config.LoadConfig()

	// AUDIT-INFRA-02: fail-fast — empty InternalSecret allows HMAC forgery on
	// the /internal/cache/invalidate endpoint from any container on service_net.
	if cfg.InternalSecret == "" {
		logger.Fatal("WS_HUB_INTERNAL_SECRET is not set — generate with: openssl rand -hex 32")
	}

	if err := telemetry.InitSentry(cfg); err != nil {
		logger.Error("Sentry initialization failed", zap.Error(err))
	}

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	tp, err := telemetry.InitTracer(ctx, cfg)
	if err != nil {
		logger.Error("OpenTelemetry initialization failed", zap.Error(err))
	} else {
		defer func() { _ = tp.Shutdown(ctx) }()
	}

	nc, err := nats.Connect(cfg.NatsURL,
		nats.RetryOnFailedConnect(true),
		nats.MaxReconnects(-1),
		nats.ReconnectWait(2*time.Second),
	)
	if err != nil {
		logger.Fatal("Failed to connect to NATS", zap.Error(err))
	}
	defer nc.Close()

	rdb := redis.NewClient(&redis.Options{
		Addr:     cfg.RedisURL,
		Password: cfg.RedisPassword,
		DB:       cfg.RedisDB,
	})
	// Check connection
	if err := rdb.Ping(ctx).Err(); err != nil {
		logger.Warn("Redis connection failed, continuing without L2 cache", zap.Error(err))
		rdb = nil
	} else {
		defer func() {
			if err := rdb.Close(); err != nil {
				logger.Error("Failed to close Redis connection", zap.Error(err))
			}
		}()
		logger.Info("Redis connected (L2 Cache enabled)", zap.String("addr", cfg.RedisURL))
	}

	authClient := hub.NewInternalAPIAuthClient(cfg.BackendURL, rdb)
	// WSH-07 (audit 2026-03-08 Wave 5): Start background eviction goroutine for
	// the auth cache. Without eviction the cache map grows unboundedly when users
	// visit many unique (user, room) pairs. The goroutine exits when ctx is done.
	authClient.StartEviction(ctx)
	h := hub.NewHub(nc, logger, authClient, cfg)

	// MOD-1: initialize JWKS cache for RS256 support.
	if cfg.JWKSURL != "" {
		if err := h.SetupJWKS(ctx, cfg.JWKSURL); err != nil {
			logger.Fatal("Failed to setup JWKS", zap.Error(err))
		}
	}

	go h.Run(ctx)
	h.SubscribeToNATS()

	hub.SetAllowedOrigins(cfg.AllowedOrigins)

	http.Handle("/ws", otelhttp.NewHandler(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		h.HandleWebSocket(w, r, cfg)
	}), "websocket_upgrade"))

	http.Handle("/health", otelhttp.NewHandler(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_ = json.NewEncoder(w).Encode(map[string]interface{}{
			"status": "healthy",
		})
	}), "health_check"))

	// INF-02 (audit 2026-03-08 Wave 5): Prometheus metrics endpoint.
	// Exposed on the same port — access is gated by the internal Docker
	// network only (not exposed to the public internet via ingress).
	http.Handle("/metrics", promhttp.Handler())

	server := &http.Server{
		Addr:         ":" + cfg.Port,
		ReadTimeout:  10 * time.Second,
		WriteTimeout: 10 * time.Second,
		// IdleTimeout limits how long a keep-alive connection may sit idle.
		// Without this, Slowloris-style attackers can exhaust file descriptors
		// by holding many connections open indefinitely. (RZ-4: audit 2026-02-24)
		IdleTimeout: 120 * time.Second,
		// ReadHeaderTimeout prevents Slowloris on the HTTP header phase.
		// After the WebSocket upgrade, gorilla/websocket manages its own deadlines.
		ReadHeaderTimeout: 5 * time.Second,
		// 8 KiB is ample for WebSocket upgrade headers; caps header-flood attacks.
		MaxHeaderBytes: 1 << 13,
	}

	go func() {
		logger.Info("Starting WebSocket Hub", zap.String("port", cfg.Port))
		if err := server.ListenAndServe(); err != http.ErrServerClosed {
			logger.Fatal("Server error", zap.Error(err))
		}
	}()

	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)
	<-quit

	logger.Info("Shutting down...")
	shutdownCtx, shutdownCancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer shutdownCancel()

	// Drain NATS subscriptions before closing the HTTP server so that
	// in-flight messages are flushed to clients rather than dropped.
	h.Stop()

	_ = server.Shutdown(shutdownCtx)
}
