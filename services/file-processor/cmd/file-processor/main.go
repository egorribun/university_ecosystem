package main

import (
	"context"
	"encoding/json"
	"log"
	"net"
	"net/http"
	"os"
	"os/signal"
	"sync"
	"syscall"

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
	defer logger.Sync()

	// Load Config via Viper
	cfg := config.Load()

	// Connect to Temporal
	c, err := client.Dial(client.Options{
		HostPort: cfg.TemporalHost,
	})
	if err != nil {
		log.Fatalf("Unable to create client", err)
	}
	defer c.Close()

	// Start Temporal Worker
	w := worker.New(c, "FILE_PROCESSING_TASK_QUEUE", worker.Options{})

	// Register Workflow and Activities
	w.RegisterWorkflow(workflow.FileProcessingWorkflow)

	// Activities require config-based init (MinIO)
	activities := workflow.NewFileActivities(cfg)
	w.RegisterActivity(activities.ResizeImageActivity)

	// Wait group for services
	var wg sync.WaitGroup

	// Start listening to Task Queue
	wg.Add(1)
	go func() {
		defer wg.Done()
		if err := w.Run(worker.InterruptCh()); err != nil {
			log.Fatalf("Unable to start worker", err)
		}
	}()
	logger.Info("Temporal Worker started", zap.String("queue", "FILE_PROCESSING_TASK_QUEUE"))

	// Connect to NATS (Legacy Support / Optional)
	nc, err := nats.Connect(cfg.NatsURL, nats.RetryOnFailedConnect(true), nats.MaxReconnects(-1))
	if err != nil {
		logger.Warn("Failed to connect to NATS (Legacy)", zap.Error(err))
	} else {
		defer nc.Close()
		js, _ := nc.JetStream()
		if js != nil {
			js.QueueSubscribe("files.process", "file-processors-temporal", func(msg *nats.Msg) {
				// Trigger workflow async
				var job workflow.ProcessJob
				json.Unmarshal(msg.Data, &job) // Error handling omitted for brevity
				opt := client.StartWorkflowOptions{ID: "nats-" + job.ID, TaskQueue: "FILE_PROCESSING_TASK_QUEUE"}
				c.ExecuteWorkflow(context.Background(), opt, workflow.FileProcessingWorkflow, job)
				msg.Ack()
			}, nats.ManualAck())
		}
	}

	// Start gRPC Server
	wg.Add(1)
	go func() {
		defer wg.Done()
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

		logger.Info("gRPC Server listening", zap.String("addr", ":"+cfg.GRPCPort))
		if err := grpcServer.Serve(lis); err != nil {
			logger.Fatal("failed to serve gRPC", zap.Error(err))
		}
	}()

	// Start GraphQL Server
	wg.Add(1)
	go func() {
		defer wg.Done()

		// Read schema (Assuming it's still in root/workdir or we move it? Keeping usage relative to running pwd)
		// For robustness, ideally embed this or load from specific location
		s, err := os.ReadFile("schema.graphql")
		if err != nil {
			// Fallback or panic?
			logger.Warn("Failed to read schema.graphql, GraphQL disabled", zap.Error(err))
			return
		}

		resolver := &gql.Resolver{
			TemporalClient: c,
			MinioBucket:    cfg.MinioBucket,
		}

		schema := graphql.MustParseSchema(string(s), resolver)
		http.Handle("/graphql", &relay.Handler{Schema: schema})

		// Expose Prometheus Metrics
		http.Handle("/metrics", promhttp.Handler())

		logger.Info("GraphQL & Metrics Server listening", zap.String("addr", ":"+cfg.GraphQLPort))
		if err := http.ListenAndServe(":"+cfg.GraphQLPort, nil); err != nil {
			logger.Fatal("Failed to serve GraphQL", zap.Error(err))
		}
	}()

	// Wait for shutdown
	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)
	<-quit

	logger.Info("Shutting down...")
}
