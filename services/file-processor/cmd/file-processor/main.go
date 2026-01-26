package main

import (
	"context"
	"encoding/json"
	"net"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/graph-gophers/graphql-go"
	"github.com/graph-gophers/graphql-go/relay"
	grpc_prometheus "github.com/grpc-ecosystem/go-grpc-prometheus"
	"github.com/nats-io/nats.go"
	"github.com/prometheus/client_golang/prometheus/promhttp"
	"go.temporal.io/sdk/client"
	"go.temporal.io/sdk/worker"
	"go.uber.org/zap"
	"google.golang.org/grpc"
	"google.golang.org/grpc/health"
	"google.golang.org/grpc/health/grpc_health_v1"
	"google.golang.org/grpc/reflection"

	pb "github.com/university-ecosystem/core/gen/go/file_processor/v1"
	"github.com/university-ecosystem/file-processor/internal/config"
	gql "github.com/university-ecosystem/file-processor/internal/graphql"
	"github.com/university-ecosystem/file-processor/internal/service"
	"github.com/university-ecosystem/file-processor/internal/workflow"
)

func main() {
	logger, _ := zap.NewProduction()
	defer func() { _ = logger.Sync() }()

	// Load Config
	cfg, err := config.Load()
	if err != nil {
		logger.Fatal("Failed to load configuration", zap.Error(err))
	}

	// Connect to Temporal
	c, err := client.Dial(client.Options{
		HostPort: cfg.TemporalHost,
	})
	if err != nil {
		logger.Fatal("Unable to create Temporal client", zap.Error(err))
	}
	defer c.Close()

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
			_, err := js.QueueSubscribe("files.process", "file-processors-temporal", func(msg *nats.Msg) {
				// Trigger workflow async
				var job workflow.ProcessJob
				if err := json.Unmarshal(msg.Data, &job); err != nil {
					logger.Warn("Failed to unmarshal NATS message", zap.Error(err))
					return
				}
				opt := client.StartWorkflowOptions{ID: "nats-" + job.ID, TaskQueue: "FILE_PROCESSING_TASK_QUEUE"}
				if _, err := c.ExecuteWorkflow(context.Background(), opt, workflow.FileProcessingWorkflow, job); err != nil {
					logger.Warn("Failed to execute workflow from NATS", zap.Error(err))
				}
				_ = msg.Ack()
			}, nats.ManualAck())
			if err != nil {
				logger.Warn("Failed to subscribe to NATS queue", zap.Error(err))
			}
		}
	}

	// gRPC Server setup
	lis, err := net.Listen("tcp", ":"+cfg.GRPCPort)
	if err != nil {
		logger.Fatal("Failed to listen for gRPC", zap.Error(err))
	}

	grpcServer := grpc.NewServer(
		grpc.StreamInterceptor(grpc_prometheus.StreamServerInterceptor),
		grpc.UnaryInterceptor(grpc_prometheus.UnaryServerInterceptor),
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
		Handler: httpHandler,
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
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	if err := httpServer.Shutdown(ctx); err != nil {
		logger.Error("HTTP Server forced to shutdown", zap.Error(err))
	}

	// 2. gRPC Server
	grpcServer.GracefulStop()

	// 3. Temporal Worker (stopped by defer w.Stop())
	logger.Info("Server exited")
}
