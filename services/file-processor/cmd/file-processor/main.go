package main

import (
	"context"
	"crypto/tls"
	"encoding/json"
	"net"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/golang-jwt/jwt/v5"
	"github.com/graph-gophers/graphql-go"
	"github.com/graph-gophers/graphql-go/relay"
	"github.com/grpc-ecosystem/go-grpc-middleware/v2/interceptors/auth"
	grpc_prometheus "github.com/grpc-ecosystem/go-grpc-prometheus"
	"github.com/nats-io/nats.go"
	"github.com/prometheus/client_golang/prometheus/promhttp"
	"go.temporal.io/sdk/client"
	"go.temporal.io/sdk/worker"
	"go.uber.org/zap"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/credentials"
	"google.golang.org/grpc/health"
	"google.golang.org/grpc/health/grpc_health_v1"
	"google.golang.org/grpc/reflection"
	"google.golang.org/grpc/status"

	pb "github.com/university-ecosystem/core/gen/go/file_processor/v1"
	"github.com/university-ecosystem/file-processor/internal/config"
	gql "github.com/university-ecosystem/file-processor/internal/graphql"
	"github.com/university-ecosystem/file-processor/internal/service"
	"github.com/university-ecosystem/file-processor/internal/workflow"

	"github.com/getsentry/sentry-go"
	"go.opentelemetry.io/contrib/instrumentation/google.golang.org/grpc/otelgrpc"
	"go.opentelemetry.io/contrib/instrumentation/net/http/otelhttp"
	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracegrpc"
	"go.opentelemetry.io/otel/sdk/resource"
	sdktrace "go.opentelemetry.io/otel/sdk/trace"
	semconv "go.opentelemetry.io/otel/semconv/v1.17.0"
)

type contextKey string

const (
	userIDKey contextKey = "user_id"
)

func main() {
	logger, _ := zap.NewProduction()
	defer func() {
		_ = logger.Sync()
	}()

	// Load Config
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
			Release:          "file-processor@1.0.0",
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

	// Connect to Temporal with retry loop
	var c client.Client
	maxAttempts := 10
	for attempt := 1; attempt <= maxAttempts; attempt++ {
		c, err = client.Dial(client.Options{
			HostPort: cfg.TemporalHost,
		})
		if err == nil {
			break
		}
		if attempt == maxAttempts {
			logger.Fatal("Unable to create Temporal client after multiple attempts", zap.Error(err))
		}
		logger.Warn("Failed to connect to Temporal, retrying...",
			zap.Int("attempt", attempt),
			zap.String("addr", cfg.TemporalHost),
			zap.Error(err),
		)
		time.Sleep(time.Duration(attempt) * 2 * time.Second)
	}
	defer c.Close()
	logger.Info("Connected to Temporal", zap.String("addr", cfg.TemporalHost))

	// Start Temporal Worker
	w := worker.New(c, "FILE_PROCESSING_TASK_QUEUE", worker.Options{})

	// Register Workflow and Activities
	w.RegisterWorkflow(workflow.FileProcessingWorkflow)

	// Activities require config-based init (MinIO)
	activities := workflow.NewFileActivities(cfg)
	w.RegisterActivity(activities.ResizeImageActivity)

	// Start Temporal Worker (Non-blocking)
	// w.Run() blocks, but w.Start() does not.
	if err := w.Start(); err != nil {
		logger.Fatal("Unable to start Temporal worker", zap.Error(err))
	}
	defer w.Stop()
	logger.Info("Temporal Worker started", zap.String("queue", "FILE_PROCESSING_TASK_QUEUE"))

	// Connect to NATS (Legacy Support / Optional)
	nc, err := nats.Connect(cfg.NatsURL, nats.RetryOnFailedConnect(true), nats.MaxReconnects(-1))
	if err != nil {
		logger.Warn("Failed to connect to NATS (Legacy)", zap.Error(err))
	} else {
		defer nc.Close()
		js, _ := nc.JetStream()
		if js != nil {
			_, err = js.QueueSubscribe("files.process", "file-processors-temporal", func(msg *nats.Msg) {
				// Trigger workflow async
				var job workflow.ProcessJob
				if err := json.Unmarshal(msg.Data, &job); err != nil {
					logger.Error("Failed to unmarshal NATS message", zap.Error(err))
					_ = msg.Nak() // Negative ack so it can be retried or moved to DLQ
					return
				}

				opt := client.StartWorkflowOptions{ID: "nats-" + job.ID, TaskQueue: "FILE_PROCESSING_TASK_QUEUE"}
				if _, err := c.ExecuteWorkflow(context.Background(), opt, workflow.FileProcessingWorkflow, job); err != nil {
					logger.Error("Failed to execute workflow from NATS", zap.Error(err))
					return
				}

				if err := msg.Ack(); err != nil {
					logger.Error("Failed to ack NATS message", zap.Error(err))
				}
			}, nats.ManualAck())
			if err != nil {
				logger.Error("Failed to subscribe to NATS queue", zap.Error(err))
			}
		}
	}

	// gRPC Server setup
	lis, err := net.Listen("tcp", ":"+cfg.GRPCPort)
	if err != nil {
		logger.Fatal("Failed to listen for gRPC", zap.Error(err))
	}

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

	// Register Implementation from internal/service
	pb.RegisterFileProcessingServiceServer(grpcServer, &service.Server{TemporalClient: c})

	reflection.Register(grpcServer)
	grpc_prometheus.Register(grpcServer)

	// Register standard Health Server
	healthServer := health.NewServer()
	grpc_health_v1.RegisterHealthServer(grpcServer, healthServer)
	healthServer.SetServingStatus("", grpc_health_v1.HealthCheckResponse_SERVING)
	healthServer.SetServingStatus("file_processor.v1.FileProcessingService", grpc_health_v1.HealthCheckResponse_SERVING)

	go func() {
		logger.Info("gRPC Server listening", zap.String("addr", ":"+cfg.GRPCPort))
		if err := grpcServer.Serve(lis); err != nil {
			logger.Fatal("failed to serve gRPC", zap.Error(err))
		}
	}()

	// GraphQL & Metrics HTTP Server
	// Read schema (Assuming it's still in root/workdir)
	s, err := os.ReadFile("schema.graphql")
	var httpHandler http.Handler
	if err != nil {
		logger.Warn("Failed to read schema.graphql, GraphQL disabled", zap.Error(err))
		httpHandler = http.DefaultServeMux
	} else {
		resolver := &gql.Resolver{
			TemporalClient: c,
			MinioBucket:    cfg.MinioBucket,
		}
		schema := graphql.MustParseSchema(string(s), resolver)
		mux := http.NewServeMux()
		mux.Handle("/graphql", &relay.Handler{Schema: schema})
		mux.Handle("/metrics", promhttp.Handler())
		httpHandler = mux
	}

	httpServer := &http.Server{
		Addr:    ":" + cfg.GraphQLPort,
		Handler: otelhttp.NewHandler(httpHandler, "graphql_metrics"),
	}

	go func() {
		logger.Info("GraphQL & Metrics Server listening", zap.String("addr", ":"+cfg.GraphQLPort))
		if err := httpServer.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			logger.Fatal("Failed to serve HTTP", zap.Error(err))
		}
	}()

	// Wait for shutdown signal
	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)
	<-quit

	logger.Info("Shutting down...")

	// Graceful shutdown sequence
	// 1. HTTP Server
	shutdownCtx, shutdownCancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer shutdownCancel()
	if err := httpServer.Shutdown(shutdownCtx); err != nil {
		logger.Error("HTTP Server forced to shutdown", zap.Error(err))
	}

	// 2. gRPC Server
	grpcServer.GracefulStop()

	// 3. Temporal Worker (stopped by defer w.Stop())
	logger.Info("Server exited")
}
func authFunc(secret string, logger *zap.Logger) auth.AuthFunc {
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
			logger.Warn("gRPC auth failed", zap.Error(err))
			return nil, status.Errorf(codes.Unauthenticated, "invalid token: %v", err)
		}

		if claims, ok := token.Claims.(jwt.MapClaims); ok && token.Valid {
			// We could extract user_id and inject into context here
			if sub, ok := claims["sub"].(string); ok {
				newCtx := context.WithValue(ctx, userIDKey, sub)
				return newCtx, nil
			}
		}

		return nil, status.Errorf(codes.Unauthenticated, "invalid token claims")
	}
}
func initTracer(ctx context.Context, cfg *config.Config) (*sdktrace.TracerProvider, error) {
	endpoint := cfg.OTLPEndpoint
	if endpoint == "" {
		endpoint = "jaeger:4317"
	}

	var opts []otlptracegrpc.Option
	opts = append(opts, otlptracegrpc.WithEndpoint(endpoint))

	if cfg.OTLPInsecure {
		// Development / local Docker Compose: no TLS.
		// NEVER set OTLP_INSECURE=true in production environments.
		opts = append(opts, otlptracegrpc.WithInsecure())
	} else {
		// Production: enforce TLS.  The default TLS config uses the system CA
		// pool; override with a custom CA via OTLP_CA_FILE if needed.
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
