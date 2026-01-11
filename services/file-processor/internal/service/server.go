package service

import (
	"context"
	"fmt"

	pb "github.com/university-ecosystem/core/gen/go/file_processor/v1"
	"github.com/university-ecosystem/file-processor/internal/workflow"
	"go.temporal.io/sdk/client"
)

// Server implements the FileProcessingService gRPC server
type Server struct {
	pb.UnimplementedFileProcessingServiceServer
	TemporalClient client.Client
}

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

	// Start workflow asynchronously
	we, err := s.TemporalClient.ExecuteWorkflow(ctx, workflowOptions, workflow.FileProcessingWorkflow, job)
	if err != nil {
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
