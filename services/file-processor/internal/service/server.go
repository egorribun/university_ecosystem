package service

import (
	"context"
	"errors"
	"fmt"
	"time"

	pb "github.com/university-ecosystem/core/gen/go/file_processor/v1"
	"github.com/university-ecosystem/file-processor/internal/workflow"
	"go.temporal.io/sdk/client"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

// Server implements the FileProcessingService gRPC server.
type Server struct {
	pb.UnimplementedFileProcessingServiceServer
	TemporalClient client.Client
}

// ProcessFile is the gRPC method to start a file processing job.
func (s *Server) ProcessFile(ctx context.Context, req *pb.ProcessFileRequest) (*pb.ProcessFileResponse, error) {
	// Create common job from proto
	job := workflow.ProcessJob{
		ID:        req.Id,
		Type:      req.Type,
		SourceKey: req.SourceKey,
		DestKey:   req.DestKey,
		Options:   make(map[string]interface{}),
	}
	for k, v := range req.Options {
		job.Options[k] = v
	}

	workflowOptions := client.StartWorkflowOptions{
		ID:        "file-process-" + req.Id,
		TaskQueue: "FILE_PROCESSING_TASK_QUEUE",
	}

	// RED-05 (audit Wave 11): Bound the ExecuteWorkflow call with an explicit timeout.
	// Without this, a slow or unavailable Temporal server causes the gRPC handler to
	// block indefinitely, accumulating goroutines and exhausting the thread pool under load.
	// 5s is enough to start a workflow — the actual processing runs asynchronously in Temporal.
	const workflowStartTimeout = 5 * time.Second
	startCtx, startCancel := context.WithTimeout(ctx, workflowStartTimeout)
	defer startCancel()

	// Start workflow asynchronously
	we, err := s.TemporalClient.ExecuteWorkflow(startCtx, workflowOptions, workflow.FileProcessingWorkflow, job)
	if err != nil {
		if errors.Is(err, context.DeadlineExceeded) {
			return nil, status.Error(codes.DeadlineExceeded, "temporal unavailable: workflow start timed out")
		}
		return nil, fmt.Errorf("failed to start workflow: %w", err)
	}

	// Return immediately with the Job ID (RunID)
	return &pb.ProcessFileResponse{
		JobId:      we.GetID(),
		Success:    true,
		DestKey:    "",
		Error:      "",
		DurationMs: 0,
	}, nil
}
