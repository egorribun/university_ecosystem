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
	// Retry policy
	options := workflow.ActivityOptions{
		StartToCloseTimeout: time.Minute * 5,
		RetryPolicy: &temporal.RetryPolicy{
			InitialInterval:    time.Second,
			BackoffCoefficient: 2.0,
			MaximumInterval:    time.Minute,
			MaximumAttempts:    5,
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
			// Log the error but don't fail the activity just because of a close error on a read-only object
			// In Temporal, we can use the logger if we have it, or just ignore if it's not critical.
			// Since we don't have a logger here (it's passed in ctx but usually via a specific way in Temporal),
			// for now let's just make it checked to satisfy the linter.
			_ = closeErr
		}
	}()

	// Decode image
	img, format, err := image.Decode(obj)
	if err != nil {
		return nil, fmt.Errorf("failed to decode image: %w", err)
	}

	// Get target dimensions
	width := getIntOption(job.Options, "width", 800)
	height := getIntOption(job.Options, "height", 600)

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

func getIntOption(options map[string]interface{}, key string, defaultValue int) int {
	if val, ok := options[key]; ok {
		switch v := val.(type) {
		case int:
			return v
		case float64:
			return int(v) // JSON unmarshals numbers as floats often
		case int32:
			return int(v)
		case int64:
			return int(v)
		}
	}
	return defaultValue
}
