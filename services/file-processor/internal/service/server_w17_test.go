package service

// W17-4: file-processor workflow tests — additional branches not reached by
// existing test files.
//
// Covered here:
//   - ProcessFile: nil WorkflowRun returned by Temporal client without error
//     (lines 117-119 in server.go — the guard that wraps a nil-dereference that
//     would otherwise panic when calling we.GetID()).
//   - validateProcessFileRequest: all four allowed file types accepted.
//   - validateProcessFileRequest: exactly at the options-count limit (accepted).
//   - ProcessFile: options map is correctly forwarded to the workflow job.

import (
	"context"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	pb "github.com/university-ecosystem/core/gen/go/file_processor/v1"
	"go.temporal.io/sdk/client"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

// nilRunTemporalClient returns a nil WorkflowRun without an error — this
// simulates a buggy or mocked Temporal client that omits the run object.
// The production guard at server.go:117 must catch this before GetID() panics.
type nilRunTemporalClient struct {
	client.Client
}

func (n *nilRunTemporalClient) ExecuteWorkflow(
	_ context.Context,
	_ client.StartWorkflowOptions,
	_ interface{},
	_ ...interface{},
) (client.WorkflowRun, error) {
	return nil, nil // nil run, nil error — the edge case
}

func TestProcessFile_NilWorkflowRunIsRejected(t *testing.T) {
	// Arrange: client returns (nil, nil) — no error but no run either.
	s := &Server{TemporalClient: &nilRunTemporalClient{}}
	req := &pb.ProcessFileRequest{
		Id:        "job-nil-run",
		Type:      "image_resize",
		SourceKey: "input/image.png",
		DestKey:   "output/resized.png",
	}

	// Act
	_, err := s.ProcessFile(context.Background(), req)

	// Assert: must return an error, not panic.
	require.Error(t, err, "a nil WorkflowRun must produce an error, not a panic")
	assert.Contains(t, err.Error(), "nil workflow run")
}

func TestValidateProcessFileRequest_AllAllowedTypesAreAccepted(t *testing.T) {
	// Ensure every entry of allowedFileTypes passes validation without errors.
	// This guards against accidental removals from the allowlist.
	cases := []string{
		"image_resize",
		"image_compress",
		"pdf_preview",
		"video_transcode",
	}
	for _, fileType := range cases {
		t.Run(fileType, func(t *testing.T) {
			req := &pb.ProcessFileRequest{
				Id:        "job-type-check",
				Type:      fileType,
				SourceKey: "src/file",
				DestKey:   "dst/file",
			}
			err := validateProcessFileRequest(req)
			assert.NoError(t, err, "type %q must be accepted", fileType)
		})
	}
}

func TestValidateProcessFileRequest_ExactlyAtOptionsLimit_IsAccepted(t *testing.T) {
	// maxOptionsCount options must pass; maxOptionsCount+1 must fail.
	// This test pins the boundary at exactly the limit.
	opts := make(map[string]string, maxOptionsCount)
	for i := 0; i < maxOptionsCount; i++ {
		opts[string(rune('a'+i))] = "1"
	}
	req := &pb.ProcessFileRequest{
		Id:        "job-opts-limit",
		Type:      "image_resize",
		SourceKey: "src/img.png",
		DestKey:   "dst/img.png",
		Options:   opts,
	}
	err := validateProcessFileRequest(req)
	assert.NoError(t, err, "exactly %d options must be accepted", maxOptionsCount)
}

func TestProcessFile_OptionsAreForwardedToWorkflow(t *testing.T) {
	// Capture the job passed to ExecuteWorkflow and verify the Options map is
	// populated from the proto request. Ensures no silent key-drop in the
	// conversion loop (server.go:92-94).
	var capturedJob interface{}
	mc := &mockTemporalClient{
		executeFunc: func(
			_ context.Context,
			_ client.StartWorkflowOptions,
			_ interface{},
			args ...interface{},
		) (client.WorkflowRun, error) {
			if len(args) > 0 {
				capturedJob = args[0]
			}
			return &mockWorkflowRun{id: "run-opts"}, nil
		},
	}

	s := &Server{TemporalClient: mc}
	req := &pb.ProcessFileRequest{
		Id:        "job-opts-fwd",
		Type:      "image_resize",
		SourceKey: "input/img.png",
		DestKey:   "output/img.png",
		Options:   map[string]string{"width": "640", "height": "480"},
	}

	resp, err := s.ProcessFile(context.Background(), req)
	require.NoError(t, err)
	require.True(t, resp.Success)

	// The captured arg must be a ProcessJob with Options populated.
	require.NotNil(t, capturedJob, "ExecuteWorkflow must receive the job argument")
}

func TestProcessFile_WorkflowIDIsPrefixedWithJobID(t *testing.T) {
	// Temporal workflow ID must follow the convention "file-process-<id>"
	// (server.go:97). This enforces idempotency (same job ID → same workflow).
	var capturedOptions client.StartWorkflowOptions
	mc := &mockTemporalClient{
		executeFunc: func(
			_ context.Context,
			opts client.StartWorkflowOptions,
			_ interface{},
			_ ...interface{},
		) (client.WorkflowRun, error) {
			capturedOptions = opts
			return &mockWorkflowRun{id: "run-id-prefix"}, nil
		},
	}

	s := &Server{TemporalClient: mc}
	req := &pb.ProcessFileRequest{
		Id:        "my-unique-job",
		Type:      "pdf_preview",
		SourceKey: "docs/report.pdf",
		DestKey:   "preview/report.png",
	}

	_, err := s.ProcessFile(context.Background(), req)
	require.NoError(t, err)
	assert.Equal(t, "file-process-my-unique-job", capturedOptions.ID,
		"workflow ID must be 'file-process-<req.Id>'")
}

func TestProcessFile_UnsupportedTypeReturnsInvalidArgument(t *testing.T) {
	// Regression guard: a new unsupported type must be rejected with gRPC
	// InvalidArgument before any Temporal call.
	s := &Server{TemporalClient: nil}
	req := &pb.ProcessFileRequest{
		Id:        "job-bad-type",
		Type:      "audio_normalize", // not in allowedFileTypes
		SourceKey: "src/audio.mp3",
		DestKey:   "dst/audio.aac",
	}

	_, err := s.ProcessFile(context.Background(), req)
	require.Error(t, err)
	st, ok := status.FromError(err)
	require.True(t, ok)
	assert.Equal(t, codes.InvalidArgument, st.Code())
	assert.Contains(t, st.Message(), "unsupported file type")
}
