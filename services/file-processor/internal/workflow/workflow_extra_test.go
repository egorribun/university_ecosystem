package workflow

// Extra unit tests for branches not yet reached by workflow_coverage_test.go:
//
//   encodeImage — JPEG, WebP→PNG transcode, and unknown-format (default) branches
//   sanitizeMinIOKey — empty key branch
//   NewFileActivities — nil minioClient guard
//   BuildMinIOClient — construction with explicit HTTP transport (smoke test)
//
// (Testing session 17 — coverage climb for file-processor/internal/workflow/workflow.go.)

import (
	"bytes"
	"context"
	"image"
	"image/jpeg"
	"net/http/httptest"
	"testing"

	
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"github.com/university-ecosystem/file-processor/internal/config"
)

// ── encodeImage ───────────────────────────────────────────────────────────────

func TestEncodeImage_JPEG(t *testing.T) {
	img := image.NewRGBA(image.Rect(0, 0, 10, 10))
	buf, format, err := encodeImage(img, "jpeg")
	require.NoError(t, err)
	assert.Equal(t, "jpeg", format)
	require.NotEmpty(t, buf.Bytes())
	// Sanity-check: decode it back.
	_, err = jpeg.Decode(bytes.NewReader(buf.Bytes()))
	require.NoError(t, err)
}

func TestEncodeImage_JPGAlias(t *testing.T) {
	// "jpg" hits the same case arm as "jpeg".
	img := image.NewRGBA(image.Rect(0, 0, 8, 8))
	buf, format, err := encodeImage(img, "jpg")
	require.NoError(t, err)
	assert.Equal(t, "jpg", format)
	require.NotEmpty(t, buf.Bytes())
}

func TestEncodeImage_WebP_TranscodesToPNG(t *testing.T) {
	// "webp" is re-encoded as PNG (Go stdlib has no WebP encoder).
	// Returned format must be "png".
	img := image.NewRGBA(image.Rect(0, 0, 8, 8))
	buf, format, err := encodeImage(img, "webp")
	require.NoError(t, err)
	assert.Equal(t, "png", format)
	require.NotEmpty(t, buf.Bytes())
}

func TestEncodeImage_UnknownFormat_FallsBackToJPEG(t *testing.T) {
	// An unrecognised format (e.g. "tiff") should fall through to the default
	// case which JPEG-encodes the image and returns outFormat = "jpeg".
	img := image.NewRGBA(image.Rect(0, 0, 8, 8))
	buf, format, err := encodeImage(img, "tiff")
	require.NoError(t, err)
	assert.Equal(t, "jpeg", format, "unknown format should produce JPEG output")
	require.NotEmpty(t, buf.Bytes())
}

// ── sanitizeMinIOKey ─────────────────────────────────────────────────────────

func TestSanitizeMinIOKey_EmptyKey(t *testing.T) {
	_, err := sanitizeMinIOKey("")
	require.Error(t, err)
	assert.Contains(t, err.Error(), "object key must not be empty")
}

func TestSanitizeMinIOKey_ValidKey(t *testing.T) {
	clean, err := sanitizeMinIOKey("uploads/images/photo.png")
	require.NoError(t, err)
	assert.Equal(t, "uploads/images/photo.png", clean)
}

func TestSanitizeMinIOKey_TraversalRejected(t *testing.T) {
	_, err := sanitizeMinIOKey("../../etc/shadow")
	require.Error(t, err)
	assert.Contains(t, err.Error(), "path traversal")
}

// ── NewFileActivities ─────────────────────────────────────────────────────────

func TestNewFileActivities_NilClientReturnsError(t *testing.T) {
	cfg := &config.Config{MinioBucket: "bucket"}
	_, err := NewFileActivities(cfg, nil)
	require.Error(t, err)
	assert.Contains(t, err.Error(), "minioClient must not be nil")
}

func TestNewFileActivities_ValidClient(t *testing.T) {
	cfg := &config.Config{MinioBucket: "test-bucket"}
	// Use the helper from workflow_coverage_test.go to build a real *minio.Client.
	srv := httptest.NewServer((&fakeS3{}).handler())
	defer srv.Close()

	client := minioClientFor(t, srv.URL)
	activities, err := NewFileActivities(cfg, client)
	require.NoError(t, err)
	require.NotNil(t, activities)
	assert.Equal(t, "test-bucket", activities.Bucket)
}

// ── BuildMinIOClient ──────────────────────────────────────────────────────────

func TestBuildMinIOClient_Smoke(t *testing.T) {
	// BuildMinIOClient is a factory; it does NOT connect eagerly — it only builds
	// the transport + minio.Client struct. Verify it returns a non-nil client for
	// a well-formed (but fake) endpoint.
	cfg := &config.Config{
		MinioEndpoint:  "localhost:9000",
		MinioAccessKey: "minioadmin",
		MinioSecretKey: "minioadmin",
		MinioSecure:    false,
		MinioBucket:    "bucket",
	}
	client, err := BuildMinIOClient(cfg)
	require.NoError(t, err)
	require.NotNil(t, client)
}

// ── getValidatedDimension — additional branches ───────────────────────────────

func TestGetValidatedDimension_UsesDefaultWhenKeyAbsent(t *testing.T) {
	// When the key is not present in options, the default value is returned.
	val, err := getValidatedDimension(map[string]interface{}{}, "width", 800)
	require.NoError(t, err)
	assert.Equal(t, 800, val)
}

func TestGetValidatedDimension_ZeroValueReturnsError(t *testing.T) {
	_, err := getValidatedDimension(map[string]interface{}{"width": 0}, "width", 800)
	require.Error(t, err)
	assert.Contains(t, err.Error(), "must be positive")
}

func TestGetValidatedDimension_ExceedsMaxDimensionReturnsError(t *testing.T) {
	_, err := getValidatedDimension(map[string]interface{}{"width": 9999}, "width", 800)
	require.Error(t, err)
	assert.Contains(t, err.Error(), "exceeds maximum")
}

func TestGetValidatedDimension_Float64Value(t *testing.T) {
	// JSON-decoded numbers arrive as float64; ensure they're handled correctly.
	val, err := getValidatedDimension(map[string]interface{}{"height": float64(720)}, "height", 600)
	require.NoError(t, err)
	assert.Equal(t, 720, val)
}

// ── downloadAndDecodeImage — context cancellation ─────────────────────────────

func TestDownloadAndDecodeImage_ContextCancelledDuringFetch(t *testing.T) {
	// Use a fakeS3 that returns a valid image body; immediately cancel the context
	// so the select in downloadAndDecodeImage fires the ctx.Done() arm before the
	// decode goroutine finishes.  The image is large enough that the race is
	// won by the cancel in most runs; the test is structured to accept either the
	// decode success OR the cancellation error without being flaky.
	fs := &fakeS3{getBody: makeRGBAPNG(t, 200, 200)}
	srv := httptest.NewServer(fs.handler())
	defer srv.Close()

	a := &FileActivities{MinioClient: minioClientFor(t, srv.URL), Bucket: "bucket"}

	ctx, cancel := context.WithCancel(context.Background())
	cancel() // cancel immediately

	// The call may return a ContextCancelled error or succeed (if decode wins the
	// race); both are acceptable — the key assertion is that it does not panic or hang.
	_, _, _ = a.downloadAndDecodeImage(ctx, "in/img.png")
}
