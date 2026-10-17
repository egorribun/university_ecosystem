package workflow

import (
	"net/http"
	"net/http/httptest"
	"sync/atomic"
	"testing"

	"github.com/stretchr/testify/require"
	"go.temporal.io/sdk/temporal"
	"go.temporal.io/sdk/testsuite"
)

func TestFileProcessingWorkflowDoesNotRetryActualInvalidDimensions(t *testing.T) {
	var downloads atomic.Int32
	storage := &fakeS3{getBody: makeRGBAPNG(t, 1, 1)}
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method == http.MethodGet {
			downloads.Add(1)
		}
		storage.handler()(w, r)
	}))
	t.Cleanup(server.Close)
	activities := &FileActivities{MinioClient: minioClientFor(t, server.URL), Bucket: "bucket"}
	suite := &testsuite.WorkflowTestSuite{}
	env := suite.NewTestWorkflowEnvironment()
	env.RegisterActivity(activities.ResizeImageActivity)
	env.ExecuteWorkflow(FileProcessingWorkflow, ProcessJob{
		ID: "invalid-dimensions", Type: "image_resize", SourceKey: "in/source.png", DestKey: "out/result.png",
		Options: map[string]interface{}{"width": "invalid"},
	})

	require.True(t, env.IsWorkflowCompleted())
	var applicationErr *temporal.ApplicationError
	require.ErrorAs(t, env.GetWorkflowError(), &applicationErr)
	require.Equal(t, "InvalidInputError", applicationErr.Type())
	require.EqualValues(t, 1, downloads.Load(), "deterministic invalid dimensions must not retry the real activity")
	require.Empty(t, storage.putBody)
}
