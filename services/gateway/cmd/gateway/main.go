package main

import (
	"context"
	"crypto/tls"
	"errors"
	"fmt"
	"net"
	"net/http"
	"net/http/httputil"
	"net/url"
	"os"
	"os/signal"
	"strings"
	"syscall"
	"time"

	"log/slog"

	"github.com/gin-contrib/cors"
	"github.com/gin-gonic/gin"
	"github.com/prometheus/client_golang/prometheus"
	"github.com/redis/go-redis/extra/redisprometheus/v9"
	"github.com/redis/go-redis/v9"
	ginprometheus "github.com/zsais/go-gin-prometheus"

	"github.com/getsentry/sentry-go"
	sentrygin "github.com/getsentry/sentry-go/gin"
	"go.opentelemetry.io/contrib/instrumentation/github.com/gin-gonic/gin/otelgin"
	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracegrpc"
	"go.opentelemetry.io/otel/propagation"
	"go.opentelemetry.io/otel/sdk/resource"
	sdktrace "go.opentelemetry.io/otel/sdk/trace"

	// MOD-02 (audit Wave 10): semconv v1.27.0 for standardised OTel attributes.
	semconv "go.opentelemetry.io/otel/semconv/v1.27.0"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials"
	"google.golang.org/grpc/credentials/insecure"

	"github.com/quic-go/quic-go/http3"
	pb "github.com/university-ecosystem/core/gen/go/file_processor/v1"
	"github.com/university-ecosystem/gateway/internal/config"
	"github.com/university-ecosystem/gateway/internal/handlers"
	"github.com/university-ecosystem/gateway/internal/tlsutil"
	"github.com/university-ecosystem/gateway/middleware"
	"github.com/university-ecosystem/services/pkg/spiffe"
)

var (
	initTracerFunc               = initTracer
	initGRPCFunc                 = initGRPC
	newGRPCClientFunc            = grpc.NewClient
	newSpiffeClientFunc          = spiffe.NewClient
	newSpiffeGRPCCredentialsFunc = func(client *spiffe.Client, expectedServerID string) (credentials.TransportCredentials, error) {
		return client.GRPCClientCredentials(expectedServerID)
	}
	newSpiffeClientTLSConfigFunc = func(client *spiffe.Client, expectedServerID string) (*tls.Config, error) {
		return client.ClientTLSConfig(expectedServerID)
	}
	closeSpiffeClientFunc           = func(client *spiffe.Client) error { return client.Close() }
	closeGRPCConnFunc               = func(conn *grpc.ClientConn) error { return conn.Close() }
	setupRouterFunc                 = setupRouter
	setTrustedProxiesFunc           = func(router *gin.Engine, proxies []string) error { return router.SetTrustedProxies(proxies) }
	registerPrometheusCollectorFunc = func(collector prometheus.Collector) error {
		return prometheus.Register(collector)
	}
	optionalAuthHandlerFunc = func(jwtMiddleware *middleware.JWTMiddleware, ctx context.Context) gin.HandlerFunc {
		return jwtMiddleware.Optional(ctx)
	}
	newOTLPTraceExporterFunc = func(ctx context.Context, opts ...otlptracegrpc.Option) (sdktrace.SpanExporter, error) {
		return otlptracegrpc.New(ctx, opts...)
	}
	newOTelResourceFunc = func(ctx context.Context, opts ...resource.Option) (*resource.Resource, error) {
		return resource.New(ctx, opts...)
	}
	shutdownH3ServerFunc   = func(server *http3.Server, ctx context.Context) error { return server.Shutdown(ctx) }
	shutdownHTTPServerFunc = func(server *http.Server, ctx context.Context) error { return server.Shutdown(ctx) }
)

func main() {
	if err := run(); err != nil {
		os.Exit(1)
	}
}

func run() error {
	// 1. Initialize Logger
	// TD-W17-02 (Wave 17): Migrated from uber-go/zap to log/slog, matching
	// ws-hub and file-processor. Eliminates the EINVAL-on-Sync workaround
	// and unifies structured logging across all three Go services.
	logger := initLogger()
	slog.SetDefault(logger)

	// 2. Load Configuration
	cfg, err := config.Load()
	if err != nil {
		logger.ErrorContext(context.Background(), "Failed to load configuration", "err", err)
		return err
	}

	// 3. Initialize Sentry
	initSentry(cfg, logger)

	// 4. Initialize OpenTelemetry
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	tp, err := initTracerFunc(ctx, cfg)
	if err != nil {
		logger.ErrorContext(ctx, "OpenTelemetry initialization failed", "err", err)
	} else {
		defer func() {
			if err := tp.Shutdown(ctx); err != nil {
				logger.ErrorContext(ctx, "Failed to shutdown tracer provider", "err", err)
			}
		}()
		logger.InfoContext(ctx, "OpenTelemetry initialized")
	}

	// 4.5 Initialize SPIFFE Workload API Client
	spiffeClient, err := newSpiffeClientFunc(ctx, spiffe.Config{
		Enabled:     cfg.SpiffeEnabled,
		SocketPath:  cfg.SpiffeEndpointSocket,
		TrustDomain: cfg.SpiffeTrustDomain,
		MySpiffeID:  cfg.SpiffeMyID,
	}, logger)
	if err != nil {
		logger.ErrorContext(ctx, "SPIFFE initialization failed", "err", err)
		if cfg.SpiffeEnabled {
			return err
		}
	} else if cfg.SpiffeEnabled && spiffeClient == nil {
		logger.ErrorContext(ctx, "SPIFFE is enabled but client initialization returned nil")
		return errors.New("SPIFFE is enabled but client initialization returned nil")
	} else if spiffeClient != nil {
		defer func() {
			if err := closeSpiffeClientFunc(spiffeClient); err != nil {
				logger.WarnContext(ctx, "Failed to close SPIFFE client", "err", err)
			}
		}()
	}

	// 5. Initialize gRPC connection to File Processor
	grpcConn, fileClient, err := initGRPCFunc(cfg, logger, spiffeClient)
	if err != nil {
		logger.ErrorContext(ctx, "gRPC initialization failed", "err", err)
		return err
	}
	defer func() {
		if err := closeGRPCConnFunc(grpcConn); err != nil {
			logger.ErrorContext(ctx, "Failed to close gRPC connection", "err", err)
		}
	}()

	// 6. Setup Router & Middleware
	router, err := setupRouterFunc(cfg, logger, grpcConn, fileClient, spiffeClient, ctx)
	if err != nil {
		logger.ErrorContext(ctx, "Router setup failed", "err", err)
		return err
	}

	// 7. Start Server
	return runServer(cfg, router, logger)
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
	return slog.New(handler).With("service", "gateway")
}

func initSentry(cfg *config.Config, logger *slog.Logger) {
	if cfg.SentryDSN == "" {
		return
	}
	err := sentry.Init(sentry.ClientOptions{
		Dsn:         cfg.SentryDSN,
		Environment: cfg.Environment,
		Release:     cfg.AppVersion,
		// RZ-33-02: Configurable via SENTRY_TRACES_SAMPLE_RATE env var.
		// Default 1.0 (100%) for dev; recommend 0.1 (10%) for production.
		TracesSampleRate: cfg.SentryTracesSampleRate,
	})
	if err != nil {
		logger.ErrorContext(context.Background(), "Sentry initialization failed", "err", err)
		return
	}
	logger.InfoContext(context.Background(), "Sentry initialized", "environment", cfg.Environment)
}

func initGRPC(cfg *config.Config, logger *slog.Logger, spiffeClients ...*spiffe.Client) (*grpc.ClientConn, pb.FileProcessingServiceClient, error) {
	var spiffeClient *spiffe.Client
	if len(spiffeClients) > 0 {
		spiffeClient = spiffeClients[0]
	}
	var grpcCreds grpc.DialOption
	if cfg.SpiffeEnabled {
		if spiffeClient == nil {
			logger.ErrorContext(context.Background(), "SPIFFE is enabled but spiffeClient is nil")
			return nil, nil, http.ErrServerClosed
		}
		creds, err := newSpiffeGRPCCredentialsFunc(spiffeClient, cfg.FileProcessorSpiffeID)
		if err != nil {
			logger.ErrorContext(context.Background(), "Failed to create SPIFFE gRPC credentials", "err", err)
			return nil, nil, err
		}
		grpcCreds = grpc.WithTransportCredentials(creds)
	} else if cfg.GrpcUseTLS {
		grpcCreds = grpc.WithTransportCredentials(credentials.NewClientTLSFromCert(nil, ""))
	} else {
		grpcCreds = grpc.WithTransportCredentials(insecure.NewCredentials())
	}

	// RZ-31-05: Set a default 30s per-RPC timeout via service config.  grpc.NewClient
	// is lazy (no blocking dial), but RPCs without a deadline can hang indefinitely if
	// file-processor is unresponsive.  30s matches the gateway ResponseHeaderTimeout.
	grpcConn, err := newGRPCClientFunc(cfg.FileProcessorAddr, grpcCreds,
		grpc.WithDefaultServiceConfig(`{"methodConfig":[{"name":[{}],"timeout":"30s"}]}`),
	)
	if err != nil {
		logger.ErrorContext(context.Background(), "Failed to initialize File Processor gRPC transport", "err", err)
		return nil, nil, err
	}
	logger.InfoContext(context.Background(), "Connected to File Processor gRPC", "addr", cfg.FileProcessorAddr)

	return grpcConn, pb.NewFileProcessingServiceClient(grpcConn), nil
}

//nolint:gocognit,cyclop
func setupRouter(cfg *config.Config, logger *slog.Logger, grpcConn *grpc.ClientConn, fileClient pb.FileProcessingServiceClient, opts ...any) (*gin.Engine, error) {
	ctx := context.Background()
	var spiffeClient *spiffe.Client

	for _, opt := range opts {
		switch v := opt.(type) {
		case context.Context:
			ctx = v
		case *spiffe.Client:
			spiffeClient = v
		}
	}

	gin.SetMode(gin.ReleaseMode)
	router := gin.New()

	// FIX 1.4: Security Hardening: Explicitly trust only internal networks and local proxies.
	if err := setTrustedProxiesFunc(router, []string{"127.0.0.1", "::1", "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"}); err != nil {
		logger.ErrorContext(ctx, "Failed to set trusted proxies", "err", err)
		return nil, fmt.Errorf("configure trusted proxies: %w", err)
	}

	// TD-W17-02: Replace ginzap with gin.Recovery + otelgin.
	// gin.Recovery provides panic recovery; otelgin provides trace-correlated
	// request logging via OpenTelemetry. This eliminates the uber-go/zap dependency.
	router.Use(gin.Recovery())

	if cfg.SentryDSN != "" {
		router.Use(sentrygin.New(sentrygin.Options{Repanic: true}))
	}
	router.Use(otelgin.Middleware("gateway"))

	if cfg.H3Enabled {
		router.Use(middleware.AltSvcMiddleware(cfg.H3Port, cfg.H3AltSvcMaxAge))
	}

	router.Use(cors.New(cors.Config{
		AllowOrigins:     cfg.AllowedOrigins,
		AllowMethods:     []string{"GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"},
		AllowHeaders:     []string{"Origin", "Content-Type", "Authorization", "X-Request-ID"},
		ExposeHeaders:    []string{"X-Request-ID", "X-RateLimit-Remaining"},
		AllowCredentials: true,
		MaxAge:           1 * time.Hour,
	}))

	// Proxy configuration
	backendURL, err := url.Parse(cfg.BackendURL)
	if err != nil {
		logger.ErrorContext(ctx, "Invalid backend URL", "err", err, "url", cfg.BackendURL)
		return nil, err
	}
	proxy := httputil.NewSingleHostReverseProxy(backendURL)
	proxyTransport := &http.Transport{
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
	if cfg.SpiffeEnabled {
		if spiffeClient == nil {
			logger.ErrorContext(ctx, "SPIFFE is enabled but spiffeClient is nil")
			return nil, http.ErrServerClosed
		}
		tlsCfg, err := newSpiffeClientTLSConfigFunc(spiffeClient, cfg.BackendSpiffeID)
		if err != nil {
			logger.ErrorContext(ctx, "Failed to build SPIFFE client TLS config for backend proxy", "err", err)
			return nil, err
		}
		proxyTransport.TLSClientConfig = tlsCfg
	}
	proxy.Transport = proxyTransport
	proxy.ErrorHandler = func(w http.ResponseWriter, r *http.Request, err error) {
		logger.ErrorContext(ctx, "Proxy error", "err", err, "path", r.URL.Path)
		w.WriteHeader(http.StatusBadGateway)
	}

	// Rate Limiter
	rateLimiter, err := middleware.NewRateLimiter(ctx, cfg.RedisURL, cfg.RateLimitRPS, cfg.RateLimitBurst)
	var redisClient *redis.Client
	if err != nil {
		logger.WarnContext(ctx, "Rate limiter not available, continuing without", "err", err)
	} else {
		router.Use(rateLimiter.Middleware(ctx))
		redisClient = rateLimiter.GetClient()
		collector := redisprometheus.NewCollector("gateway", "redis", redisClient)
		if err := registerPrometheusCollectorFunc(collector); err != nil {
			logger.WarnContext(ctx, "Failed to register Redis metrics collector", "err", err)
		}
	}

	// Prometheus
	p := ginprometheus.NewPrometheus("gin")
	p.SetListenAddress(":9102")
	p.Use(router)

	// Admin/Metrics separation
	public := router.Group("/")
	public.GET("/health", handlers.HealthHandler)

	// JWT
	if len(strings.TrimSpace(cfg.JWTSecret)) < 32 {
		logger.ErrorContext(ctx, "JWT_SECRET must be set and at least 32 characters.")
		return nil, http.ErrServerClosed
	}
	jwtMiddleware := middleware.NewJWTMiddlewareWithConfig(cfg.JWTSecret, cfg.JWKSPublicKeyPEM, redisClient, middleware.DefaultL1CacheConfig())
	// PERF-W17-02: Pre-populate L1 cache from Redis to avoid cold-start thundering herd.
	jwtMiddleware.WarmL1Cache(ctx)
	jwtMiddleware.ListenForRevocations(ctx)
	// MOD-W17-03: Start JWKS hot-reload if endpoint is configured.
	if cfg.JWKSEndpoint != "" {
		interval := time.Duration(cfg.JWKSRefreshInterval) * time.Second
		jwtMiddleware.StartJWKSRefresher(ctx, cfg.JWKSEndpoint, interval, logger)
		logger.InfoContext(ctx, "JWKS hot-reload enabled", "endpoint", cfg.JWKSEndpoint, "interval", interval)
	}

	internalSecret := []byte(cfg.InternalHMACSecret)

	// ws-hub Reverse Proxy configuration (handles /ws, /ws/*, /webtransport)
	wsHubURL, err := url.Parse(cfg.WsHubURL)
	if err != nil {
		logger.ErrorContext(ctx, "Invalid ws-hub URL", "err", err, "url", cfg.WsHubURL)
		return nil, err
	}
	wsProxy := httputil.NewSingleHostReverseProxy(wsHubURL)
	wsProxy.Transport = proxyTransport
	wsProxy.ErrorHandler = func(w http.ResponseWriter, r *http.Request, err error) {
		logger.ErrorContext(ctx, "WS Hub Proxy error", "err", err, "path", r.URL.Path)
		w.WriteHeader(http.StatusBadGateway)
	}
	wsProxyFn := handlers.ProxyHandler(wsProxy, internalSecret)

	// Register WebSocket and WebTransport reverse proxy routes
	router.Any("/ws", wsProxyFn)
	router.Any("/ws/*path", wsProxyFn)
	router.Any("/webtransport", wsProxyFn)

	// All API routes under a single wildcard to avoid gin tree conflicts.
	// Auth logic is handled inside the handler based on path prefix.
	proxyFn := handlers.ProxyHandler(proxy, internalSecret)
	fileFn := handlers.ProxyOrFileHandler(proxy, internalSecret, ctx, grpcConn, fileClient, logger)
	api := router.Group("/api")
	{
		api.Any("/v1/*path", func(c *gin.Context) {
			subPath := c.Param("path")
			if strings.HasPrefix(subPath, "/auth/") {
				// Auth routes: optional JWT
				jwtMiddleware.Optional(ctx)(c)
			} else {
				// All other v1 routes: require JWT
				jwtMiddleware.Validate(ctx)(c)
			}
			if c.IsAborted() {
				return
			}
			fileFn(c)
		})
		api.Any("/admin/*path", func(c *gin.Context) {
			jwtMiddleware.Validate(ctx)(c)
			if c.IsAborted() {
				return
			}
			proxyFn(c)
		})
		api.Any("/public/*path", func(c *gin.Context) {
			optionalAuthHandlerFunc(jwtMiddleware, ctx)(c)
			if c.IsAborted() {
				return
			}
			proxyFn(c)
		})
	}

	// GraphQL (optional JWT)
	router.Any("/graphql", func(c *gin.Context) {
		optionalAuthHandlerFunc(jwtMiddleware, ctx)(c)
		if c.IsAborted() {
			return
		}
		proxyFn(c)
	})

	router.NoRoute(func(c *gin.Context) {
		if strings.HasPrefix(c.Request.URL.Path, "/api/") {
			c.JSON(http.StatusNotFound, gin.H{"error": "endpoint not found"})
			return
		}
		handlers.ProxyHandler(proxy, internalSecret)(c)
	})

	return router, nil
}

func runServer(cfg *config.Config, router *gin.Engine, logger *slog.Logger, signalChannels ...chan os.Signal) error {
	addr := ":" + cfg.Port
	srv := &http.Server{
		Addr:              addr,
		Handler:           router,
		ReadHeaderTimeout: 5 * time.Second,
		ReadTimeout:       15 * time.Second,
		// FIX-WS-01: WriteTimeout must be 0 (disabled) because this gateway proxies
		// long-lived WebSocket connections. A non-zero WriteTimeout causes net/http to
		// close the underlying TCP connection once the deadline fires, immediately
		// terminating all active WebSocket upgrades. The proxy's own
		// ResponseHeaderTimeout (30s) already guards against slow upstream headers on
		// plain HTTP requests; WebSocket frames are handled at the application layer.
		WriteTimeout:   0,
		IdleTimeout:    120 * time.Second,
		MaxHeaderBytes: 1 << 13,
	}

	// HTTP/3 QUIC Listener (UDP 8443)
	var h3Server *http3.Server
	if cfg.H3Enabled {
		tlsConfig, err := prepareTLSConfig(cfg, logger)
		if err != nil {
			logger.ErrorContext(context.Background(), "Failed to prepare TLS config for HTTP/3 listener", "err", err)
		} else {
			h3Addr := ":" + cfg.H3Port
			h3Server = &http3.Server{
				Addr:            h3Addr,
				Handler:         router,
				TLSConfig:       http3.ConfigureTLSConfig(tlsConfig),
				EnableDatagrams: true,
			}
			go func() {
				logger.InfoContext(context.Background(), "Starting HTTP/3 QUIC listener", "addr", h3Addr)
				if err := h3Server.ListenAndServe(); err != nil && err != http.ErrServerClosed {
					logger.ErrorContext(context.Background(), "HTTP/3 QUIC listener error", "err", err)
				}
			}()
		}
	}

	// RZ-31-01: Replace os.Exit(1) with channel-based error propagation so that
	// all defers in main() execute (OTEL flush, gRPC close, Sentry drain).
	// os.Exit bypasses defers in ALL goroutines — traces and error reports are lost.
	serverErr := make(chan error, 1)
	go func() {
		logger.InfoContext(context.Background(), "Starting API Gateway", "addr", addr, "backend", cfg.BackendURL)
		if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			logger.ErrorContext(context.Background(), "Failed to start server", "err", err)
			serverErr <- err
		}
	}()

	quit := make(chan os.Signal, 1)
	if len(signalChannels) > 0 && signalChannels[0] != nil {
		quit = signalChannels[0]
	} else {
		signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)
		defer signal.Stop(quit)
	}
	var runErr error
	select {
	case <-quit:
	case err := <-serverErr:
		logger.ErrorContext(context.Background(), "Server startup failed, initiating orderly shutdown", "err", err)
		runErr = err
	}

	logger.InfoContext(context.Background(), "Shutting down server...")

	shutdownCtx, shutdownCancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer shutdownCancel()

	if h3Server != nil {
		if err := shutdownH3ServerFunc(h3Server, shutdownCtx); err != nil {
			logger.ErrorContext(context.Background(), "HTTP/3 server forced to shutdown", "err", err)
		}
	}

	if err := shutdownHTTPServerFunc(srv, shutdownCtx); err != nil {
		logger.ErrorContext(context.Background(), "Server forced to shutdown", "err", err)
	}

	logger.InfoContext(context.Background(), "Server exiting")
	return runErr
}

func prepareTLSConfig(cfg *config.Config, logger *slog.Logger) (*tls.Config, error) {
	if cfg.TLSCertFile != "" && cfg.TLSKeyFile != "" {
		cert, err := tls.LoadX509KeyPair(cfg.TLSCertFile, cfg.TLSKeyFile)
		if err != nil {
			return nil, err
		}
		return &tls.Config{
			Certificates: []tls.Certificate{cert},
			MinVersion:   tls.VersionTLS13,
		}, nil
	}
	logger.InfoContext(context.Background(), "No TLS cert files provided; generating in-memory self-signed TLS 1.3 certificate for HTTP/3 listener")
	return tlsutil.GenerateSelfSignedTLSCert()
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
	exporter, err := newOTLPTraceExporterFunc(ctx, opts...)
	if err != nil {
		return nil, err
	}

	res, err := newOTelResourceFunc(ctx,
		resource.WithAttributes(
			semconv.ServiceNameKey.String("gateway"),
			attribute.String("environment", cfg.Environment),
		),
	)
	if err != nil {
		return nil, errors.Join(err, exporter.Shutdown(ctx))
	}

	tp := sdktrace.NewTracerProvider(
		sdktrace.WithBatcher(exporter),
		sdktrace.WithResource(res),
	)
	otel.SetTracerProvider(tp)
	// MOD-31-02: Register composite propagator so W3C Baggage headers (user_id,
	// request_id) propagate alongside TraceContext across service boundaries.
	otel.SetTextMapPropagator(
		propagation.NewCompositeTextMapPropagator(
			propagation.TraceContext{},
			propagation.Baggage{},
		),
	)
	return tp, nil
}
