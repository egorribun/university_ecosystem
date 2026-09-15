package service

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"strings"
	"time"

	pb "github.com/university-ecosystem/core/gen/go/file_processor/v1"
	"github.com/university-ecosystem/file-processor/internal/objectkey"
	"github.com/university-ecosystem/file-processor/internal/workflow"
	enumspb "go.temporal.io/api/enums/v1"
	"go.temporal.io/sdk/client"
	"go.temporal.io/sdk/temporal"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/metadata"
	"google.golang.org/grpc/status"
)

// Server implements the FileProcessingService gRPC server.
type Server struct {
	pb.UnimplementedFileProcessingServiceServer
	TemporalClient    client.Client
	CapabilitySecret  []byte
	RequireCapability bool
	// ReplayGuard is shared by every file-processing ingress in a process. A
	// nil guard keeps local development compatibility; release setup must inject
	// one so a signed bearer capability cannot be replayed.
	ReplayGuard pb.CapabilityReplayGuard
	Now         func() time.Time
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
	const maxKeyLen = objectkey.MaxLength
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
	normalized, err := objectkey.Normalize(key)
	if err != nil {
		if errors.Is(err, objectkey.ErrAbsolute) {
			return status.Error(codes.InvalidArgument, "absolute path is not allowed in key")
		}
		if errors.Is(err, objectkey.ErrNUL) {
			return status.Error(codes.InvalidArgument, "object key contains NUL")
		}
		if errors.Is(err, objectkey.ErrEmpty) {
			return status.Error(codes.InvalidArgument, "object key must not be empty")
		}
		// All other errors from the shared validator are rejected as traversal;
		// this fail-closed fallback keeps future guards from becoming bypasses.
		return status.Error(codes.InvalidArgument, "path traversal in key")
	}
	if normalized != key {
		return status.Error(codes.InvalidArgument, "object key must be canonical")
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

func (s *Server) authorizeCapability(ctx context.Context, req *pb.ProcessFileRequest) (string, pb.ProcessingCapabilityClaims, error) {
	if !s.RequireCapability {
		return "", pb.ProcessingCapabilityClaims{}, nil
	}
	identity, ok := pb.ProcessingIdentityFromContext(ctx)
	if !ok {
		return "", pb.ProcessingCapabilityClaims{}, status.Error(codes.PermissionDenied, "file processing authorization required")
	}
	values := metadata.ValueFromIncomingContext(ctx, strings.ToLower(pb.ProcessingCapabilityHeader))
	if len(values) != 1 || strings.TrimSpace(values[0]) == "" {
		return "", pb.ProcessingCapabilityClaims{}, status.Error(codes.PermissionDenied, "file processing authorization required")
	}
	now := time.Now().UTC()
	if s.Now != nil {
		now = s.Now().UTC()
	}
	claims, err := pb.VerifyProcessingCapability(values[0], s.CapabilitySecret, now)
	if err != nil {
		return "", pb.ProcessingCapabilityClaims{}, status.Error(codes.PermissionDenied, "file processing authorization required")
	}
	// The gRPC boundary has already rejected unsafe keys. Normalize once more and
	// require byte-for-byte equality so an alternate representation cannot be
	// authorized by a proof for a different canonical object.
	sourceKey, sourceErr := objectkey.Normalize(req.SourceKey)
	destKey, destErr := objectkey.Normalize(req.DestKey)
	if sourceErr != nil || destErr != nil || sourceKey != req.SourceKey || destKey != req.DestKey {
		return "", pb.ProcessingCapabilityClaims{}, status.Error(codes.PermissionDenied, "file processing authorization required")
	}
	if !claims.Matches(pb.ProcessingCapabilityExpectation{
		ID:        req.Id,
		Type:      req.Type,
		SourceKey: sourceKey,
		DestKey:   destKey,
		UserID:    identity.UserID,
		SessionID: identity.SessionID,
		TenantID:  identity.TenantID,
	}) {
		return "", pb.ProcessingCapabilityClaims{}, status.Error(codes.PermissionDenied, "file processing authorization required")
	}
	return values[0], claims, nil
}

// ProcessFile validates the request and starts an async Temporal workflow.
func (s *Server) ProcessFile(ctx context.Context, req *pb.ProcessFileRequest) (*pb.ProcessFileResponse, error) {
	if err := validateProcessFileRequest(req); err != nil {
		return nil, err
	}
	_, capabilityClaims, err := s.authorizeCapability(ctx, req)
	if err != nil {
		return nil, err
	}

	// Create common job from proto
	job := workflow.ProcessJob{
		ID:   req.Id,
		Type: req.Type,
		// The workflow calls objectkey.Normalize again immediately before
		// storage access, after this boundary has rejected unsafe values.
		SourceKey: req.SourceKey,
		DestKey:   req.DestKey,
		// The bearer capability authenticates this ingress only. It is
		// intentionally not copied into Temporal history, where durable payloads
		// would outlive the short-lived proof and expose it to workflow readers.
		Capability: "",
		Options:    make(map[string]interface{}, len(req.Options)),
	}
	for k, v := range req.Options {
		job.Options[k] = v
	}

	workflowOptions := client.StartWorkflowOptions{
		ID:                    "file-process-" + req.Id,
		TaskQueue:             "FILE_PROCESSING_TASK_QUEUE",
		WorkflowIDReusePolicy: enumspb.WORKFLOW_ID_REUSE_POLICY_REJECT_DUPLICATE,
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
		// REJECT_DUPLICATE is the cross-ingress idempotency authority. A
		// redelivery can therefore safely return the deterministic workflow ID
		// instead of exposing Temporal's internal AlreadyStarted error as an
		// opaque gRPC Unknown failure.
		if temporal.IsWorkflowExecutionAlreadyStartedError(err) {
			return &pb.ProcessFileResponse{
				JobId:      workflowOptions.ID,
				Success:    true,
				DestKey:    "",
				Error:      "",
				DurationMs: 0,
			}, nil
		}
		if errors.Is(err, context.DeadlineExceeded) {
			return nil, status.Error(codes.DeadlineExceeded, "temporal unavailable: workflow start timed out")
		}
		return nil, fmt.Errorf("failed to start workflow: %w", err)
	}
	if we == nil {
		return nil, fmt.Errorf("temporal client returned nil workflow run without error")
	}
	// Temporal is the authoritative idempotency boundary: every ingress uses
	// the same deterministic workflow ID and REJECT_DUPLICATE policy. Record the
	// nonce only after ExecuteWorkflow succeeds so a transient Temporal outage
	// never burns a valid capability before the job exists. If this best-effort
	// defense-in-depth record is unavailable, the already-started deterministic
	// workflow remains safe and the caller still receives the real job ID.
	if s.RequireCapability && s.ReplayGuard != nil {
		if _, replayErr := pb.ConsumeCapabilityReplay(
			ctx,
			s.ReplayGuard,
			capabilityClaims.Nonce,
			time.Unix(capabilityClaims.ExpiresAt, 0),
			nowUTC(s.Now),
		); replayErr != nil {
			// The deterministic Temporal workflow ID remains the idempotency
			// authority. Keep the accepted job successful while recording a
			// non-sensitive diagnostic for an unavailable replay guard.
			slog.Default().ErrorContext(ctx, "capability replay admission failed after workflow start", "error_type", fmt.Sprintf("%T", replayErr))
		}
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

func nowUTC(now func() time.Time) time.Time {
	if now != nil {
		return now().UTC()
	}
	return time.Now().UTC()
}
