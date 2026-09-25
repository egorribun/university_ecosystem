package graphql

import (
	"context"
	"fmt"
	"log/slog"
	"net/url"
	"strings"
	"time"

	"github.com/google/uuid"
	gql "github.com/graph-gophers/graphql-go"
	pb "github.com/university-ecosystem/core/gen/go/file_processor/v1"
	"github.com/university-ecosystem/file-processor/internal/objectkey"
	"github.com/university-ecosystem/file-processor/internal/workflow"
	enumspb "go.temporal.io/api/enums/v1"
	"go.temporal.io/sdk/client"
	"go.temporal.io/sdk/temporal"
)

// Resolver is the root resolver for the GraphQL API.
type Resolver struct {
	TemporalClient    client.Client
	CapabilitySecret  []byte
	RequireCapability bool
	// ReplayGuard is shared with the gRPC and NATS ingress paths by production
	// bootstrap, preventing a capability from crossing ingress boundaries twice.
	ReplayGuard pb.CapabilityReplayGuard
	Now         func() time.Time
}

// Health returns the health status of the service.
func (r *Resolver) Health() string {
	return "OK"
}

func sanitizeKey(key string) (string, error) {
	// GraphQL historically accepted one leading slash as a shorthand for a
	// relative object key. Preserve that compatibility while routing the actual
	// validation through the same platform-neutral boundary as gRPC, NATS, and
	// Temporal activities.
	key = strings.TrimPrefix(key, "/")
	cleaned, err := objectkey.Normalize(key)
	if err != nil {
		return "", fmt.Errorf("invalid path string")
	}
	return cleaned, nil
}

// publicImagePath returns the same-origin backend image-proxy path for key.
// Unlike a direct object-storage URL it works in every environment and keeps
// the backend's public-prefix authorization in front of the private bucket.
func publicImagePath(key string) string {
	segments := strings.Split(key, "/")
	for index, segment := range segments {
		segments[index] = url.PathEscape(segment)
	}
	return "/api/v1/img/" + strings.Join(segments, "/")
}

// File returns a resolver for a specific file.
//
// W140 (z) #1: args.ID must be gql.ID (not string) because schema.graphql
// declares `file(id: ID!): File` and graph-gophers/graphql-go v1.9.0+ enforces
// strict ID type via MustParseSchema. Pre-W140 this was masked because
// schema.graphql was missing from the runtime image (W139 §Honesty #7) — the
// schema parse failed at step 9 before MustParseSchema reached the resolver
// type check.
func (r *Resolver) File(args struct{ ID gql.ID }) *FileResolver {
	safeID, err := sanitizeKey(string(args.ID))
	if err != nil {
		// In a real GraphQL context, return an error, but here we fallback to safe empty
		safeID = "invalid-path"
	}

	return &FileResolver{
		id:  safeID,
		url: publicImagePath(safeID),
	}
}

// ProcessFile starts a file processing job.
func (r *Resolver) ProcessFile(ctx context.Context, args struct{ Input ProcessFileInput }) (*FileJobResolver, error) {
	options := make(map[string]interface{})
	if args.Input.Width != nil {
		options["width"] = int(*args.Input.Width)
	}
	if args.Input.Height != nil {
		options["height"] = int(*args.Input.Height)
	}

	safeSourceKey, err := sanitizeKey(args.Input.SourceKey)
	if err != nil {
		return nil, fmt.Errorf("invalid source key: %v", err)
	}

	safeDestKey, err := sanitizeKey(args.Input.DestKey)
	if err != nil {
		return nil, fmt.Errorf("invalid destination key: %v", err)
	}

	jobID := generateID()
	var capabilityClaims pb.ProcessingCapabilityClaims
	var capabilityNow time.Time
	if r.RequireCapability {
		identity, ok := pb.ProcessingIdentityFromContext(ctx)
		if !ok {
			return nil, fmt.Errorf("file processing authorization required")
		}
		now := time.Now().UTC()
		if r.Now != nil {
			now = r.Now().UTC()
		}
		capabilityNow = now
		claims, verifyErr := pb.VerifyProcessingCapability(args.Input.Capability, r.CapabilitySecret, now)
		if verifyErr != nil || !claims.Matches(pb.ProcessingCapabilityExpectation{
			ID: claims.ID, Type: args.Input.Type, SourceKey: safeSourceKey,
			DestKey: safeDestKey, UserID: identity.UserID,
			SessionID: identity.SessionID, TenantID: identity.TenantID,
		}) {
			return nil, fmt.Errorf("file processing authorization required")
		}
		capabilityClaims = claims
		jobID = claims.ID
	}

	job := workflow.ProcessJob{
		ID:        jobID,
		Type:      args.Input.Type,
		SourceKey: safeSourceKey,
		DestKey:   safeDestKey,
		// The bearer capability is an ingress proof, not workflow data. Do not
		// persist it in Temporal history after this boundary has verified it.
		Capability: "",
		Options:    options,
	}

	workflowOptions := client.StartWorkflowOptions{
		// All ingresses use the same workflow namespace. This is a second line of
		// defense if a deployment has not yet wired a shared replay guard.
		ID:                    "file-process-" + job.ID,
		TaskQueue:             "FILE_PROCESSING_TASK_QUEUE",
		WorkflowIDReusePolicy: enumspb.WORKFLOW_ID_REUSE_POLICY_REJECT_DUPLICATE,
	}

	run, err := r.TemporalClient.ExecuteWorkflow(ctx, workflowOptions, workflow.FileProcessingWorkflow, job)
	if err != nil {
		// REJECT_DUPLICATE is the shared idempotency boundary for every ingress.
		// Treat a duplicate submission as a successful handoff to the existing
		// deterministic workflow rather than leaking Temporal's internal error to
		// GraphQL clients.
		if temporal.IsWorkflowExecutionAlreadyStartedError(err) {
			return &FileJobResolver{
				jobID:     workflowOptions.ID,
				status:    "STARTED",
				resultURL: "",
			}, nil
		}
		return nil, err
	}
	// Temporal owns idempotency for this mutation. Every ingress submits the
	// same deterministic workflow ID with REJECT_DUPLICATE, so record the
	// capability nonce only after the workflow has been accepted. A transient
	// start failure therefore leaves the capability retryable, while a replay
	// cannot create a second workflow even if this defense-in-depth registry is
	// temporarily unavailable.
	if r.RequireCapability && r.ReplayGuard != nil {
		if _, replayErr := pb.ConsumeCapabilityReplay(
			ctx,
			r.ReplayGuard,
			capabilityClaims.Nonce,
			time.Unix(capabilityClaims.ExpiresAt, 0),
			capabilityNow,
		); replayErr != nil {
			// The deterministic Temporal workflow ID remains the idempotency
			// authority. Keep the accepted job successful while recording a
			// non-sensitive diagnostic for an unavailable replay guard.
			slog.Default().ErrorContext(ctx, "capability replay admission failed after workflow start", "error_type", fmt.Sprintf("%T", replayErr))
		}
	}

	return &FileJobResolver{
		jobID:     run.GetID(),
		status:    "STARTED",
		resultURL: "",
	}, nil
}

// -- Sub-Resolvers --

// FileResolver resolves file-related fields.
type FileResolver struct {
	id  string
	url string
}

// ID returns the file ID.
//
// W140 (z) #1: return type is gql.ID (not string) per GraphQL ID! spec.
func (r *FileResolver) ID() gql.ID { return gql.ID(r.id) }

// URL returns the file URL.
func (r *FileResolver) URL() string { return r.url }

// Size returns the file size (mocked).
func (r *FileResolver) Size() *int32 { s := int32(0); return &s } // Mock

// Type returns the file type (mocked).
func (r *FileResolver) Type() *string { t := "unknown"; return &t }

// FileJobResolver resolves file processing job fields.
type FileJobResolver struct {
	jobID     string
	status    string
	resultURL string
}

// JobID returns the job ID.
//
// W140 (z) #1: return type is gql.ID (not string) per schema FileJob.jobId ID!.
func (r *FileJobResolver) JobID() gql.ID { return gql.ID(r.jobID) }

// Status returns the job status.
func (r *FileJobResolver) Status() string { return r.status }

// ResultURL returns the result URL.
func (r *FileJobResolver) ResultURL() *string { return &r.resultURL }

// ProcessFileInput defines the input for the ProcessFile mutation.
type ProcessFileInput struct {
	Type       string
	SourceKey  string
	DestKey    string
	Capability string
	Width      *int32
	Height     *int32
}

// RZ-W19-17: use UUID instead of nanosecond timestamp to avoid collisions.
func generateID() string {
	return fmt.Sprintf("file-process-%s", uuid.New().String())
}
