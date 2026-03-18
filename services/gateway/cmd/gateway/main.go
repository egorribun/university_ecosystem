package main

import (
	"bytes"
	"context"
	"crypto/tls"
	"encoding/json"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/http/httputil"
	"net/url"
	"os"
	"os/signal"
	"strings"
	"syscall"
	"time"

	"github.com/gin-contrib/cors"
	ginzap "github.com/gin-contrib/zap"
	"github.com/gin-gonic/gin"
	"github.com/prometheus/client_golang/prometheus"
	"github.com/redis/go-redis/extra/redisprometheus/v9"
	"github.com/redis/go-redis/v9"
	ginprometheus "github.com/zsais/go-gin-prometheus"
	"go.uber.org/zap"
	"go.uber.org/zap/zapcore"

	"github.com/getsentry/sentry-go"
	sentrygin "github.com/getsentry/sentry-go/gin"
	"go.opentelemetry.io/contrib/instrumentation/github.com/gin-gonic/gin/otelgin"
	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracegrpc"
	"go.opentelemetry.io/otel/sdk/resource"
	sdktrace "go.opentelemetry.io/otel/sdk/trace"
	// MOD-02 (audit Wave 10): semconv v1.27.0 for standardised OTel attributes.
	semconv "go.opentelemetry.io/otel/semconv/v1.27.0"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials"
	"google.golang.org/grpc/credentials/insecure"

	pb "github.com/university-ecosystem/core/gen/go/file_processor/v1"
	"github.com/university-ecosystem/gateway/internal/config"
	"github.com/university-ecosystem/gateway/internal/handlers"
	"github.com/university-ecosystem/gateway/middleware"
)

func main() {
	// Initialize standardized logger
	encoderConfig := zap.NewProductionEncoderConfig()
	encoderConfig.TimeKey = "timestamp"
	encoderConfig.EncodeTime = zapcore.ISO8601TimeEncoder
	encoderConfig.MessageKey = "message"

	zapConfig := zap.NewProductionConfig()
	zapConfig.EncoderConfig = encoderConfig

	logger, _ := zapConfig.Build(zap.Fields(zap.String("service", "gateway")))
	defer func() {
		_ = logger.Sync()
	}()

	// Load configuration
	cfg, err := config.Load()
	if err != nil {
		logger.Fatal("Failed to load configuration", zap.Error(err))
	}

	// Create a context for OpenTelemetry shutdown
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	// Initialize Sentry
	if cfg.SentryDSN != "" {
		err := sentry.Init(sentry.ClientOptions{
			Dsn:              cfg.SentryDSN,
			Environment:      cfg.Environment,
			Release:          cfg.AppVersion,
			TracesSampleRate: 1.0,
		})
		if err != nil {
			logger.Error("Sentry initialization failed", zap.Error(err))
		} else {
			logger.Info("Sentry initialized", zap.String("environment", cfg.Environment))
		}
	}

	// Initialize OpenTelemetry
	tp, err := initTracer(ctx, cfg)
	if err != nil {
		logger.Error("OpenTelemetry initialization failed", zap.Error(err))
	} else {
		defer func() { _ = tp.Shutdown(ctx) }()
		logger.Info("OpenTelemetry initialized")
	}

	// Parse backend URL
	backendURL, err := url.Parse(cfg.BackendURL)
	if err != nil {
		logger.Fatal("Invalid backend URL", zap.Error(err), zap.String("url", cfg.BackendURL))
	}

	// Create reverse proxy
	// PERF-02 (audit 2026-03-15 Wave 7): set explicit transport timeouts so
	// a slow or hung Python backend cannot accumulate gateway goroutines
	// indefinitely.  ResponseHeaderTimeout is the critical setting: it bounds
	// the wait for the first response byte after the request is sent.
	proxy := httputil.NewSingleHostReverseProxy(backendURL)
	proxy.Transport = &http.Transport{
		DialContext: (&net.Dialer{
			Timeout:   5 * time.Second,
			KeepAlive: 30 * time.Second,
		}).DialContext,
		ResponseHeaderTimeout: 30 * time.Second,
		IdleConnTimeout:       90 * time.Second,
		MaxIdleConns:          200,
		MaxIdleConnsPerHost:   50,
		TLSHandshakeTimeout:   10 * time.Second,
	}
	proxy.ErrorHandler = func(w http.ResponseWriter, r *http.Request, err error) {
		logger.Error("Proxy error", zap.Error(err), zap.String("path", r.URL.Path))
		w.WriteHeader(http.StatusBadGateway)
	}

	// Connect to File Processor gRPC (CRIT-02: Optional TLS via system CA pool)
	var grpcCreds grpc.DialOption
	if cfg.GrpcUseTLS {
		grpcCreds = grpc.WithTransportCredentials(credentials.NewClientTLSFromCert(nil, ""))
	} else {
		grpcCreds = grpc.WithTransportCredentials(insecure.NewCredentials())
	}

	grpcConn, err := grpc.NewClient(cfg.FileProcessorAddr, grpcCreds)
	if err != nil {
		logger.Fatal("Failed to initialize File Processor gRPC transport", zap.Error(err))
	}
	defer func() {
		_ = grpcConn.Close()
	}()
	logger.Info("Connected to File Processor gRPC", zap.String("addr", cfg.FileProcessorAddr))

	fileClient := pb.NewFileProcessingServiceClient(grpcConn)

	// Set Gin mode
	gin.SetMode(gin.ReleaseMode)

	// Create router
	router := gin.New()

	// FIX 1.4: Security Hardening: Explicitly trust only internal networks and local proxies.
	// Without this, Gin trusts 'X-Forwarded-For' from ANY source, allowing Rate Limit IP spoofing.
	_ = router.SetTrustedProxies([]string{"127.0.0.1", "::1", "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"})

	router.Use(gin.Recovery())
	router.Use(ginzap.Ginzap(logger, time.RFC3339, true))
	router.Use(ginzap.RecoveryWithZap(logger, true))

	// Add Observability Middlewares
	if cfg.SentryDSN != "" {
		router.Use(sentrygin.New(sentrygin.Options{Repanic: true}))
	}
	router.Use(otelgin.Middleware("gateway"))

	router.Use(cors.New(cors.Config{
		AllowOrigins:     cfg.AllowedOrigins,
		AllowMethods:     []string{"GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"},
		AllowHeaders:     []string{"Origin", "Content-Type", "Authorization", "X-Request-ID"},
		ExposeHeaders:    []string{"X-Request-ID", "X-RateLimit-Remaining"},
		AllowCredentials: true,
		// GW-P3-01 (audit Wave 10): 12h exceeds browser preflight cache limits
		// (Chrome caps at 7200s = 2h, Firefox at 86400s). Use 1h to match Chrome.
		MaxAge: 1 * time.Hour,
	}))

	// Initialize rate limiter
	rateLimiter, err := middleware.NewRateLimiter(cfg.RedisURL, cfg.RateLimitRPS, cfg.RateLimitBurst)
	if err != nil {
		logger.Warn("Rate limiter not available, continuing without", zap.Error(err))
	} else {
		router.Use(rateLimiter.Middleware())
		logger.Info("Rate limiter enabled", zap.Int("rps", cfg.RateLimitRPS))

		// Register Redis metrics collector
		collector := redisprometheus.NewCollector("gateway", "redis", rateLimiter.GetClient())
		if err := prometheus.Register(collector); err != nil {
			logger.Warn("Failed to register Redis metrics collector", zap.Error(err))
		} else {
			logger.Info("Redis metrics collector registered")
		}
	}

	// Initialize Prometheus
	// RZ-09 (audit 2026-03-15 Wave 7): expose /metrics on an internal-only port
	// so it is NOT reachable via the public API router.  K8s NetworkPolicy already
	// allows Prometheus scraper access to :9102 — see k8s/backend/network-policy.yaml.
	p := ginprometheus.NewPrometheus("gin")
	p.SetListenAddress(":9102")
	p.Use(router)

	// Public routes (initially empty group, will add middleware below)
	public := router.Group("/")
	{
		public.GET("/health", handlers.HealthHandler)
	}

	// Initialize JWT Middleware
	if len(strings.TrimSpace(cfg.JWTSecret)) < 32 {
		logger.Fatal("JWT_SECRET must be set and at least 32 characters. Gateway cannot start securely without it.")
	}

	var redisClient *redis.Client
	if rateLimiter != nil {
		redisClient = rateLimiter.GetClient()
	}

	// Wire RS256 public key if configured (MOD-1 / RZ-6).
	jwtMiddleware := middleware.NewJWTMiddlewareWithConfig(cfg.JWTSecret, cfg.JWKSPublicKeyPEM, redisClient, middleware.DefaultL1CacheConfig())
	jwtMiddleware.ListenForRevocations(ctx)

	// RZ-14-05: Convert the shared HMAC secret to []byte once for all proxy handlers.
	// When empty (dev/single-node mode), ProxyHandler skips signing and the backend
	// skips verification — X-Internal-Signature is not set.
	internalSecret := []byte(cfg.InternalHMACSecret)

	// --- API Grouping & JWT Architecture (CRIT-04) ---

	// 1. Core API (Always Validated)
	api := router.Group("/api")
	api.Use(jwtMiddleware.Validate())
	{
		// New gRPC Endpoint for Synchronous File Processing MUST be registered BEFORE the catch-all
		api.POST("/v1/files/process/sync", handlers.FileProcessSyncHandler(grpcConn, fileClient, logger))

		// Proxies to backend for all v1 and admin routes (Catch-all fallbacks)
		api.Any("/v1/*path", handlers.ProxyHandler(proxy, internalSecret))
		api.Any("/admin/*path", handlers.ProxyHandler(proxy, internalSecret))
	}

	// 2. Public API (Optional Auth - passes headers if logged in)
	optional := router.Group("/")
	optional.Use(jwtMiddleware.Optional())
	{
		optional.Any("/api/public/*path", handlers.ProxyHandler(proxy, internalSecret))
		optional.Any("/api/v1/auth/*path", handlers.ProxyHandler(proxy, internalSecret))
		optional.Any("/graphql", handlers.ProxyHandler(proxy, internalSecret))
	}

	// 3. Public API (No Auth or Optional)
	publicAPI := router.Group("/api/public")
	{
		publicAPI.Any("/*path", handlers.ProxyHandler(proxy, internalSecret))
	}

	// NoRoute fallback: return 404 for unmatched /api/ paths; proxy everything else (static assets, etc.)
	router.NoRoute(func(c *gin.Context) {
		if strings.HasPrefix(c.Request.URL.Path, "/api/") {
			c.JSON(http.StatusNotFound, gin.H{"error": "endpoint not found"})
			return
		}
		handlers.ProxyHandler(proxy, internalSecret)(c)
	})
	logger.Info("JWT validation enabled")

	// Start server with graceful shutdown
	addr := ":" + cfg.Port
	srv := &http.Server{
		Addr:              addr,
		Handler:           router,
		ReadHeaderTimeout: 5 * time.Second,
		ReadTimeout:       15 * time.Second,
		WriteTimeout:      30 * time.Second,
		IdleTimeout:       120 * time.Second,
		MaxHeaderBytes:    1 << 13,
	}

	go func() {
		logger.Info("Starting API Gateway", zap.String("addr", addr), zap.String("backend", cfg.BackendURL))
		if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			logger.Fatal("Failed to start server", zap.Error(err))
		}
	}()

	// Wait for interrupt signal
	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)
	<-quit

	logger.Info("Shutting down server...")

	shutdownCtx, shutdownCancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer shutdownCancel()

	if err := srv.Shutdown(shutdownCtx); err != nil {
		logger.Error("Server forced to shutdown", zap.Error(err))
	}

	logger.Info("Server exiting")
}

func initTracer(ctx context.Context, cfg *config.Config) (*sdktrace.TracerProvider, error) {
	// RZ-02 (audit 2026-03-15 Wave 7): reuse cfg.GrpcUseTLS (already used for
	// file-processor gRPC) so the same env variable (GRPC_USE_TLS=false) switches
	// both connections to insecure mode for local dev.  Production default is TLS
	// because config.go:52 makes GrpcUseTLS=true when GRPC_USE_TLS is absent.
	opts := []otlptracegrpc.Option{
		otlptracegrpc.WithEndpoint(cfg.OtelEndpoint),
	}
	if cfg.GrpcUseTLS {
		opts = append(opts, otlptracegrpc.WithTLSCredentials(
			credentials.NewTLS(&tls.Config{MinVersion: tls.VersionTLS12}),
		))
	} else {
		opts = append(opts, otlptracegrpc.WithInsecure())
	}
	exporter, err := otlptracegrpc.New(ctx, opts...)
	if err != nil {
		return nil, err
	}

	res, err := resource.New(ctx,
		resource.WithAttributes(
			semconv.ServiceNameKey.String("gateway"),
			attribute.String("environment", cfg.Environment),
		),
	)
	if err != nil {
		return nil, err
	}

	tp := sdktrace.NewTracerProvider(
		sdktrace.WithBatcher(exporter),
		sdktrace.WithResource(res),
	)
	otel.SetTracerProvider(tp)
	return tp, nil
}
