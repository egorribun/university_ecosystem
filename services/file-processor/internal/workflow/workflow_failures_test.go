package workflow

import (
	"context"
	"errors"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/mock"
	"github.com/stretchr/testify/require"
	enumspb "go.temporal.io/api/enums/v1"
	"go.temporal.io/sdk/temporal"
	"go.temporal.io/sdk/testsuite"
)

func TestFileProcessingWorkflow_RetriesOnRetryableError(t *testing.T) {
	ts := &testsuite.WorkflowTestSuite{}
	env := ts.NewTestWorkflowEnvironment()
	a := &FileActivities{}

	// Count number of times activity is called
	callCount := 0
	env.OnActivity(a.ResizeImageActivity, mock.Anything, mock.Anything).Return(
		func(ctx context.Context, job ProcessJob) (*ProcessResult, error) {
			callCount++
			if callCount < 3 {
				// Return a retryable error
				return nil, errors.New("temporary network error")
			}
			return &ProcessResult{JobID: "job-retry", Success: true, DestKey: "out/retry.png"}, nil
		},
	)

	job := ProcessJob{
		ID:        "job-retry",
		Type:      "resize",
		SourceKey: "in/retry.png",
		DestKey:   "out/retry.png",
	}
	env.ExecuteWorkflow(FileProcessingWorkflow, job)

	require.True(t, env.IsWorkflowCompleted())
	require.NoError(t, env.GetWorkflowError())
	assert.Equal(t, 3, callCount, "Workflow should retry until success or max attempts")

	var result ProcessResult
	require.NoError(t, env.GetWorkflowResult(&result))
	assert.True(t, result.Success)
}

func TestFileProcessingWorkflow_FailsImmediatelyOnNonRetryableError(t *testing.T) {
	ts := &testsuite.WorkflowTestSuite{}
	env := ts.NewTestWorkflowEnvironment()
	a := &FileActivities{}

	callCount := 0
	// Non-retryable error type registered in workflow.go: "InvalidInputError"
	nonRetryableErr := temporal.NewApplicationError("invalid dimensions", "InvalidInputError")

	env.OnActivity(a.ResizeImageActivity, mock.Anything, mock.Anything).Return(
		func(ctx context.Context, job ProcessJob) (*ProcessResult, error) {
			callCount++
			return nil, nonRetryableErr
		},
	)

	job := ProcessJob{
		ID:        "job-non-retryable",
		Type:      "resize",
		SourceKey: "in/bad.png",
		DestKey:   "out/bad.png",
	}
	env.ExecuteWorkflow(FileProcessingWorkflow, job)

	require.True(t, env.IsWorkflowCompleted())
	err := env.GetWorkflowError()
	require.Error(t, err)
	assert.Equal(t, 1, callCount, "Workflow should fail immediately on non-retryable error")
	assert.Contains(t, err.Error(), "invalid dimensions")
}

func TestFileProcessingWorkflow_ReachesMaxAttemptsAndFails(t *testing.T) {
	ts := &testsuite.WorkflowTestSuite{}
	env := ts.NewTestWorkflowEnvironment()
	a := &FileActivities{}

	callCount := 0
	env.OnActivity(a.ResizeImageActivity, mock.Anything, mock.Anything).Return(
		func(ctx context.Context, job ProcessJob) (*ProcessResult, error) {
			callCount++
			return nil, errors.New("persistent error")
		},
	)

	job := ProcessJob{
		ID:        "job-max-attempts",
		Type:      "resize",
		SourceKey: "in/persist.png",
		DestKey:   "out/persist.png",
	}
	env.ExecuteWorkflow(FileProcessingWorkflow, job)

	require.True(t, env.IsWorkflowCompleted())
	err := env.GetWorkflowError()
	require.Error(t, err)
	// MaximumAttempts is configured as 5 in workflow.go
	assert.Equal(t, 5, callCount, "Workflow should attempt exactly MaximumAttempts before failing")
}

func TestFileProcessingWorkflow_ActivityTimeoutRetries(t *testing.T) {
	ts := &testsuite.WorkflowTestSuite{}
	env := ts.NewTestWorkflowEnvironment()
	a := &FileActivities{}

	callCount := 0
	timeoutErr := temporal.NewTimeoutError(enumspb.TIMEOUT_TYPE_START_TO_CLOSE, errors.New("activity timeout"))

	env.OnActivity(a.ResizeImageActivity, mock.Anything, mock.Anything).Return(
		func(ctx context.Context, job ProcessJob) (*ProcessResult, error) {
			callCount++
			return nil, timeoutErr
		},
	)

	job := ProcessJob{
		ID:        "job-timeout",
		Type:      "resize",
		SourceKey: "in/timeout.png",
		DestKey:   "out/timeout.png",
	}
	env.ExecuteWorkflow(FileProcessingWorkflow, job)

	require.True(t, env.IsWorkflowCompleted())
	err := env.GetWorkflowError()
	require.Error(t, err)
	assert.Equal(t, 5, callCount, "Workflow should retry activity on timeout up to max attempts")
}
