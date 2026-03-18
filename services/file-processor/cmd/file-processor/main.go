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
	"syscall"
	"time"

	"github.com/golang-jwt/jwt/v5"
	"github.com/google/uuid"
	enumspb "go.temporal.io/api/enums/v1"
	"github.com/graph-gophers/graphql-go"
	"github.com/graph-gophers/graphql-go/relay"
	"github.com/grpc-ecosystem/go-grpc-middleware/v2/interceptors/auth"
	grpc_prometheus "github.com/grpc-ecosystem/go-grpc-prometheus"
	"github.com/nats-io/nats.go"
	"github.com/prometheus/client_golang/prometheus/promhttp"
	"go.temporal.io/sdk/client"
	"go.temporal.io/sdk/worker"
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
	// MOD-02 (audit Wave 10): semconv v1.27.0 for standardised OTel attributes.
	semconv "go.opentelemetry.io/otel/semconv/v1.27.0"
)

type contextKey string

const (
	userIDKey contextKey = "user_id"
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

	// Load Config
	cfg, err := config.Load()
	if err != nil {
		logger.Error("Failed to load configuration", "err", err)
		os.Exit(1)
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
			logger.Error("Sentry initialization failed", "err", err)
		} else {
			logger.Info("Sentry initialized", "environment", cfg.Environment)
		}
	}

	// Initialize OpenTelemetry
	tp, err := initTracer(ctx, cfg)
	if err != nil {
		logger.Error("OpenTelemetry initialization failed", "err", err)
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
			logger.Error("Unable to create Temporal client after multiple attempts", "err", err)
			os.Exit(1)
		}
		logger.Warn("Failed to connect to Temporal, retrying...",
			"attempt", attempt,
			"addr", cfg.TemporalHost,
			"err", err,
		)
		time.Sleep(time.Duration(attempt) * 2 * time.Second)
	}
	defer c.Close()
	logger.Info("Connected to Temporal", "addr", cfg.TemporalHost)

	// Start Temporal Worker
	w := worker.New(c, "FILE_PROCESSING_TASK_QUEUE", worker.Options{})

	// Register Workflow and Activities
	w.RegisterWorkflow(workflow.FileProcessingWorkflow)

	// FP-P1-02 (audit Wave 10): build a singleton MinIO client with an explicit
	// HTTP connection pool.  All activity invocations share this one client so
	// connections are reused rather than re-established per-activity.
	minioClient, err := workflow.BuildMinIOClient(cfg)
	if err != nil {
		logger.Error("Failed to initialize MinIO client", "err", err)
		os.Exit(1)
	}

	// Activities require config-based init (MinIO)
	// RZ-04 (audit 2026-03-15 Wave 7): NewFileActivities now returns an error
	// instead of panicking, so K8s can restart the pod cleanly on init failure.
	activities, err := workflow.NewFileActivities(cfg, minioClient)
	if err != nil {
		logger.Error("Failed to initialize file activities", "err", err)
		os.Exit(1)
	}
	w.RegisterActivity(activities.ResizeImageActivity)

	// Start Temporal Worker (Non-blocking)
	// w.Run() blocks, but w.Start() does not.
	if err := w.Start(); err != nil {
		logger.Error("Unable to start Temporal worker", "err", err)
		os.Exit(1)
	}
	defer w.Stop()
	logger.Info("Temporal Worker started", "queue", "FILE_PROCESSING_TASK_QUEUE")

	// Connect to NATS (Legacy Support / Optional)
	nc, err := nats.Connect(cfg.NatsURL, nats.RetryOnFailedConnect(true), nats.MaxReconnects(-1))
	if err != nil {
		logger.Warn("Failed to connect to NATS (Legacy)", "err", err)
	} else {
		defer nc.Close()
		js, _ := nc.JetStream()
		if js != nil {
			_, err = js.QueueSubscribe("files.process", "file-processors-temporal", func(msg *nats.Msg) {
				// Trigger workflow async
				var job workflow.ProcessJob
				if err := json.Unmarshal(msg.Data, &job); err != nil {
					logger.Error("Failed to unmarshal NATS message", "err", err)
					_ = msg.Nak() // Negative ack so it can be retried or moved to DLQ
					return
				}

				// FP-P1-03 (audit Wave 10): WorkflowExecutionTimeout hard-caps the
			// entire workflow lifetime so a hung activity cannot orphan a workflow
			// run indefinitely in Temporal.
			//
			// FP-P2-02 (audit Wave 10): append a per-delivery UUID so the
			// workflow ID is unpredictable and NATS redeliveries each get their
			// own run rather than resuming a previous one.  REJECT_DUPLICATE
			// guards against accidental double-submission of the exact same ID.
			opt := client.StartWorkflowOptions{
				ID:                       "proc-" + job.ID + ":" + uuid.NewString(),
				TaskQueue:                "FILE_PROCESSING_TASK_QUEUE",
				WorkflowExecutionTimeout: 30 * time.Minute,
				WorkflowIDReusePolicy:    enumspb.WORKFLOW_ID_REUSE_POLICY_REJECT_DUPLICATE,
			}
				// TD-01 (Wave 12): use a timeout context instead of context.Background()
			// so that a Temporal outage does not accumulate blocking goroutines
			// indefinitely. 5 s is generous for a workflow enqueue (not execution).
			wfCtx, wfCancel := context.WithTimeout(ctx, 5*time.Second)
			_, execErr := c.ExecuteWorkflow(wfCtx, opt, workflow.FileProcessingWorkflow, job)
			wfCancel()
			if execErr != nil {
					logger.Error("Failed to execute workflow from NATS", "err", execErr)
					return
				}

				if err := msg.Ack(); err != nil {
					logger.Error("Failed to ack NATS message", "err", err)
				}
			}, nats.ManualAck())
			if err != nil {
				logger.Error("Failed to subscribe to NATS queue", "err", err)
			}
		}
	}

	// gRPC Server setup
	lis, err := net.Listen("tcp", ":"+cfg.GRPCPort)
	if err != nil {
		logger.Error("Failed to listen for gRPC", "err", err)
		os.Exit(1)
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
		logger.Info("gRPC Server listening", "addr", ":"+cfg.GRPCPort)
		if err := grpcServer.Serve(lis); err != nil {
			logger.Error("failed to serve gRPC", "err", err)
			os.Exit(1)
		}
	}()

	// GraphQL & Metrics HTTP Server
	// Read schema (Assuming it's still in root/workdir)
	s, err := os.ReadFile("schema.graphql")
	// FP-P2-01 (audit Wave 10): previously fell back to http.DefaultServeMux when
	// schema.graphql was missing. http.DefaultServeMux exposes /debug/pprof/ and
	// /debug/vars if those packages are imported anywhere in the binary — all
	// without authentication. Fail-secure: exit rather than start an unprotected server.
	if err != nil {
		logger.Error("schema.graphql not found — refusing to start without GraphQL schema; "+
			"ensure schema.graphql is present in the working directory",
			"err", err,
			"hint", "copy schema.graphql to the binary working directory",
		)
		os.Exit(1)
	}
	var httpHandler http.Handler
	{
		resolver := &gql.Resolver{
			TemporalClient: c,
			MinioBucket:    cfg.MinioBucket,
		}
		// RED-04 (audit Wave 11): Disable GraphQL introspection in production.
		// OWASP API8:2023 — introspection enables schema reconnaissance for attackers
		// with network access to this internal service (:8003). Keep enabled in dev/staging
		// for tooling (GraphiQL, codegen, schema stitching).
		var schemaOpts []graphql.SchemaOpt
		if cfg.Environment == "production" {
			schemaOpts = append(schemaOpts, graphql.DisableIntrospection())
		}
		schema := graphql.MustParseSchema(string(s), resolver, schemaOpts...)
		mux := http.NewServeMux()
		// GO-1 (audit 2026-03): wrap /graphql with JWT auth middleware.
		// /metrics intentionally has no JWT auth — it is protected at the
		// network level (internal service mesh) and/or Prometheus scrape credentials.
		graphqlHandler := httpJWTMiddleware(cfg.JWTSecret, logger, &relay.Handler{Schema: schema})
		mux.Handle("/graphql", graphqlHandler)
		mux.Handle("/metrics", promhttp.Handler())
		httpHandler = mux
	}

	httpServer := &http.Server{
		Addr:    ":" + cfg.GraphQLPort,
		Handler: otelhttp.NewHandler(httpHandler, "graphql_metrics"),
	}

	go func() {
		logger.Info("GraphQL & Metrics Server listening", "addr", ":"+cfg.GraphQLPort)
		if err := httpServer.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			logger.Error("Failed to serve HTTP", "err", err)
			os.Exit(1)
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
		logger.Error("HTTP Server forced to shutdown", "err", err)
	}

	// 2. gRPC Server
	grpcServer.GracefulStop()

	// 3. Temporal Worker (stopped by defer w.Stop())
	logger.Info("Server exited")
}

// httpJWTMiddleware validates the Bearer token in HTTP requests using the
// same JWT secret as the gRPC authFunc.  Requests without a valid token
// receive 401 Unauthorized.
//
// GO-1 (audit 2026-03): The /graphql HTTP endpoint was registered on the mux
// without any authentication, while /grpc already had JWT validation via the
// grpc-middleware auth interceptor.  This middleware closes that gap.
func httpJWTMiddleware(secret string, log *slog.Logger, next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		authHeader := r.Header.Get("Authorization")
		const prefix = "Bearer "
		if len(authHeader) <= len(prefix) || authHeader[:len(prefix)] != prefix {
			log.Warn("GraphQL HTTP request missing or malformed Authorization header",
				"remote", r.RemoteAddr,
			)
			http.Error(w, "Unauthorized", http.StatusUnauthorized)
			return
		}
		tokenStr := authHeader[len(prefix):]

		token, err := jwt.Parse(tokenStr, func(t *jwt.Token) (interface{}, error) {
			if _, ok := t.Method.(*jwt.SigningMethodHMAC); !ok {
				return nil, status.Errorf(codes.Unauthenticated, "unexpected signing method: %v", t.Header["alg"])
			}
			return []byte(secret), nil
		})
		if err != nil || !token.Valid {
			log.Warn("GraphQL HTTP JWT validation failed",
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
			logger.Warn("gRPC auth failed", "err", err)
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
		// TD-02 (Wave 12): fail-fast in production — a comment is not enforcement.
		// Mirrors _enforce_production_secrets pattern from the Python backend.
		if cfg.Environment == "production" {
			return nil, errors.New(
				"OTLP_INSECURE=true is forbidden in production; unset OTLP_INSECURE or set it to false",
			)
		}
		slog.Warn("OTLP running without TLS — development mode only; never set OTLP_INSECURE=true in production")
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
