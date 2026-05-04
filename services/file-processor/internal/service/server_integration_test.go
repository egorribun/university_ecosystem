//go:build integration

// Package service integration tests, gated behind //go:build integration.
//
// Per ADR-022 — exercises the gRPC validation boundary (validateProcessFileRequest
// at server.go:44-76) which rejects path traversal and oversized keys BEFORE the
// Temporal workflow is started. Validation fires entirely in-process, so this
// test does not need a real gRPC listener — `s.ProcessFile(ctx, req)` is called
// directly with TemporalClient: nil (never reached when validation rejects).
package service

import (
	"context"
	"strings"
	"testing"

	"github.com/stretchr/testify/require"
	pb "github.com/university-ecosystem/core/gen/go/file_processor/v1"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

// TestIntegration_GRPCPathTraversalRejection covers RZ-27-04 + RZ-26-04 at the
// gRPC boundary: validateProcessFileRequest rejects path traversal in
// sourceKey/destKey and rejects keys exceeding 1024 bytes BEFORE Temporal
// workflow start. This guards against:
//   - Object-storage path traversal via crafted keys (RZ-27-04)
//   - Temporal workflow history bloat from oversized keys (RZ-26-04)
//
// All cases must result in codes.InvalidArgument; TemporalClient: nil is safe
// because validation rejects every test case before reaching ExecuteWorkflow
// at server.go:110.
func TestIntegration_GRPCPathTraversalRejection(t *testing.T) {
	s := &Server{TemporalClient: nil}
	ctx := context.Background()

	cases := []struct {
		name         string
		sourceKey    string
		destKey      string
		wantCode     codes.Code
		wantContains string
	}{
		{
			name:         "path_traversal_in_source",
			sourceKey:    "../etc/passwd",
			destKey:      "output/x.png",
			wantCode:     codes.InvalidArgument,
			wantContains: "path traversal",
		},
		{
			name:         "path_traversal_in_dest",
			sourceKey:    "input/x.png",
			destKey:      "../../secret",
			wantCode:     codes.InvalidArgument,
			wantContains: "path traversal",
		},
		{
			name:         "slash_dotdot_in_middle",
			sourceKey:    "input/../../../etc/passwd",
			destKey:      "out",
			wantCode:     codes.InvalidArgument,
			wantContains: "path traversal",
		},
		{
			name:         "oversized_source_key",
			sourceKey:    strings.Repeat("a", 1025),
			destKey:      "output/x",
			wantCode:     codes.InvalidArgument,
			wantContains: "exceeds",
		},
		{
			name:         "oversized_dest_key",
			sourceKey:    "input/x",
			destKey:      strings.Repeat("b", 2048),
			wantCode:     codes.InvalidArgument,
			wantContains: "exceeds",
		},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			req := &pb.ProcessFileRequest{
				Id:        "test-" + tc.name,
				Type:      "image_resize",
				SourceKey: tc.sourceKey,
				DestKey:   tc.destKey,
				Options:   map[string]string{"width": "100", "height": "100"},
			}
			_, err := s.ProcessFile(ctx, req)
			require.Error(t, err, "request must be rejected")
			st, ok := status.FromError(err)
			require.True(t, ok, "error must be a gRPC status, got %T: %v", err, err)
			require.Equal(t, tc.wantCode, st.Code(), "expected gRPC code mismatch")
			require.Contains(t, st.Message(), tc.wantContains,
				"expected error to contain %q, got %q", tc.wantContains, st.Message())
		})
	}
}
