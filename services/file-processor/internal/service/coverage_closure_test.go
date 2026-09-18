package service

import (
	"context"
	"errors"
	"strings"
	"testing"
	"time"

	"github.com/stretchr/testify/require"
	pb "github.com/university-ecosystem/core/gen/go/file_processor/v1"
	"go.temporal.io/sdk/client"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/metadata"
	"google.golang.org/grpc/status"
)

type replayAdmissionError struct{}

func (replayAdmissionError) Consume(context.Context, string, time.Time) (bool, error) {
	return false, errors.New("replay registry unavailable")
}

func TestAuthorizeCapabilityRejectsNonCanonicalRequestRepresentation(t *testing.T) {
	req := capabilityRequest()
	tokenCtx := capabilityContext(t, req, "u-1", "session-1")
	req.SourceKey = "users/u-1/./source.png"
	server := &Server{
		CapabilitySecret:  []byte(capabilityKey),
		RequireCapability: true,
		Now:               func() time.Time { return time.Unix(1_700_000_000, 0) },
	}

	_, _, err := server.authorizeCapability(tokenCtx, req)
	require.Equal(t, codes.PermissionDenied, status.Code(err))
}

func TestProcessFileContinuesAfterReplayAdmissionFailure(t *testing.T) {
	req := capabilityRequest()
	server := &Server{
		CapabilitySecret:  []byte(capabilityKey),
		RequireCapability: true,
		ReplayGuard:       replayAdmissionError{},
		Now:               func() time.Time { return time.Unix(1_700_000_000, 0) },
		TemporalClient: &mockTemporalClient{executeFunc: func(context.Context, client.StartWorkflowOptions, interface{}, ...interface{}) (client.WorkflowRun, error) {
			return &mockWorkflowRun{id: "accepted-after-replay-outage"}, nil
		}},
	}

	resp, err := server.ProcessFile(capabilityContext(t, req, "u-1", "session-1"), req)
	require.NoError(t, err)
	require.Equal(t, "accepted-after-replay-outage", resp.JobId)
}

func TestNowUTCUsesProvidedClockAndWallClockFallback(t *testing.T) {
	provided := time.Date(2026, 9, 14, 12, 0, 0, 0, time.FixedZone("test", 3*60*60))
	require.Equal(t, provided.UTC(), nowUTC(func() time.Time { return provided }))
	before := time.Now().UTC()
	fallback := nowUTC(nil)
	after := time.Now().UTC()
	require.False(t, fallback.Before(before))
	require.False(t, fallback.After(after))
}

func TestAuthorizeCapabilityRequiresIdentity(t *testing.T) {
	req := capabilityRequest()
	now := time.Unix(1_700_000_000, 0)
	tokenCtx := metadata.NewIncomingContext(context.Background(), metadata.Pairs(
		strings.ToLower(pb.ProcessingCapabilityHeader), "token",
	))
	server := &Server{
		CapabilitySecret:  []byte(capabilityKey),
		RequireCapability: true,
		Now:               func() time.Time { return now },
	}
	_, _, err := server.authorizeCapability(tokenCtx, req)
	require.Equal(t, codes.PermissionDenied, status.Code(err))
}
