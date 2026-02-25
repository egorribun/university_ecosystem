package main

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
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
	semconv "go.opentelemetry.io/otel/semconv/v1.17.0"
	"google.golang.org/grpc"
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
			Release:          "gateway@1.0.0",
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
	proxy := httputil.NewSingleHostReverseProxy(backendURL)
	proxy.ErrorHandler = func(w http.ResponseWriter, r *http.Request, err error) {
		logger.Error("Proxy error", zap.Error(err), zap.String("path", r.URL.Path))
		w.WriteHeader(http.StatusBadGateway)
	}

	// BFF Logic: Intercept login/refresh to set cookies
	proxy.ModifyResponse = func(r *http.Response) error {
		if (r.Request.URL.Path == "/api/v1/auth/login" || r.Request.URL.Path == "/api/v1/auth/refresh") && r.StatusCode == http.StatusOK {
			// Read body
			body, err := io.ReadAll(r.Body)
			if err != nil {
				return err
			}
			_ = r.Body.Close()

			var data map[string]interface{}
			if err := json.Unmarshal(body, &data); err != nil {
				// Restore body and return if not JSON
				r.Body = io.NopCloser(bytes.NewBuffer(body))
				return nil
			}

			if token, ok := data["access_token"].(string); ok {
				// Set cookie — name must match middleware.AccessTokenCookieName so the
				// gateway's auth middleware can read it on subsequent requests.
				cookie := &http.Cookie{
					Name:     middleware.AccessTokenCookieName,
					Value:    token,
					Path:     "/",
					HttpOnly: true,
					Secure:   cfg.Environment != "development", // Use Secure in production
					SameSite: http.SameSiteStrictMode,
					MaxAge:   3600, // 1 hour (align with Python token TTL)
				}
				r.Header.Add("Set-Cookie", cookie.String())

				// Security Hardening: Strip access_token from JSON to protect against XSS
				// if the frontend is fully transitioned to cookies.
				delete(data, "access_token")
				newBody, _ := json.Marshal(data)
				r.Body = io.NopCloser(bytes.NewBuffer(newBody))
				r.ContentLength = int64(len(newBody))
				r.Header.Set("Content-Length", fmt.Sprint(len(newBody)))
			} else {
				// Restore body
				r.Body = io.NopCloser(bytes.NewBuffer(body))
			}
		}
		return nil
	}

	// Connect to File Processor gRPC
	grpcConn, err := grpc.NewClient(cfg.FileProcessorAddr,
		grpc.WithTransportCredentials(insecure.NewCredentials()),
	)
	if err != nil {
		logger.Warn("Failed to connect to File Processor gRPC", zap.Error(err))
	} else {
		defer func() {
			_ = grpcConn.Close()
		}()
		logger.Info("Connected to File Processor gRPC", zap.String("addr", cfg.FileProcessorAddr))
	}
	fileClient := pb.NewFileProcessingServiceClient(grpcConn)

	// Set Gin mode
	gin.SetMode(gin.ReleaseMode)

	// Create router
	router := gin.New()
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
		MaxAge:           12 * time.Hour,
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
	p := ginprometheus.NewPrometheus("gin")
	p.Use(router)

	// Health check (no auth required)
	router.GET("/health", handlers.HealthHandler)

	// Public routes (no auth)
	public := router.Group("/")
	{
		public.Any("/api/public/*path", handlers.ProxyHandler(proxy))
		public.Any("/api/v1/auth/*path", handlers.ProxyHandler(proxy))
		public.Any("/graphql", handlers.ProxyHandler(proxy))
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

	// Protected specific routes
	protected := router.Group("/")
	protected.Use(jwtMiddleware.Validate())
	{
		// New gRPC Endpoint for Synchronous File Processing - register BEFORE catch-all
		protected.POST("/api/v1/files/process/sync", handlers.FileProcessSyncHandler(grpcConn, fileClient, logger))
	}

	// Catch-all Proxy for remaining routes (BFF fallback)
	// We use NoRoute but we need it to still respect JWT for /api/v1/ and /api/admin/
	router.NoRoute(jwtMiddleware.Optional(), func(c *gin.Context) {
		path := c.Request.URL.Path
		if strings.HasPrefix(path, "/api/v1/") || strings.HasPrefix(path, "/api/admin/") {
			// Require full validation for these paths if they weren't matched by specific routes
			// (jwtMiddleware.Optional already set user info if valid, but here we can enforce it if needed)
			// For BFF simplicity, we re-run Validate() for these specific prefixes in NoRoute
			jwtMiddleware.Validate()(c)
			if c.IsAborted() {
				return
			}
		}
		handlers.ProxyHandler(proxy)(c)
	})
	logger.Info("JWT validation enabled")

	// Start server with graceful shutdown
	addr := ":" + cfg.Port
	srv := &http.Server{
		Addr:    addr,
		Handler: router,
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
	exporter, err := otlptracegrpc.New(ctx,
		otlptracegrpc.WithInsecure(),
		otlptracegrpc.WithEndpoint("jaeger:4317"), // Default OTEL endpoint
	)
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
