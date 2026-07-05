package service

import (
	"context"
	"strings"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	pb "github.com/university-ecosystem/core/gen/go/file_processor/v1"
	"go.temporal.io/sdk/client"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

// TestGRPCPathTraversalRejection covers RZ-27-04 + RZ-26-04 at the
// gRPC boundary: validateProcessFileRequest rejects path traversal in
// sourceKey/destKey and rejects keys exceeding 1024 bytes BEFORE Temporal
// workflow start.
func TestGRPCPathTraversalRejection(t *testing.T) {
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

type mockWorkflowRun struct {
	client.WorkflowRun
	id string
}

func (m *mockWorkflowRun) GetID() string {
	return m.id
}

type mockTemporalClient struct {
	client.Client
	executeFunc func(ctx context.Context, options client.StartWorkflowOptions, workflow interface{}, args ...interface{}) (client.WorkflowRun, error)
}

func (m *mockTemporalClient) ExecuteWorkflow(ctx context.Context, options client.StartWorkflowOptions, workflow interface{}, args ...interface{}) (client.WorkflowRun, error) {
	if m.executeFunc != nil {
		return m.executeFunc(ctx, options, workflow, args...)
	}
	return &mockWorkflowRun{id: "default-run-id"}, nil
}

func TestProcessFile_Success(t *testing.T) {
	ctx := context.Background()

	mockClient := &mockTemporalClient{
		executeFunc: func(ctx context.Context, options client.StartWorkflowOptions, workflow interface{}, args ...interface{}) (client.WorkflowRun, error) {
			assert.Equal(t, "file-process-job123", options.ID)
			return &mockWorkflowRun{id: "run-456"}, nil
		},
	}

	s := &Server{
		TemporalClient: mockClient,
	}

	req := &pb.ProcessFileRequest{
		Id:        "job123",
		Type:      "image_resize",
		SourceKey: "input/image.png",
		DestKey:   "output/resized.png",
		Options:   map[string]string{"width": "300"},
	}

	resp, err := s.ProcessFile(ctx, req)
	require.NoError(t, err)
	assert.True(t, resp.Success)
	assert.Equal(t, "run-456", resp.JobId)
}

func TestProcessFile_TemporalError(t *testing.T) {
	ctx := context.Background()

	mockClient := &mockTemporalClient{
		executeFunc: func(ctx context.Context, options client.StartWorkflowOptions, workflow interface{}, args ...interface{}) (client.WorkflowRun, error) {
			return nil, assert.AnError
		},
	}

	s := &Server{
		TemporalClient: mockClient,
	}

	req := &pb.ProcessFileRequest{
		Id:        "job123",
		Type:      "image_resize",
		SourceKey: "input/image.png",
		DestKey:   "output/resized.png",
	}

	_, err := s.ProcessFile(ctx, req)
	require.Error(t, err)
	assert.Contains(t, err.Error(), "failed to start workflow")
}

func TestProcessFile_TemporalTimeout(t *testing.T) {
	ctx := context.Background()

	mockClient := &mockTemporalClient{
		executeFunc: func(ctx context.Context, options client.StartWorkflowOptions, workflow interface{}, args ...interface{}) (client.WorkflowRun, error) {
			return nil, context.DeadlineExceeded
		},
	}

	s := &Server{
		TemporalClient: mockClient,
	}

	req := &pb.ProcessFileRequest{
		Id:        "job123",
		Type:      "image_resize",
		SourceKey: "input/image.png",
		DestKey:   "output/resized.png",
	}

	_, err := s.ProcessFile(ctx, req)
	require.Error(t, err)
	st, ok := status.FromError(err)
	require.True(t, ok)
	assert.Equal(t, codes.DeadlineExceeded, st.Code())
	assert.Contains(t, st.Message(), "temporal unavailable")
}

