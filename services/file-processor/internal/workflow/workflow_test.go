package workflow

import (
	"context"
	"image"
	"image/color"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/minio/minio-go/v7"
	"github.com/minio/minio-go/v7/pkg/credentials"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"github.com/university-ecosystem/file-processor/internal/config"
)

func TestGetValidatedDimension_ReturnsDefaultForMissingKey(t *testing.T) {
	options := map[string]interface{}{}

	result, err := getValidatedDimension(options, "width", 800)

	assert.NoError(t, err)
	assert.Equal(t, 800, result)
}

func TestGetValidatedDimension_ReturnsDefaultForNilOptions(t *testing.T) {
	var options map[string]interface{}

	result, err := getValidatedDimension(options, "height", 600)

	assert.NoError(t, err)
	assert.Equal(t, 600, result)
}

func TestGetValidatedDimension_ParsesIntValue(t *testing.T) {
	options := map[string]interface{}{
		"width": 1024,
	}

	result, err := getValidatedDimension(options, "width", 800)

	assert.NoError(t, err)
	assert.Equal(t, 1024, result)
}

func TestGetValidatedDimension_ParsesFloat64Value(t *testing.T) {
	options := map[string]interface{}{
		"height": float64(768),
	}

	result, err := getValidatedDimension(options, "height", 600)

	assert.NoError(t, err)
	assert.Equal(t, 768, result)
}

func TestGetValidatedDimension_ErrorsOnInvalidType(t *testing.T) {
	options := map[string]interface{}{
		"width": "not-a-number",
	}

	_, err := getValidatedDimension(options, "width", 800)

	assert.Error(t, err)
	assert.Contains(t, err.Error(), "invalid string value")
}

func TestGetValidatedDimension_ErrorsOnNonPositive(t *testing.T) {
	options := map[string]interface{}{
		"width": 0,
	}

	_, err := getValidatedDimension(options, "width", 800)
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "must be positive")

	options["width"] = -100
	_, err = getValidatedDimension(options, "width", 800)
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "must be positive")
}

func TestGetValidatedDimension_ErrorsOnExceedingLimit(t *testing.T) {
	options := map[string]interface{}{
		"width": maxImageDimension + 1,
	}

	_, err := getValidatedDimension(options, "width", 800)

	assert.Error(t, err)
	assert.Contains(t, err.Error(), "exceeds maximum allowed dimension")
}

func TestProcessJob_StructFieldsAreAccessible(t *testing.T) {
	job := ProcessJob{
		ID:          "job-123",
		Type:        "resize",
		SourceKey:   "source/image.jpg",
		DestKey:     "dest/image.jpg",
		Options:     map[string]interface{}{"width": 100},
		CallbackURL: "http://callback.example.com",
	}

	assert.Equal(t, "job-123", job.ID)
	assert.Equal(t, "resize", job.Type)
	assert.Equal(t, "source/image.jpg", job.SourceKey)
	assert.Equal(t, "dest/image.jpg", job.DestKey)
	assert.Equal(t, 100, job.Options["width"])
	assert.Equal(t, "http://callback.example.com", job.CallbackURL)
}

func TestProcessResult_StructFieldsAreAccessible(t *testing.T) {
	result := ProcessResult{
		JobID:    "job-456",
		Success:  true,
		DestKey:  "result/image.jpg",
		Error:    "",
		Duration: 1500,
	}

	assert.Equal(t, "job-456", result.JobID)
	assert.True(t, result.Success)
	assert.Equal(t, "result/image.jpg", result.DestKey)
	assert.Empty(t, result.Error)
	assert.Equal(t, int64(1500), result.Duration)
}

func TestSanitizeMinIOKey_ValidKeys(t *testing.T) {
	cases := []string{
		"images/profile.jpg",
		"documents/report.pdf",
		"archive.zip",
	}
	for _, tc := range cases {
		t.Run(tc, func(t *testing.T) {
			res, err := sanitizeMinIOKey(tc)
			assert.NoError(t, err)
			assert.Equal(t, tc, res)
		})
	}
}

func TestSanitizeMinIOKey_Errors(t *testing.T) {
	cases := []struct {
		name string
		key  string
	}{
		{"empty key", ""},
		{"path traversal parent", "../etc/passwd"},
		{"path traversal middle", "images/../../passwd"},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			_, err := sanitizeMinIOKey(tc.key)
			assert.Error(t, err)
		})
	}
}

func TestEncodeImage_Formats(t *testing.T) {
	img := image.NewRGBA(image.Rect(0, 0, 10, 10))

	cases := []struct {
		format     string
		wantFormat string
	}{
		{"jpeg", "jpeg"},
		{"jpg", "jpg"},
		{"png", "png"},
		{"webp", "png"},            // transcode webp -> png
		{"gif", "jpeg"},            // fallback to jpeg
		{"unknown-format", "jpeg"}, // fallback to jpeg
	}

	for _, tc := range cases {
		t.Run(tc.format, func(t *testing.T) {
			buf, format, err := encodeImage(img, tc.format)
			assert.NoError(t, err)
			assert.NotEmpty(t, buf.Bytes())
			assert.Equal(t, tc.wantFormat, format)
		})
	}
}

func TestNewFileActivities_NilClient(t *testing.T) {
	cfg := &config.Config{MinioBucket: "test-bucket"}
	_, err := NewFileActivities(cfg, nil)
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "must not be nil")
}

func TestNewFileActivities_Success(t *testing.T) {
	cfg := &config.Config{MinioBucket: "test-bucket"}
	dummyClient, err := minio.New("localhost:9000", &minio.Options{
		Creds: credentials.NewStaticV4("access", "secret", ""),
	})
	require.NoError(t, err)

	activities, err := NewFileActivities(cfg, dummyClient)
	require.NoError(t, err)
	assert.Equal(t, "test-bucket", activities.Bucket)
	assert.Equal(t, dummyClient, activities.MinioClient)
}

func TestBuildMinIOClient(t *testing.T) {
	cfg := &config.Config{
		MinioEndpoint:  "localhost:9000",
		MinioAccessKey: "access",
		MinioSecretKey: "secret",
		MinioSecure:    false,
	}

	client, err := BuildMinIOClient(cfg)
	require.NoError(t, err)
	assert.NotNil(t, client)
}

func TestBuildMinIOClient_Error(t *testing.T) {
	cfg := &config.Config{
		MinioEndpoint: "  invalid-endpoint-with-spaces  ",
	}
	_, err := BuildMinIOClient(cfg)
	assert.Error(t, err)
}

func decodePanic(r io.Reader) (image.Image, error) {
	panic("mock panic in image decode")
}
func decodeConfigPanic(r io.Reader) (image.Config, error) {
	return image.Config{ColorModel: color.RGBAModel, Width: 10, Height: 10}, nil
}

func TestFileActivities_DownloadAndDecodeImage_PanicRecovery(t *testing.T) {
	// Register custom panic-format decoder
	image.RegisterFormat("panic-format", "magic", decodePanic, decodeConfigPanic)

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "image/panic-format")
		w.Header().Set("Last-Modified", time.Now().UTC().Format(http.TimeFormat))
		w.Header().Set("Content-Length", "5")
		w.Header().Set("ETag", `"123456"`)
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte("magic"))
	}))
	defer server.Close()

	endpoint := strings.TrimPrefix(server.URL, "http://")
	minioClient, err := minio.New(endpoint, &minio.Options{
		Creds:  credentials.NewStaticV4("access", "secret", ""),
		Secure: false,
		Region: "us-east-1",
	})
	require.NoError(t, err)

	cfg := &config.Config{MinioBucket: "test-bucket"}
	activities, err := NewFileActivities(cfg, minioClient)
	require.NoError(t, err)

	_, _, err = activities.downloadAndDecodeImage(context.Background(), "test.panic")
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "panic during image decode")
}

func TestFileActivities_DownloadAndDecodeImage_ContextCancelled(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "image/png")
		w.Header().Set("Last-Modified", time.Now().UTC().Format(http.TimeFormat))
		w.Header().Set("Content-Length", "5")
		w.Header().Set("ETag", `"123456"`)
		w.WriteHeader(http.StatusOK)
		time.Sleep(100 * time.Millisecond)
		_, _ = w.Write([]byte("magic"))
	}))
	defer server.Close()

	endpoint := strings.TrimPrefix(server.URL, "http://")
	minioClient, err := minio.New(endpoint, &minio.Options{
		Creds:  credentials.NewStaticV4("access", "secret", ""),
		Secure: false,
		Region: "us-east-1",
	})
	require.NoError(t, err)

	cfg := &config.Config{MinioBucket: "test-bucket"}
	activities, err := NewFileActivities(cfg, minioClient)
	require.NoError(t, err)

	ctx, cancel := context.WithCancel(context.Background())
	cancel() // cancel immediately

	_, _, err = activities.downloadAndDecodeImage(ctx, "test.png")
	assert.Error(t, err)
}
