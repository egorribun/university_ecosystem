// Package main implements the API Gateway for University Ecosystem.
// It provides rate limiting, JWT validation, and reverse proxy to FastAPI.
package main

import (
	"log"
	"net/http"
	"net/http/httputil"
	"net/url"
	"time"

	"github.com/gin-contrib/cors"
	ginzap "github.com/gin-contrib/zap"
	"github.com/gin-gonic/gin"
	ginprometheus "github.com/zsais/go-gin-prometheus"
	"go.uber.org/zap"

	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"

	pb "github.com/university-ecosystem/core/gen/go/file_processor/v1"
	"github.com/university-ecosystem/gateway/internal/config"
	"github.com/university-ecosystem/gateway/internal/handlers"
	"github.com/university-ecosystem/gateway/middleware"
)

func main() {
	// Initialize logger
	logger, _ := zap.NewProduction()
	defer logger.Sync()

	// Load configuration (will exit if invalid)
	cfg := config.Load()

	// Parse backend URL
	backendURL, err := url.Parse(cfg.BackendURL)
	if err != nil {
		log.Fatalf("Invalid backend URL: %v", err)
	}

	// Create reverse proxy
	proxy := httputil.NewSingleHostReverseProxy(backendURL)
	proxy.ErrorHandler = func(w http.ResponseWriter, r *http.Request, err error) {
		logger.Error("Proxy error", zap.Error(err), zap.String("path", r.URL.Path))
		w.WriteHeader(http.StatusBadGateway)
	}

	// Connect to File Processor gRPC
	// In production, use proper credentials and connection pooling/balancing
	grpcConn, err := grpc.Dial(cfg.FileProcessorAddr,
		grpc.WithTransportCredentials(insecure.NewCredentials()),
		grpc.WithBlock(),
		grpc.WithTimeout(5*time.Second),
	)
	if err != nil {
		// Log but don't fail hard, maybe service is starting up
		logger.Warn("Failed to connect to File Processor gRPC", zap.Error(err))
	} else {
		defer grpcConn.Close()
		logger.Info("Connected to File Processor gRPC", zap.String("addr", cfg.FileProcessorAddr))
	}
	fileClient := pb.NewFileProcessingServiceClient(grpcConn)

	// Set Gin mode
	gin.SetMode(gin.ReleaseMode)

	// Create router
	router := gin.New()

	// Global middleware
	router.Use(ginzap.Ginzap(logger, time.RFC3339, true))
	router.Use(ginzap.RecoveryWithZap(logger, true))
	router.Use(cors.New(cors.Config{
		AllowOrigins:     []string{"*"},
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

	// Protected routes (JWT required)
	// We guaranteed JWTSecret is present in config.Load(), so we don't need the if check anymore
	// But sticking to the pattern of checking just in case config logic changes later
	if cfg.JWTSecret != "" {
		jwtMiddleware := middleware.NewJWTMiddleware(cfg.JWTSecret)
		protected := router.Group("/")
		protected.Use(jwtMiddleware.Validate())
		{
			// New gRPC Endpoint for Synchronous File Processing
			protected.POST("/api/v1/files/process/sync", handlers.FileProcessSyncHandler(grpcConn, fileClient, logger))

			protected.Any("/api/v1/*path", handlers.ProxyHandler(proxy))
			protected.Any("/api/admin/*path", handlers.ProxyHandler(proxy))
		}
		logger.Info("JWT validation enabled")
	} else {
		// No JWT validation - proxy everything
		router.Any("/api/*path", handlers.ProxyHandler(proxy))
		logger.Warn("JWT validation disabled - no secret configured")
	}

	// Start server
	addr := ":" + cfg.Port
	logger.Info("Starting API Gateway", zap.String("addr", addr), zap.String("backend", cfg.BackendURL))

	if err := router.Run(addr); err != nil {
		log.Fatalf("Failed to start server: %v", err)
	}
}
