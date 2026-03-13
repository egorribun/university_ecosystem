package workflow

import (
	"bytes"
	"context"
	"fmt"
	"image"
	"image/jpeg"
	"image/png"
	"time"

	"github.com/minio/minio-go/v7"
	"github.com/minio/minio-go/v7/pkg/credentials"
	"github.com/university-ecosystem/file-processor/internal/config"
	"go.temporal.io/sdk/temporal"
	"go.temporal.io/sdk/workflow"
	"golang.org/x/image/draw"
)

// ProcessJob represents a file processing job
// Shared between workflow and other packages, could be in a 'types' or 'domain' package.
// For now, keeping it here and exporting.
type ProcessJob struct {
	ID          string                 `json:"id"`
	Type        string                 `json:"type"` // resize, thumbnail, optimize
	SourceKey   string                 `json:"source_key"`
	DestKey     string                 `json:"dest_key"`
	Options     map[string]interface{} `json:"options"`
	CallbackURL string                 `json:"callback_url,omitempty"`
}

// ProcessResult represents the result of a processing job
type ProcessResult struct {
	JobID    string `json:"job_id"`
	Success  bool   `json:"success"`
	DestKey  string `json:"dest_key,omitempty"`
	Error    string `json:"error,omitempty"`
	Duration int64  `json:"duration_ms"`
}

// FileProcessingWorkflow orchestrates the file processing
func FileProcessingWorkflow(ctx workflow.Context, job ProcessJob) (*ProcessResult, error) {
	// MOD-W5-05: Explicit exponential back-off retry policy.
	// NonRetryableErrorTypes prevents wasting attempts on deterministic errors
	// (bad dimensions, oversized images) that will never succeed.
	options := workflow.ActivityOptions{
		StartToCloseTimeout: time.Minute * 5,
		RetryPolicy: &temporal.RetryPolicy{
			InitialInterval:        time.Second,
			BackoffCoefficient:     2.0,
			MaximumInterval:        time.Minute,
			MaximumAttempts:        5,
			NonRetryableErrorTypes: []string{"InvalidInputError", "FileTooLargeError"},
		},
	}

	ctx = workflow.WithActivityOptions(ctx, options)

	var result ProcessResult

	// Execute Activity
	var a *FileActivities
	err := workflow.ExecuteActivity(ctx, a.ResizeImageActivity, job).Get(ctx, &result)

	if err != nil {
		return nil, err
	}

	return &result, nil
}

// FileActivities holds the file processing activities
type FileActivities struct {
	MinioClient *minio.Client
	Bucket      string
}

// NewFileActivities creates a new activity struct with dependencies
func NewFileActivities(cfg *config.Config) *FileActivities {
	// Initialize MinIO client
	client, err := minio.New(cfg.MinioEndpoint, &minio.Options{
		Creds:  credentials.NewStaticV4(cfg.MinioAccessKey, cfg.MinioSecretKey, ""),
		Secure: cfg.MinioSecure,
	})
	if err != nil {
		panic(err) // Worker will retry initialization if panic occurs on startup
	}

	return &FileActivities{
		MinioClient: client,
		Bucket:      cfg.MinioBucket,
	}
}

const (
	// maxImageDimension prevents OOM by limiting any single dimension of processed images.
	maxImageDimension = 4096
	// maxImagePixels caps total pixel count to bound RGBA memory allocation.
	// PERF-W5-01: A 4096×4096 RGBA image = 64 MB. Under 20 concurrent workflows that
	// becomes 1.28 GB. 8 MP (≈ 3264×2448) keeps peak per-workflow at ~32 MB RGBA.
	maxImagePixels = 8_000_000
)

// ResizeImageActivity performs the image resizing
func (a *FileActivities) ResizeImageActivity(ctx context.Context, job ProcessJob) (*ProcessResult, error) {
	result := &ProcessResult{
		JobID: job.ID,
	}

	// Download from MinIO
	obj, err := a.MinioClient.GetObject(ctx, a.Bucket, job.SourceKey, minio.GetObjectOptions{})
	if err != nil {
		return nil, err
	}
	defer func() {
		if closeErr := obj.Close(); closeErr != nil {
			_ = closeErr
		}
	}()

	// Decode image
	img, format, err := image.Decode(obj)
	if err != nil {
		return nil, fmt.Errorf("failed to decode image: %w", err)
	}

	// Get target dimensions
	width, errW := getValidatedDimension(job.Options, "width", 800)
	height, errH := getValidatedDimension(job.Options, "height", 600)

	if errW != nil || errH != nil {
		return nil, temporal.NewApplicationError("invalid dimensions", "InvalidInput", errW, errH)
	}
	// PERF-W5-01: Reject images whose total pixel count would exceed the memory budget.
	// Enforced after per-dimension validation so the error message is specific.
	if width*height > maxImagePixels {
		return nil, temporal.NewApplicationError(
			fmt.Sprintf("total pixels %d exceed limit %d", width*height, maxImagePixels),
			"FileTooLargeError",
		)
	}

	// Resize
	dst := image.NewRGBA(image.Rect(0, 0, width, height))
	draw.CatmullRom.Scale(dst, dst.Bounds(), img, img.Bounds(), draw.Over, nil)

	// Encode
	var buf bytes.Buffer
	switch format {
	case "jpeg", "jpg":
		if err := jpeg.Encode(&buf, dst, &jpeg.Options{Quality: 85}); err != nil {
			return nil, err
		}
	case "png":
		if err := png.Encode(&buf, dst); err != nil {
			return nil, err
		}
	default:
		// Default to JPEG if unknown output
		if err := jpeg.Encode(&buf, dst, &jpeg.Options{Quality: 85}); err != nil {
			return nil, err
		}
	}

	// Upload result
	_, err = a.MinioClient.PutObject(ctx, a.Bucket, job.DestKey, &buf, int64(buf.Len()),
		minio.PutObjectOptions{ContentType: "image/" + format})

	if err != nil {
		return nil, err
	}

	result.Success = true
	result.DestKey = job.DestKey
	return result, nil
}

func getValidatedDimension(options map[string]interface{}, key string, defaultValue int) (int, error) {
	val := defaultValue
	if raw, ok := options[key]; ok {
		switch v := raw.(type) {
		case int:
			val = v
		case float64:
			val = int(v)
		case int32:
			val = int(v)
		case int64:
			val = int(v)
		default:
			return 0, fmt.Errorf("invalid type for %s", key)
		}
	}

	if val <= 0 {
		return 0, fmt.Errorf("%s must be positive", key)
	}
	if val > maxImageDimension {
		return 0, fmt.Errorf("%s exceeds maximum allowed dimension (%d)", key, maxImageDimension)
	}
	return val, nil
}
