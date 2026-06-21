package workflow

// Default-run (no build tag) coverage tests for the MinIO-touching activity
// paths. The existing workflow_integration_test.go covers the same happy path
// but is gated behind `//go:build integration` (needs a real MinIO container via
// testcontainers + Docker), so it does NOT contribute to the default `go test`
// coverage the CI gate measures. These tests stand up a lightweight in-process
// fake-S3 HTTP server (httptest) and point a real *minio.Client at it, exercising
// downloadAndDecodeImage + ResizeImageActivity without Docker. (Testing session 16.)

import (
	"bytes"
	"context"
	"image"
	"image/png"
	"io"
	"net/http"
	"net/http/httptest"
	"net/url"
	"strconv"
	"testing"
	"time"

	"github.com/minio/minio-go/v7"
	"github.com/minio/minio-go/v7/pkg/credentials"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// makeRGBAPNG returns the bytes of a valid w×h RGBA PNG. Mirrors the integration
// test's makeTestPNG but lives in a non-build-tagged file so it compiles in the
// default test run.
func makeRGBAPNG(t *testing.T, w, h int) []byte {
	t.Helper()
	img := image.NewRGBA(image.Rect(0, 0, w, h))
	var buf bytes.Buffer
	require.NoError(t, png.Encode(&buf, img))
	return buf.Bytes()
}

// minioClientFor builds a path-style *minio.Client pointed at the given test
// server URL. Region is pinned so minio-go skips the GetBucketLocation probe.
func minioClientFor(t *testing.T, serverURL string) *minio.Client {
	t.Helper()
	u, err := url.Parse(serverURL)
	require.NoError(t, err)
	client, err := minio.New(u.Host, &minio.Options{
		Creds:  credentials.NewStaticV4("test", "test", ""),
		Secure: false,
		Region: "us-east-1",
	})
	require.NoError(t, err)
	return client
}

// fakeS3 serves a minimal subset of the S3 object API: GET returns getBody,
// PUT captures the uploaded bytes into putBody and replies with the configured
// putStatus. A nil getBody on GET yields a 404.
type fakeS3 struct {
	getBody   []byte
	putStatus int
	putBody   []byte
}

func (f *fakeS3) handler() http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		switch r.Method {
		case http.MethodGet, http.MethodHead:
			if f.getBody == nil {
				http.Error(w, "not found", http.StatusNotFound)
				return
			}
			w.Header().Set("Content-Type", "image/png")
			w.Header().Set("ETag", `"deadbeef"`)
			w.Header().Set("Last-Modified", time.Now().UTC().Format(http.TimeFormat))
			w.Header().Set("Accept-Ranges", "bytes")
			w.Header().Set("Content-Length", strconv.Itoa(len(f.getBody)))
			w.WriteHeader(http.StatusOK)
			if r.Method == http.MethodGet {
				_, _ = w.Write(f.getBody) //nolint:errcheck // test server best-effort
			}
		case http.MethodPut:
			b, _ := io.ReadAll(r.Body) //nolint:errcheck // test handler best-effort
			f.putBody = b
			status := f.putStatus
			if status == 0 {
				status = http.StatusOK
			}
			w.Header().Set("ETag", `"deadbeef"`)
			w.WriteHeader(status)
		default:
			w.WriteHeader(http.StatusOK)
		}
	}
}

func TestDownloadAndDecodeImage_HappyPath(t *testing.T) {
	fs := &fakeS3{getBody: makeRGBAPNG(t, 40, 30)}
	srv := httptest.NewServer(fs.handler())
	defer srv.Close()

	a := &FileActivities{MinioClient: minioClientFor(t, srv.URL), Bucket: "bucket"}
	// Pass a deadline so the deadliner (SetReadDeadline) branch is exercised.
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	img, format, err := a.downloadAndDecodeImage(ctx, "in/img.png")
	require.NoError(t, err)
	require.NotNil(t, img)
	assert.Equal(t, "png", format)
	assert.Equal(t, 40, img.Bounds().Dx())
	assert.Equal(t, 30, img.Bounds().Dy())
}

func TestDownloadAndDecodeImage_DecodeError(t *testing.T) {
	fs := &fakeS3{getBody: []byte("this is not an image")}
	srv := httptest.NewServer(fs.handler())
	defer srv.Close()

	a := &FileActivities{MinioClient: minioClientFor(t, srv.URL), Bucket: "bucket"}
	_, _, err := a.downloadAndDecodeImage(context.Background(), "in/garbage.png")
	require.Error(t, err)
	assert.Contains(t, err.Error(), "failed to decode image")
}

func TestResizeImageActivity_HappyPath(t *testing.T) {
	fs := &fakeS3{getBody: makeRGBAPNG(t, 100, 100)}
	srv := httptest.NewServer(fs.handler())
	defer srv.Close()

	a := &FileActivities{MinioClient: minioClientFor(t, srv.URL), Bucket: "bucket"}
	job := ProcessJob{
		ID:        "job-ok",
		Type:      "resize",
		SourceKey: "in/img.png",
		DestKey:   "out/img.png",
		Options:   map[string]interface{}{"width": 50, "height": 50},
	}
	res, err := a.ResizeImageActivity(context.Background(), job)
	require.NoError(t, err)
	require.True(t, res.Success)
	assert.Equal(t, "out/img.png", res.DestKey)
	assert.Equal(t, "job-ok", res.JobID)

	// minio-go uploads over plain HTTP using AWS streaming-signature chunk
	// encoding, so the captured PUT body is the chunk-wrapped payload, not raw
	// PNG bytes — asserting it is non-empty is the meaningful default-run check.
	// The clean PNG round-trip is verified by workflow_integration_test.go
	// against a real MinIO container (which de-chunks the upload).
	require.NotEmpty(t, fs.putBody)
}

func TestResizeImageActivity_BadSourceKey(t *testing.T) {
	// No server contact: sanitizeMinIOKey rejects before any MinIO call.
	a := &FileActivities{MinioClient: &minio.Client{}, Bucket: "bucket"}
	job := ProcessJob{ID: "j", SourceKey: "../../etc/passwd", DestKey: "out/x.png"}
	_, err := a.ResizeImageActivity(context.Background(), job)
	require.Error(t, err)
	assert.Contains(t, err.Error(), "path traversal")
}

func TestResizeImageActivity_BadDestKey(t *testing.T) {
	a := &FileActivities{MinioClient: &minio.Client{}, Bucket: "bucket"}
	job := ProcessJob{ID: "j", SourceKey: "in/ok.png", DestKey: "images/../../passwd"}
	_, err := a.ResizeImageActivity(context.Background(), job)
	require.Error(t, err)
	assert.Contains(t, err.Error(), "path traversal")
}

func TestResizeImageActivity_InvalidDimensions(t *testing.T) {
	fs := &fakeS3{getBody: makeRGBAPNG(t, 100, 100)}
	srv := httptest.NewServer(fs.handler())
	defer srv.Close()

	a := &FileActivities{MinioClient: minioClientFor(t, srv.URL), Bucket: "bucket"}
	job := ProcessJob{
		ID:        "j",
		SourceKey: "in/img.png",
		DestKey:   "out/img.png",
		Options:   map[string]interface{}{"width": "not-a-number"},
	}
	_, err := a.ResizeImageActivity(context.Background(), job)
	require.Error(t, err)
	assert.Contains(t, err.Error(), "invalid dimensions")
}

func TestResizeImageActivity_TooManyPixels(t *testing.T) {
	fs := &fakeS3{getBody: makeRGBAPNG(t, 100, 100)}
	srv := httptest.NewServer(fs.handler())
	defer srv.Close()

	a := &FileActivities{MinioClient: minioClientFor(t, srv.URL), Bucket: "bucket"}
	job := ProcessJob{
		ID:        "j",
		SourceKey: "in/img.png",
		DestKey:   "out/img.png",
		// Each dimension <= maxImageDimension (4096) but product > maxImagePixels (8M).
		Options: map[string]interface{}{"width": 4000, "height": 4000},
	}
	_, err := a.ResizeImageActivity(context.Background(), job)
	require.Error(t, err)
	assert.Contains(t, err.Error(), "exceed limit")
}

func TestResizeImageActivity_UploadError(t *testing.T) {
	fs := &fakeS3{getBody: makeRGBAPNG(t, 100, 100), putStatus: http.StatusInternalServerError}
	srv := httptest.NewServer(fs.handler())
	defer srv.Close()

	a := &FileActivities{MinioClient: minioClientFor(t, srv.URL), Bucket: "bucket"}
	job := ProcessJob{
		ID:        "j",
		SourceKey: "in/img.png",
		DestKey:   "out/img.png",
		Options:   map[string]interface{}{"width": 50, "height": 50},
	}
	_, err := a.ResizeImageActivity(context.Background(), job)
	require.Error(t, err)
}

func TestGetValidatedDimension_ParsesInt32AndInt64(t *testing.T) {
	r32, err := getValidatedDimension(map[string]interface{}{"width": int32(640)}, "width", 800)
	require.NoError(t, err)
	assert.Equal(t, 640, r32)

	r64, err := getValidatedDimension(map[string]interface{}{"height": int64(480)}, "height", 600)
	require.NoError(t, err)
	assert.Equal(t, 480, r64)
}

func TestGetValidatedDimension_ParsesValidNumericString(t *testing.T) {
	res, err := getValidatedDimension(map[string]interface{}{"width": "1280"}, "width", 800)
	require.NoError(t, err)
	assert.Equal(t, 1280, res)
}

func TestGetValidatedDimension_ErrorsOnUnsupportedType(t *testing.T) {
	// A bool value hits the switch default arm ("invalid type for ...").
	_, err := getValidatedDimension(map[string]interface{}{"width": true}, "width", 800)
	require.Error(t, err)
	assert.Contains(t, err.Error(), "invalid type")
}
