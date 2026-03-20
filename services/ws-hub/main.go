package main

import (
	"context"
	"encoding/json"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"log/slog"

	"github.com/nats-io/nats.go"
	"github.com/prometheus/client_golang/prometheus/promhttp"
	"github.com/redis/go-redis/v9"
	"go.opentelemetry.io/contrib/instrumentation/net/http/otelhttp"

	"github.com/university-ecosystem/ws-hub/internal/telemetry"
	"github.com/university-ecosystem/ws-hub/pkg/config"
	"github.com/university-ecosystem/ws-hub/pkg/hub"
)

func main() {
	// MOD-01 (audit Wave 11): stdlib slog replaces go.uber.org/zap.
	// JSON handler with UTC timestamps matches the structured log format
	// expected by the Loki/Grafana log aggregation pipeline.
	handler := slog.NewJSONHandler(os.Stdout, &slog.HandlerOptions{
		Level: slog.LevelInfo,
		ReplaceAttr: func(_ []string, a slog.Attr) slog.Attr {
			if a.Key == slog.TimeKey {
				a.Value = slog.StringValue(a.Value.Time().UTC().Format(time.RFC3339Nano))
			}
			return a
		},
	})
	logger := slog.New(handler)

	cfg := config.LoadConfig()

	// AUDIT-INFRA-02: fail-fast — empty InternalSecret allows HMAC forgery on
	// the /internal/cache/invalidate endpoint from any container on service_net.
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
	if err != nil {
		logger.ErrorContext(ctx, "OpenTelemetry initialization failed", "err", err)
	} else {
		defer func() {
			if err := tp.Shutdown(ctx); err != nil {
				logger.ErrorContext(ctx, "Failed to shutdown tracer provider", "err", err)
			}
		}()
	}

	// MOD-W10-04: credentials from separate env vars, not embedded in the URL.
	// nats.go logs the URL on reconnect — having user:pass in it exposes secrets
	// in log aggregators and /proc/<pid>/environ on Linux.
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
	defer nc.Close()

	rdb := redis.NewClient(&redis.Options{
		Addr:     cfg.RedisURL,
		Password: cfg.RedisPassword,
		DB:       cfg.RedisDB,
	})
	// Check connection
	if err := rdb.Ping(ctx).Err(); err != nil {
		logger.WarnContext(ctx, "Redis connection failed, continuing without L2 cache", "err", err)
		rdb = nil
	} else {
		defer func() {
			if err := rdb.Close(); err != nil {
				logger.ErrorContext(context.Background(), "Failed to close Redis connection", "err", err)
			}
		}()
		logger.InfoContext(ctx, "Redis connected (L2 Cache enabled)", "addr", cfg.RedisURL)
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
			logger.ErrorContext(ctx, "Failed to setup JWKS", "err", err)
			os.Exit(1)
		}
	}

	// PERF-W9-06: Periodically evict orphaned rate.Limiter entries from
	// msgLimiters that were not cleaned up due to goroutine panics in ReadPump.
	h.StartLimiterCleanup(ctx)
	go h.Run(ctx)
	h.SubscribeToNATS(ctx) // WSH-P1-03: pass app context for graceful shutdown

	hub.SetAllowedOrigins(cfg.AllowedOrigins)

	http.Handle("/ws", otelhttp.NewHandler(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		h.HandleWebSocket(w, r, cfg)
	}), "websocket_upgrade"))

	http.Handle("/health", otelhttp.NewHandler(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if err := json.NewEncoder(w).Encode(map[string]interface{}{
			"status": "healthy",
		}); err != nil {
			logger.ErrorContext(r.Context(), "Failed to encode health check response", "err", err)
		}
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
		logger.InfoContext(context.Background(), "Starting WebSocket Hub", "port", cfg.Port)
		if err := server.ListenAndServe(); err != http.ErrServerClosed {
			logger.ErrorContext(context.Background(), "Server error", "err", err)
			os.Exit(1)
		}
	}()

	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)
	<-quit

	logger.InfoContext(context.Background(), "Shutting down...")
	shutdownCtx, shutdownCancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer shutdownCancel()

	// Drain NATS subscriptions before closing the HTTP server so that
	// in-flight messages are flushed to clients rather than dropped.
	h.Stop()

	if err := server.Shutdown(shutdownCtx); err != nil {
		logger.ErrorContext(context.Background(), "Server forced to shutdown", "err", err)
	}
}
