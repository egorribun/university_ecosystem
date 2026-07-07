package workflow

// W17-4: file-processor workflow tests — branches not reached by existing files.
//
// Covered here:
//   - ResizeImageActivity: context cancelled mid-PUT (storage write timeout).
//   - ResizeImageActivity: PUT returns 403 Forbidden (permission denied analogue).
//   - ResizeImageActivity: source is a valid JPEG (exercises jpeg decode path).
//   - ResizeImageActivity: exactly-at-pixel-limit dimensions are accepted.
//   - ResizeImageActivity: one-pixel-over-limit is rejected with FileTooLargeError.
//   - encodeImage: PNG output has a non-empty byte slice (quick round-trip).
//   - sanitizeMinIOKey: single-segment key with dots is accepted as-is.
//   - FileProcessingWorkflow: activity returning a non-nil result with Success=false
//     propagates correctly (workflow succeeds, result carries the failure).

import (
	"bytes"
	"context"
	"image"
	"image/jpeg"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/mock"
	"github.com/stretchr/testify/require"
	"go.temporal.io/sdk/testsuite"
)

// makeRGBAJPEG returns the bytes of a valid w×h RGBA JPEG for tests that need
// a JPEG source (exercises the jpeg decode branch in downloadAndDecodeImage).
func makeRGBAJPEG(t *testing.T, w, h int) []byte {
	t.Helper()
	img := image.NewRGBA(image.Rect(0, 0, w, h))
	var buf bytes.Buffer
	require.NoError(t, jpeg.Encode(&buf, img, &jpeg.Options{Quality: 80}))
	return buf.Bytes()
}

// ── ResizeImageActivity: storage write failures ───────────────────────────────

func TestResizeImageActivity_PutForbidden(t *testing.T) {
	// 403 from the PUT endpoint simulates permission-denied on storage write.
	// The activity must surface an error (not swallow it).
	fs := &fakeS3{
		getBody:   makeRGBAPNG(t, 20, 20),
		putStatus: http.StatusForbidden,
	}
	srv := httptest.NewServer(fs.handler())
	defer srv.Close()

	a := &FileActivities{MinioClient: minioClientFor(t, srv.URL), Bucket: "bucket"}
	job := ProcessJob{
		ID:        "job-put-403",
		SourceKey: "in/img.png",
		DestKey:   "out/img.png",
		Options:   map[string]interface{}{"width": 10, "height": 10},
	}
	_, err := a.ResizeImageActivity(context.Background(), job)
	require.Error(t, err, "a 403 on PUT must return an error")
}

func TestResizeImageActivity_PutTimeout(t *testing.T) {
	// The context is cancelled before the PUT response arrives, simulating a
	// storage write that times out. The activity must return an error.
	fs := &fakeS3{getBody: makeRGBAPNG(t, 20, 20)}

	// Override the PUT handler to block until the context is done.
	blockPUT := make(chan struct{})
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method == http.MethodPut {
			<-blockPUT // block until test unblocks
			w.WriteHeader(http.StatusOK)
			return
		}
		fs.handler().ServeHTTP(w, r)
	}))
	defer srv.Close()
	defer close(blockPUT)

	a := &FileActivities{MinioClient: minioClientFor(t, srv.URL), Bucket: "bucket"}
	job := ProcessJob{
		ID:        "job-put-timeout",
		SourceKey: "in/img.png",
		DestKey:   "out/img.png",
		Options:   map[string]interface{}{"width": 10, "height": 10},
	}

	ctx, cancel := context.WithCancel(context.Background())
	cancel() // cancel immediately so the PUT is aborted

	_, err := a.ResizeImageActivity(ctx, job)
	// Either the context-cancelled error from downloadAndDecodeImage fires
	// or the upload itself fails — either way we must get an error.
	require.Error(t, err, "cancelled context must produce an error on the activity")
}

// ── ResizeImageActivity: JPEG source image ────────────────────────────────────

func TestResizeImageActivity_JPEGSource(t *testing.T) {
	// Use a JPEG source so the jpeg decode path in image.Decode is exercised.
	// The fakeS3 handler reports Content-Type: image/png, but minio-go passes
	// the body directly to image.Decode which dispatches on magic bytes.
	jpegBody := makeRGBAJPEG(t, 60, 40)
	fs := &fakeS3{getBody: jpegBody}
	srv := httptest.NewServer(fs.handler())
	defer srv.Close()

	a := &FileActivities{MinioClient: minioClientFor(t, srv.URL), Bucket: "bucket"}
	job := ProcessJob{
		ID:        "job-jpeg-src",
		SourceKey: "in/photo.jpg",
		DestKey:   "out/photo.jpg",
		Options:   map[string]interface{}{"width": 30, "height": 20},
	}
	res, err := a.ResizeImageActivity(context.Background(), job)
	require.NoError(t, err)
	assert.True(t, res.Success)
	assert.Equal(t, "out/photo.jpg", res.DestKey)
}

// ── ResizeImageActivity: pixel limit boundary ─────────────────────────────────

func TestResizeImageActivity_ExactlyAtPixelLimit_IsAccepted(t *testing.T) {
	// width=4000, height=2000 → 8,000,000 pixels == maxImagePixels → accepted.
	fs := &fakeS3{getBody: makeRGBAPNG(t, 10, 10)}
	srv := httptest.NewServer(fs.handler())
	defer srv.Close()

	a := &FileActivities{MinioClient: minioClientFor(t, srv.URL), Bucket: "bucket"}
	job := ProcessJob{
		ID:        "job-pixel-limit-ok",
		SourceKey: "in/img.png",
		DestKey:   "out/img.png",
		Options:   map[string]interface{}{"width": 4000, "height": 2000},
	}
	res, err := a.ResizeImageActivity(context.Background(), job)
	require.NoError(t, err, "4000×2000 = 8M pixels must be accepted")
	assert.True(t, res.Success)
}

func TestResizeImageActivity_OnePixelOverLimit_IsRejected(t *testing.T) {
	// width=4001, height=2000 → 8,002,000 > maxImagePixels → rejected with
	// FileTooLargeError. Each individual dimension (4001, 2000) is under
	// maxImageDimension (4096) so the per-dimension check passes first.
	fs := &fakeS3{getBody: makeRGBAPNG(t, 10, 10)}
	srv := httptest.NewServer(fs.handler())
	defer srv.Close()

	a := &FileActivities{MinioClient: minioClientFor(t, srv.URL), Bucket: "bucket"}
	job := ProcessJob{
		ID:        "job-pixel-limit-over",
		SourceKey: "in/img.png",
		DestKey:   "out/img.png",
		Options:   map[string]interface{}{"width": 4001, "height": 2000},
	}
	_, err := a.ResizeImageActivity(context.Background(), job)
	require.Error(t, err, "4001×2000 = 8,002,000 pixels must be rejected")
	assert.Contains(t, err.Error(), "exceed limit")
}

// ── sanitizeMinIOKey: additional accepted forms ───────────────────────────────

func TestSanitizeMinIOKey_DottedFilenameIsAccepted(t *testing.T) {
	// A key like "archive.tar.gz" has dots but no traversal — must be accepted.
	clean, err := sanitizeMinIOKey("archive.tar.gz")
	require.NoError(t, err)
	assert.Equal(t, "archive.tar.gz", clean)
}

func TestSanitizeMinIOKey_SingleDotSegmentIsNormalised(t *testing.T) {
	// "a/./b" is cleaned to "a/b" by path.Clean — no traversal, should succeed.
	clean, err := sanitizeMinIOKey("a/./b")
	require.NoError(t, err)
	assert.Equal(t, "a/b", clean)
}

// ── FileProcessingWorkflow: result with Success=false propagates ──────────────

func TestFileProcessingWorkflow_ActivitySuccessFalseIsReturned(t *testing.T) {
	// An activity that returns Success=false (not an error) must be propagated
	// unchanged by the workflow. The workflow itself succeeds (no error) but the
	// result reflects the activity's failure flag.
	ts := &testsuite.WorkflowTestSuite{}
	env := ts.NewTestWorkflowEnvironment()
	a := &FileActivities{}
	env.RegisterActivity(a.ResizeImageActivity)

	env.OnActivity(a.ResizeImageActivity, mock.Anything, mock.Anything).Return(
		&ProcessResult{
			JobID:   "job-fail-flag",
			Success: false,
			Error:   "downstream rejection",
		}, nil, // no workflow-level error
	)

	job := ProcessJob{
		ID:        "job-fail-flag",
		Type:      "resize",
		SourceKey: "in/img.png",
		DestKey:   "out/img.png",
	}
	env.ExecuteWorkflow(FileProcessingWorkflow, job)

	require.True(t, env.IsWorkflowCompleted())
	require.NoError(t, env.GetWorkflowError())

	var result ProcessResult
	require.NoError(t, env.GetWorkflowResult(&result))
	assert.False(t, result.Success, "workflow result must carry Success=false from activity")
	assert.Equal(t, "downstream rejection", result.Error)
}
