package service

import (
	"context"
	"strings"
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	pb "github.com/university-ecosystem/core/gen/go/file_processor/v1"
	"github.com/university-ecosystem/file-processor/internal/workflow"
	"go.temporal.io/sdk/client"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/metadata"
	"google.golang.org/grpc/status"
	"google.golang.org/protobuf/proto"
)

var capabilityKey = strings.Repeat("k", 32)

func capabilityRequest() *pb.ProcessFileRequest {
	return &pb.ProcessFileRequest{
		Id:        "job-capability-1",
		Type:      "image_resize",
		SourceKey: "users/u-1/source.png",
		DestKey:   "users/u-1/dest.png",
		Options:   map[string]string{"width": "100"},
	}
}

func capabilityContext(t *testing.T, req *pb.ProcessFileRequest, user, session string) context.Context {
	t.Helper()
	return capabilityContextAt(t, req, user, session, time.Unix(1_700_000_000, 0))
}

func capabilityContextAt(t *testing.T, req *pb.ProcessFileRequest, user, session string, now time.Time) context.Context {
	t.Helper()
	token, err := pb.MintProcessingCapabilityAt([]byte(capabilityKey), pb.ProcessingCapabilityClaims{
		ID:        req.Id,
		Type:      req.Type,
		SourceKey: req.SourceKey,
		DestKey:   req.DestKey,
		UserID:    user,
		SessionID: session,
		ExpiresAt: now.Add(5 * time.Minute).Unix(),
		Nonce:     "nonce-capability-123",
	}, now)
	require.NoError(t, err)
	ctx := metadata.NewIncomingContext(context.Background(), metadata.Pairs(
		strings.ToLower(pb.ProcessingCapabilityHeader), token,
	))
	return pb.WithProcessingIdentity(ctx, pb.ProcessingIdentity{UserID: user, SessionID: session})
}

func TestProcessFile_RequiresOwnerBoundCapability(t *testing.T) {
	called := false
	server := &Server{
		CapabilitySecret:  []byte(capabilityKey),
		RequireCapability: true,
		Now:               func() time.Time { return time.Unix(1_700_000_000, 0) },
		TemporalClient: &mockTemporalClient{executeFunc: func(context.Context, client.StartWorkflowOptions, interface{}, ...interface{}) (client.WorkflowRun, error) {
			called = true
			return &mockWorkflowRun{id: "unexpected"}, nil
		}},
	}
	_, err := server.ProcessFile(context.Background(), capabilityRequest())
	require.Error(t, err)
	assert.Equal(t, codes.PermissionDenied, status.Code(err))
	assert.False(t, called, "Temporal must not run without a capability")
}

func TestProcessFile_AcceptsMatchingCapabilityAndPropagatesProof(t *testing.T) {
	var captured interface{}
	req := capabilityRequest()
	server := &Server{
		CapabilitySecret:  []byte(capabilityKey),
		RequireCapability: true,
		Now:               func() time.Time { return time.Unix(1_700_000_000, 0) },
		TemporalClient: &mockTemporalClient{executeFunc: func(_ context.Context, _ client.StartWorkflowOptions, _ interface{}, args ...interface{}) (client.WorkflowRun, error) {
			require.Len(t, args, 1)
			captured = args[0]
			return &mockWorkflowRun{id: "accepted"}, nil
		}},
	}
	response, err := server.ProcessFile(capabilityContext(t, req, "u-1", "session-1"), req)
	require.NoError(t, err)
	assert.Equal(t, "accepted", response.JobId)
	job, ok := captured.(workflow.ProcessJob)
	require.True(t, ok)
	assert.NotEmpty(t, job.Capability)
	assert.Equal(t, req.SourceKey, job.SourceKey)
	assert.Equal(t, req.DestKey, job.DestKey)
}

func TestProcessFile_RejectsCapabilityIdentityMismatch(t *testing.T) {
	req := capabilityRequest()
	server := &Server{
		CapabilitySecret:  []byte(capabilityKey),
		RequireCapability: true,
		Now:               func() time.Time { return time.Unix(1_700_000_000, 0) },
		TemporalClient:    &mockTemporalClient{},
	}
	_, err := server.ProcessFile(capabilityContext(t, req, "u-1", "session-1"), func() *pb.ProcessFileRequest {
		copyReq := proto.Clone(req).(*pb.ProcessFileRequest)
		copyReq.DestKey = "users/u-1/other.png"
		return copyReq
	}())
	require.Error(t, err)
	assert.Equal(t, codes.PermissionDenied, status.Code(err))
}

func TestProcessFile_RejectsMissingCapabilityMetadata(t *testing.T) {
	req := capabilityRequest()
	ctx := pb.WithProcessingIdentity(context.Background(), pb.ProcessingIdentity{
		UserID: "u-1", SessionID: "session-1",
	})
	server := &Server{
		CapabilitySecret:  []byte(capabilityKey),
		RequireCapability: true,
		Now:               func() time.Time { return time.Unix(1_700_000_000, 0) },
		TemporalClient:    &mockTemporalClient{},
	}
	_, err := server.ProcessFile(ctx, req)
	require.Error(t, err)
	assert.Equal(t, codes.PermissionDenied, status.Code(err))
}

func TestProcessFile_RejectsInvalidCapabilitySignature(t *testing.T) {
	req := capabilityRequest()
	ctx := capabilityContext(t, req, "u-1", "session-1")
	ctx = metadata.NewIncomingContext(ctx, metadata.Pairs(
		strings.ToLower(pb.ProcessingCapabilityHeader), "not-a-capability",
	))
	server := &Server{
		CapabilitySecret:  []byte(capabilityKey),
		RequireCapability: true,
		TemporalClient:    &mockTemporalClient{},
	}
	_, err := server.ProcessFile(ctx, req)
	require.Error(t, err)
	assert.Equal(t, codes.PermissionDenied, status.Code(err))
}

func TestProcessFile_RejectsNonCanonicalCapabilityRequest(t *testing.T) {
	canonicalReq := capabilityRequest()
	ctx := capabilityContext(t, canonicalReq, "u-1", "session-1")
	nonCanonicalReq := proto.Clone(canonicalReq).(*pb.ProcessFileRequest)
	nonCanonicalReq.SourceKey = "users/u-1/./source.png"
	server := &Server{
		CapabilitySecret:  []byte(capabilityKey),
		RequireCapability: true,
		Now:               func() time.Time { return time.Unix(1_700_000_000, 0) },
		TemporalClient:    &mockTemporalClient{},
	}
	_, err := server.ProcessFile(ctx, nonCanonicalReq)
	require.Error(t, err)
	assert.Equal(t, codes.PermissionDenied, status.Code(err))
}

func TestProcessFile_UsesWallClockWhenNowHookIsNil(t *testing.T) {
	req := capabilityRequest()
	server := &Server{
		CapabilitySecret:  []byte(capabilityKey),
		RequireCapability: true,
		TemporalClient: &mockTemporalClient{executeFunc: func(context.Context, client.StartWorkflowOptions, interface{}, ...interface{}) (client.WorkflowRun, error) {
			return &mockWorkflowRun{id: "wall-clock-accepted"}, nil
		}},
	}
	response, err := server.ProcessFile(capabilityContextAt(t, req, "u-1", "session-1", time.Now().UTC()), req)
	require.NoError(t, err)
	assert.Equal(t, "wall-clock-accepted", response.JobId)
}
