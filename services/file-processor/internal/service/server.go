package service

import (
	"context"
	"errors"
	"fmt"
	"path"
	"strings"
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

// RZ-23-04 (audit 2026-03-25 Wave 23): Validate inputs before persisting to
// Temporal workflow history. Without validation, invalid/malicious payloads are
// retried 5 times before DLQ, wasting Temporal storage and compute. The Options
// map is bounded to prevent DoS via bloated workflow history.
var allowedFileTypes = map[string]bool{
	"image_resize":    true,
	"image_compress":  true,
	"pdf_preview":     true,
	"video_transcode": true,
}

const (
	maxOptionsCount   = 10
	maxOptionKeyLen   = 64
	maxOptionValueLen = 1024
)

// ProcessFile is the gRPC method to start a file processing job.
// validateProcessFileRequest performs input validation on gRPC requests.
// RZ-23-04: reject invalid requests before Temporal workflow start.
func validateProcessFileRequest(req *pb.ProcessFileRequest) error {
	if err := validateProcessFileIdentity(req); err != nil {
		return err
	}
	if err := validateProcessFileKeys(req.SourceKey, req.DestKey); err != nil {
		return err
	}
	return validateProcessFileOptions(req.Options)
}

func validateProcessFileIdentity(req *pb.ProcessFileRequest) error {
	if req.Id == "" {
		return status.Error(codes.InvalidArgument, "id is required")
	}
	if !allowedFileTypes[req.Type] {
		return status.Errorf(codes.InvalidArgument, "unsupported file type: %q", req.Type)
	}
	if req.SourceKey == "" || req.DestKey == "" {
		return status.Error(codes.InvalidArgument, "source_key and dest_key are required")
	}
	return nil
}

func validateProcessFileKeys(sourceKey, destKey string) error {
	// RZ-26-04: bound key lengths to prevent Temporal workflow history bloat.
	const maxKeyLen = 1024
	if len(sourceKey) > maxKeyLen || len(destKey) > maxKeyLen {
		return status.Errorf(codes.InvalidArgument, "source_key/dest_key exceeds %d bytes", maxKeyLen)
	}
	// RZ-27-04: Reject path traversal at gRPC boundary before Temporal workflow
	// start. sanitizeMinIOKey in workflow.go catches this too (defense in depth).
	for _, key := range []string{sourceKey, destKey} {
		// Object keys are always relative to the configured tenant prefix.  Check
		// the raw value before path.Clean: Clean("/../../etc/passwd") yields
		// "/etc/passwd", which no longer contains a detectable ".." segment.
		// Reject both slash styles at the boundary so platform-specific input
		// cannot escape the prefix when a key is later interpreted by another
		// storage adapter.
		if err := validateProcessFileKey(key); err != nil {
			return err
		}
	}
	return nil
}

func validateProcessFileKey(key string) error {
	if path.IsAbs(key) || strings.HasPrefix(key, "/") || strings.HasPrefix(key, "\\") {
		return status.Errorf(codes.InvalidArgument, "absolute path is not allowed in key: %q", key)
	}
	cleaned := path.Clean(key)
	if strings.HasPrefix(cleaned, "..") || strings.Contains(cleaned, "/../") {
		return status.Errorf(codes.InvalidArgument, "path traversal in key: %q", key)
	}
	return nil
}

func validateProcessFileOptions(options map[string]string) error {
	if len(options) > maxOptionsCount {
		return status.Errorf(codes.InvalidArgument, "options count %d exceeds limit of %d", len(options), maxOptionsCount)
	}
	for k, v := range options {
		if len(k) > maxOptionKeyLen || len(v) > maxOptionValueLen {
			return status.Error(codes.InvalidArgument, "option key/value exceeds size limit")
		}
	}
	return nil
}

// ProcessFile validates the request and starts an async Temporal workflow.
func (s *Server) ProcessFile(ctx context.Context, req *pb.ProcessFileRequest) (*pb.ProcessFileResponse, error) {
	if err := validateProcessFileRequest(req); err != nil {
		return nil, err
	}

	// Create common job from proto
	job := workflow.ProcessJob{
		ID:        req.Id,
		Type:      req.Type,
		SourceKey: req.SourceKey,
		DestKey:   req.DestKey,
		Options:   make(map[string]interface{}, len(req.Options)),
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
	if we == nil {
		return nil, fmt.Errorf("temporal client returned nil workflow run without error")
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
