package workflow

// Coverage tests (testing session 9) for FileProcessingWorkflow via the
// Temporal SDK's built-in testsuite (go.temporal.io/sdk/testsuite — no new
// dependency). The ResizeImageActivity is mocked via env.OnActivity so no
// MinIO connection is needed; the workflow body (versioning, ActivityOptions,
// retry policy wiring, result propagation) is what gets exercised.

import (
	"errors"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/mock"
	"github.com/stretchr/testify/require"
	"go.temporal.io/sdk/testsuite"
)

func newWorkflowEnv(t *testing.T) *testsuite.TestWorkflowEnvironment {
	t.Helper()
	ts := &testsuite.WorkflowTestSuite{}
	env := ts.NewTestWorkflowEnvironment()
	a := &FileActivities{}
	env.RegisterActivity(a.ResizeImageActivity)
	return env
}

func TestFileProcessingWorkflow_Success(t *testing.T) {
	env := newWorkflowEnv(t)
	a := &FileActivities{}
	env.OnActivity(a.ResizeImageActivity, mock.Anything, mock.Anything).Return(
		&ProcessResult{JobID: "job-1", Success: true, DestKey: "out/img.png"}, nil,
	)

	job := ProcessJob{
		ID:        "job-1",
		Type:      "resize",
		SourceKey: "in/img.png",
		DestKey:   "out/img.png",
		Options:   map[string]interface{}{"width": 100, "height": 100},
	}
	env.ExecuteWorkflow(FileProcessingWorkflow, job)

	require.True(t, env.IsWorkflowCompleted())
	require.NoError(t, env.GetWorkflowError())

	var result ProcessResult
	require.NoError(t, env.GetWorkflowResult(&result))
	assert.True(t, result.Success)
	assert.Equal(t, "job-1", result.JobID)
	assert.Equal(t, "out/img.png", result.DestKey)
}

func TestFileProcessingWorkflow_ActivityErrorPropagates(t *testing.T) {
	env := newWorkflowEnv(t)
	a := &FileActivities{}
	env.OnActivity(a.ResizeImageActivity, mock.Anything, mock.Anything).Return(
		nil, errors.New("resize exploded"),
	)

	job := ProcessJob{
		ID:        "job-err",
		Type:      "resize",
		SourceKey: "in/x.png",
		DestKey:   "out/x.png",
	}
	env.ExecuteWorkflow(FileProcessingWorkflow, job)

	require.True(t, env.IsWorkflowCompleted())
	err := env.GetWorkflowError()
	require.Error(t, err)
	assert.Contains(t, err.Error(), "resize exploded")
}
