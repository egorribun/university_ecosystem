package graphql

// Coverage tests (testing session 9) for the GraphQL resolver: ProcessFile
// happy/error paths, sanitizeKey traversal guards and the sub-resolver
// accessors. Mirrors the manual fakeTemporalClient idiom from
// internal/service/server_test.go (it is unexported there, so duplicated).

import (
	"context"
	"strings"
	"testing"

	gql "github.com/graph-gophers/graphql-go"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"github.com/university-ecosystem/file-processor/internal/workflow"
	"go.temporal.io/sdk/client"
)

type fakeWorkflowRun struct {
	client.WorkflowRun
	id string
}

func (f *fakeWorkflowRun) GetID() string { return f.id }

type fakeTemporalClient struct {
	client.Client
	executeFunc func(ctx context.Context, options client.StartWorkflowOptions, wf interface{}, args ...interface{}) (client.WorkflowRun, error)
}

func (f *fakeTemporalClient) ExecuteWorkflow(ctx context.Context, options client.StartWorkflowOptions, wf interface{}, args ...interface{}) (client.WorkflowRun, error) {
	if f.executeFunc != nil {
		return f.executeFunc(ctx, options, wf, args...)
	}
	return &fakeWorkflowRun{id: "noop"}, nil
}

func int32Ptr(v int32) *int32 { return &v }

// ---------------------------------------------------------------------------
// sanitizeKey
// ---------------------------------------------------------------------------

func TestSanitizeKey(t *testing.T) {
	cases := []struct {
		name    string
		input   string
		want    string
		wantErr bool
	}{
		{"clean path", "uploads/file.png", "uploads/file.png", false},
		{"leading slash collapsed", "/uploads/a.png", "uploads/a.png", false},
		{"traversal rejected", "../etc/passwd", "", true},
		{"embedded traversal rejected", "uploads/../../etc/passwd", "", true},
		{"empty rejected", "", "", true},
		{"root rejected", "/", "", true},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			got, err := sanitizeKey(tc.input)
			if tc.wantErr {
				require.Error(t, err)
				return
			}
			require.NoError(t, err)
			assert.Equal(t, tc.want, got)
		})
	}
}

// ---------------------------------------------------------------------------
// Resolver.File
// ---------------------------------------------------------------------------

func TestFile_ResolvesSanitizedURL(t *testing.T) {
	r := &Resolver{MinioBucket: "files"}
	fr := r.File(struct{ ID gql.ID }{ID: gql.ID("uploads/photo.png")})
	require.NotNil(t, fr)
	assert.Equal(t, gql.ID("uploads/photo.png"), fr.ID())
	assert.Contains(t, fr.URL(), "/files/")
	assert.NotNil(t, fr.Size())
	assert.NotNil(t, fr.Type())
}

func TestFile_TraversalFallsBackToInvalidPath(t *testing.T) {
	r := &Resolver{MinioBucket: "files"}
	fr := r.File(struct{ ID gql.ID }{ID: gql.ID("../../etc/passwd")})
	require.NotNil(t, fr)
	assert.Equal(t, gql.ID("invalid-path"), fr.ID())
}

func TestHealth_ReturnsOK(t *testing.T) {
	r := &Resolver{}
	assert.Equal(t, "OK", r.Health())
}

// ---------------------------------------------------------------------------
// Resolver.ProcessFile
// ---------------------------------------------------------------------------

func TestProcessFile_SuccessThreadsOptionsAndPrefix(t *testing.T) {
	var capturedOptions client.StartWorkflowOptions
	var capturedJob workflow.ProcessJob
	fake := &fakeTemporalClient{
		executeFunc: func(_ context.Context, options client.StartWorkflowOptions, _ interface{}, args ...interface{}) (client.WorkflowRun, error) {
			capturedOptions = options
			require.Len(t, args, 1)
			capturedJob = args[0].(workflow.ProcessJob)
			return &fakeWorkflowRun{id: "wf-run-1"}, nil
		},
	}
	r := &Resolver{TemporalClient: fake, MinioBucket: "files"}

	input := ProcessFileInput{
		Type:      "image",
		SourceKey: "src/a.png",
		DestKey:   "dst/a.png",
		Width:     int32Ptr(640),
		Height:    int32Ptr(480),
	}
	jobRes, err := r.ProcessFile(context.Background(), struct{ Input ProcessFileInput }{Input: input})
	require.NoError(t, err)
	require.NotNil(t, jobRes)

	assert.Equal(t, gql.ID("wf-run-1"), jobRes.JobID())
	assert.Equal(t, "STARTED", jobRes.Status())
	assert.True(t, strings.HasPrefix(capturedOptions.ID, "graphql-"))
	assert.Equal(t, "FILE_PROCESSING_TASK_QUEUE", capturedOptions.TaskQueue)
	assert.Equal(t, 640, capturedJob.Options["width"])
	assert.Equal(t, 480, capturedJob.Options["height"])
	assert.Equal(t, "src/a.png", capturedJob.SourceKey)
	assert.Equal(t, "dst/a.png", capturedJob.DestKey)
}

func TestProcessFile_InvalidSourceKeyRejected(t *testing.T) {
	r := &Resolver{TemporalClient: &fakeTemporalClient{}, MinioBucket: "files"}
	_, err := r.ProcessFile(context.Background(), struct{ Input ProcessFileInput }{
		Input: ProcessFileInput{Type: "image", SourceKey: "../etc/passwd", DestKey: "dst/ok.png"},
	})
	require.Error(t, err)
	assert.Contains(t, err.Error(), "invalid source key")
}

func TestProcessFile_InvalidDestKeyRejected(t *testing.T) {
	r := &Resolver{TemporalClient: &fakeTemporalClient{}, MinioBucket: "files"}
	_, err := r.ProcessFile(context.Background(), struct{ Input ProcessFileInput }{
		Input: ProcessFileInput{Type: "image", SourceKey: "src/ok.png", DestKey: "../../boom"},
	})
	require.Error(t, err)
	assert.Contains(t, err.Error(), "invalid destination key")
}

func TestProcessFile_ExecuteWorkflowErrorPropagates(t *testing.T) {
	fake := &fakeTemporalClient{
		executeFunc: func(_ context.Context, _ client.StartWorkflowOptions, _ interface{}, _ ...interface{}) (client.WorkflowRun, error) {
			return nil, assert.AnError
		},
	}
	r := &Resolver{TemporalClient: fake, MinioBucket: "files"}
	_, err := r.ProcessFile(context.Background(), struct{ Input ProcessFileInput }{
		Input: ProcessFileInput{Type: "image", SourceKey: "src/ok.png", DestKey: "dst/ok.png"},
	})
	require.Error(t, err)
}
