package main

import (
	"context"
	"crypto/tls"
	"encoding/json"
	"errors"
	"fmt"
	"log/slog"
	"net"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/golang-jwt/jwt/v5"
	"github.com/google/uuid"
	"github.com/graph-gophers/graphql-go"
	"github.com/graph-gophers/graphql-go/relay"
	"github.com/grpc-ecosystem/go-grpc-middleware/v2/interceptors/auth"
	grpc_prometheus "github.com/grpc-ecosystem/go-grpc-prometheus"
	"github.com/nats-io/nats.go"
	"github.com/prometheus/client_golang/prometheus/promhttp"
	enumspb "go.temporal.io/api/enums/v1"
	"go.temporal.io/sdk/client"
	"go.temporal.io/sdk/worker"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/credentials"
	"google.golang.org/grpc/health"
	"google.golang.org/grpc/health/grpc_health_v1"
	"google.golang.org/grpc/reflection"
	"google.golang.org/grpc/status"

	"github.com/getsentry/sentry-go"
	"go.opentelemetry.io/contrib/instrumentation/google.golang.org/grpc/otelgrpc"
	"go.opentelemetry.io/contrib/instrumentation/net/http/otelhttp"
	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracegrpc"
	"go.opentelemetry.io/otel/sdk/resource"
	sdktrace "go.opentelemetry.io/otel/sdk/trace"
	semconv "go.opentelemetry.io/otel/semconv/v1.27.0"

	pb "github.com/university-ecosystem/core/gen/go/file_processor/v1"
	"github.com/university-ecosystem/file-processor/internal/config"
	gql "github.com/university-ecosystem/file-processor/internal/graphql"
	"github.com/university-ecosystem/file-processor/internal/service"
	"github.com/university-ecosystem/file-processor/internal/workflow"
)

type contextKey string

const (
	userIDKey contextKey = "user_id"
)

func main() {
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()

	logger := initLogger()

	cfg, err := config.Load()
	if err != nil {
		logger.ErrorContext(ctx, "Failed to load configuration", "err", err)
		os.Exit(1)
	}

	initSentry(ctx, cfg, logger)

	tp, err := initTracer(ctx, cfg, logger)
	if err != nil {
		logger.ErrorContext(ctx, "OpenTelemetry initialization failed", "err", err)
	} else {
		defer func() {
			if shutErr := tp.Shutdown(ctx); shutErr != nil {
				logger.WarnContext(ctx, "Failed to shutdown tracer provider", "err", shutErr)
			}
		}()
	}

	c, err := connectTemporal(ctx, cfg, logger)
	if err != nil {
		logger.ErrorContext(ctx, "Failed to connect to Temporal", "err", err)
		os.Exit(1)
	}
	defer c.Close()

	w, _ := setupTemporalWorker(ctx, c, cfg, logger)
	if err := w.Start(); err != nil {
		logger.ErrorContext(ctx, "Unable to start Temporal worker", "err", err)
		os.Exit(1)
	}
	defer w.Stop()
	logger.InfoContext(ctx, "Temporal Worker started", "queue", "FILE_PROCESSING_TASK_QUEUE")

	startNatsSubscriber(ctx, cfg, c, logger)

	grpcSrv := setupGRPCServer(ctx, cfg, c, logger)
	graphqlSrv := setupGraphQLServer(ctx, cfg, c, logger)

	runServers(ctx, grpcSrv, graphqlSrv, cfg, logger)
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

func initSentry(ctx context.Context, cfg *config.Config, logger *slog.Logger) {
	if cfg.SentryDSN == "" {
		return
	}
	err := sentry.Init(sentry.ClientOptions{
		Dsn:              cfg.SentryDSN,
		Environment:      cfg.Environment,
		Release:          "file-processor@1.0.0",
		TracesSampleRate: 1.0,
	})
	if err != nil {
		logger.ErrorContext(ctx, "Sentry initialization failed", "err", err)
	} else {
		logger.InfoContext(ctx, "Sentry initialized", "environment", cfg.Environment)
	}
}

func connectTemporal(ctx context.Context, cfg *config.Config, logger *slog.Logger) (client.Client, error) {
	var c client.Client
	var err error
	maxAttempts := 10
	for attempt := 1; attempt <= maxAttempts; attempt++ {
		c, err = client.Dial(client.Options{
			HostPort: cfg.TemporalHost,
		})
		if err == nil {
			logger.InfoContext(ctx, "Connected to Temporal", "addr", cfg.TemporalHost)
			return c, nil
		}
		logger.WarnContext(ctx, "Failed to connect to Temporal, retrying...",
			"attempt", attempt,
			"addr", cfg.TemporalHost,
			"err", err,
		)
		select {
		case <-ctx.Done():
			return nil, ctx.Err()
		case <-time.After(time.Duration(attempt) * 2 * time.Second):
		}
	}
	return nil, fmt.Errorf("unable to create Temporal client after multiple attempts: %w", err)
}

func setupTemporalWorker(ctx context.Context, c client.Client, cfg *config.Config, logger *slog.Logger) (worker.Worker, *workflow.FileActivities) {
	w := worker.New(c, "FILE_PROCESSING_TASK_QUEUE", worker.Options{})
	w.RegisterWorkflow(workflow.FileProcessingWorkflow)

	minioClient, err := workflow.BuildMinIOClient(cfg)
	if err != nil {
		logger.ErrorContext(ctx, "Failed to initialize MinIO client", "err", err)
		os.Exit(1)
	}

	activities, err := workflow.NewFileActivities(cfg, minioClient)
	if err != nil {
		logger.ErrorContext(ctx, "Failed to initialize file activities", "err", err)
		os.Exit(1)
	}
	w.RegisterActivity(activities.ResizeImageActivity)

	return w, activities
}

func startNatsSubscriber(ctx context.Context, cfg *config.Config, c client.Client, logger *slog.Logger) {
	nc, err := nats.Connect(cfg.NatsURL, nats.RetryOnFailedConnect(true), nats.MaxReconnects(-1))
	if err != nil {
		logger.WarnContext(ctx, "Failed to connect to NATS (Legacy)", "err", err)
		return
	}

	js, err := nc.JetStream()
	if err != nil {
		logger.ErrorContext(ctx, "Failed to get JetStream context", "err", err)
		nc.Close()
		return
	}

	_, err = js.QueueSubscribe("files.process", "file-processors-temporal", func(msg *nats.Msg) {
		var job workflow.ProcessJob
		if err := json.Unmarshal(msg.Data, &job); err != nil {
			logger.ErrorContext(ctx, "Failed to unmarshal NATS message", "err", err)
			if nackErr := msg.Nak(); nackErr != nil {
				logger.ErrorContext(ctx, "Failed to nack NATS message", "err", nackErr)
			}
			return
		}

		opt := client.StartWorkflowOptions{
			ID:                       "proc-" + job.ID + ":" + uuid.NewString(),
			TaskQueue:                "FILE_PROCESSING_TASK_QUEUE",
			WorkflowExecutionTimeout: 30 * time.Minute,
			WorkflowIDReusePolicy:    enumspb.WORKFLOW_ID_REUSE_POLICY_REJECT_DUPLICATE,
		}

		wfCtx, wfCancel := context.WithTimeout(ctx, 5*time.Second)
		defer wfCancel()

		_, execErr := c.ExecuteWorkflow(wfCtx, opt, workflow.FileProcessingWorkflow, job)
		if execErr != nil {
			logger.ErrorContext(ctx, "Failed to execute workflow from NATS", "err", execErr)
			return
		}

		if ackErr := msg.Ack(); ackErr != nil {
			logger.ErrorContext(ctx, "Failed to ack NATS message", "err", ackErr)
		}
	}, nats.ManualAck())

	if err != nil {
		logger.ErrorContext(ctx, "Failed to subscribe to NATS queue", "err", err)
	}

	go func() {
		<-ctx.Done()
		nc.Close()
	}()
}

func setupGRPCServer(ctx context.Context, cfg *config.Config, c client.Client, logger *slog.Logger) *grpc.Server {
	grpcServer := grpc.NewServer(
		grpc.StatsHandler(otelgrpc.NewServerHandler()),
		grpc.ChainStreamInterceptor(
			grpc_prometheus.StreamServerInterceptor,
			auth.StreamServerInterceptor(authFunc(cfg.JWTSecret, logger)),
		),
		grpc.ChainUnaryInterceptor(
			grpc_prometheus.UnaryServerInterceptor,
			auth.UnaryServerInterceptor(authFunc(cfg.JWTSecret, logger)),
		),
	)

	pb.RegisterFileProcessingServiceServer(grpcServer, &service.Server{TemporalClient: c})
	reflection.Register(grpcServer)
	grpc_prometheus.Register(grpcServer)

	healthServer := health.NewServer()
	grpc_health_v1.RegisterHealthServer(grpcServer, healthServer)
	healthServer.SetServingStatus("", grpc_health_v1.HealthCheckResponse_SERVING)
	healthServer.SetServingStatus("file_processor.v1.FileProcessingService", grpc_health_v1.HealthCheckResponse_SERVING)

	return grpcServer
}

func setupGraphQLServer(ctx context.Context, cfg *config.Config, c client.Client, logger *slog.Logger) *http.Server {
	s, err := os.ReadFile("schema.graphql")
	if err != nil {
		logger.ErrorContext(ctx, "schema.graphql not found", "err", err)
		os.Exit(1)
	}

	resolver := &gql.Resolver{
		TemporalClient: c,
		MinioBucket:    cfg.MinioBucket,
	}

	var schemaOpts []graphql.SchemaOpt
	if cfg.Environment == "production" {
		schemaOpts = append(schemaOpts, graphql.RestrictIntrospection(func(ctx context.Context) bool {
			return false
		}))
	}

	schema := graphql.MustParseSchema(string(s), resolver, schemaOpts...)
	mux := http.NewServeMux()
	graphqlHandler := httpJWTMiddleware(cfg.JWTSecret, logger, &relay.Handler{Schema: schema})
	mux.Handle("/graphql", graphqlHandler)
	mux.Handle("/metrics", promhttp.Handler())

	return &http.Server{
		Addr:              ":" + cfg.GraphQLPort,
		Handler:           otelhttp.NewHandler(mux, "graphql_metrics"),
		ReadHeaderTimeout: 5 * time.Second,
	}
}

func runServers(ctx context.Context, grpcSrv *grpc.Server, graphqlSrv *http.Server, cfg *config.Config, logger *slog.Logger) {
	lc := net.ListenConfig{}
	lis, err := lc.Listen(ctx, "tcp", ":"+cfg.GRPCPort)
	if err != nil {
		logger.ErrorContext(ctx, "Failed to listen for gRPC", "err", err)
		os.Exit(1)
	}

	go func() {
		logger.InfoContext(ctx, "gRPC Server listening", "addr", ":"+cfg.GRPCPort)
		if err := grpcSrv.Serve(lis); err != nil && !errors.Is(err, grpc.ErrServerStopped) {
			logger.ErrorContext(ctx, "failed to serve gRPC", "err", err)
		}
	}()

	go func() {
		logger.InfoContext(ctx, "GraphQL & Metrics Server listening", "addr", ":"+cfg.GraphQLPort)
		if err := graphqlSrv.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
			logger.ErrorContext(ctx, "Failed to serve HTTP", "err", err)
		}
	}()

	<-ctx.Done()
	logger.InfoContext(ctx, "Shutting down servers...")

	grpcSrv.GracefulStop()

	shutdownCtx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	if err := graphqlSrv.Shutdown(shutdownCtx); err != nil {
		logger.ErrorContext(ctx, "HTTP Server forced to shutdown", "err", err)
	}
}

func httpJWTMiddleware(secret string, log *slog.Logger, next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		authHeader := r.Header.Get("Authorization")
		const prefix = "Bearer "
		if len(authHeader) <= len(prefix) || authHeader[:len(prefix)] != prefix {
			log.WarnContext(r.Context(), "GraphQL HTTP request missing or malformed Authorization header",
				"remote", r.RemoteAddr,
			)
			http.Error(w, "Unauthorized", http.StatusUnauthorized)
			return
		}
		tokenStr := authHeader[len(prefix):]

		token, err := jwt.Parse(tokenStr, func(t *jwt.Token) (interface{}, error) {
			if _, ok := t.Method.(*jwt.SigningMethodHMAC); !ok {
				return nil, status.Errorf(codes.Unauthenticated, "invalid token")
			}
			return []byte(secret), nil
		})
		if err != nil || !token.Valid {
			log.WarnContext(r.Context(), "GraphQL HTTP JWT validation failed",
				"remote", r.RemoteAddr,
				"err", err,
			)
			http.Error(w, "Unauthorized", http.StatusUnauthorized)
			return
		}

		claims, ok := token.Claims.(jwt.MapClaims)
		if !ok {
			http.Error(w, "Unauthorized", http.StatusUnauthorized)
			return
		}
		if sub, ok := claims["sub"].(string); ok {
			ctx := context.WithValue(r.Context(), userIDKey, sub)
			r = r.WithContext(ctx)
		}

		next.ServeHTTP(w, r)
	})
}

func authFunc(secret string, logger *slog.Logger) auth.AuthFunc {
	return func(ctx context.Context) (context.Context, error) {
		tokenStr, err := auth.AuthFromMD(ctx, "bearer")
		if err != nil {
			return nil, err
		}

		token, err := jwt.Parse(tokenStr, func(token *jwt.Token) (interface{}, error) {
			if _, ok := token.Method.(*jwt.SigningMethodHMAC); !ok {
				return nil, status.Errorf(codes.Unauthenticated, "invalid signing method")
			}
			return []byte(secret), nil
		})

		if err != nil {
			logger.WarnContext(ctx, "gRPC auth failed", "err", err)
			return nil, status.Errorf(codes.Unauthenticated, "invalid token: %v", err)
		}

		if claims, ok := token.Claims.(jwt.MapClaims); ok && token.Valid {
			if sub, ok := claims["sub"].(string); ok {
				newCtx := context.WithValue(ctx, userIDKey, sub)
				return newCtx, nil
			}
		}

		return nil, status.Errorf(codes.Unauthenticated, "invalid token claims")
	}
}

func initTracer(ctx context.Context, cfg *config.Config, logger *slog.Logger) (*sdktrace.TracerProvider, error) {
	endpoint := cfg.OTLPEndpoint
	if endpoint == "" {
		endpoint = "jaeger:4317"
	}

	var opts []otlptracegrpc.Option
	opts = append(opts, otlptracegrpc.WithEndpoint(endpoint))

	if cfg.OTLPInsecure {
		if cfg.Environment == "production" {
			return nil, errors.New("OTLP_INSECURE=true is forbidden in production")
		}
		logger.WarnContext(ctx, "OTLP running without TLS — development mode only")
		opts = append(opts, otlptracegrpc.WithInsecure())
	} else {
		opts = append(opts, otlptracegrpc.WithTLSCredentials(credentials.NewTLS(&tls.Config{
			MinVersion: tls.VersionTLS12,
		})))
	}

	exporter, err := otlptracegrpc.New(ctx, opts...)
	if err != nil {
		return nil, err
	}

	res, err := resource.New(ctx,
		resource.WithAttributes(
			semconv.ServiceNameKey.String("file-processor"),
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
