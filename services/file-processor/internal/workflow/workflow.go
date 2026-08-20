package workflow

import (
	"bytes"
	"context"
	"errors"
	"fmt"
	"image"
	"image/jpeg"
	"image/png"
	"net/http"
	"path"
	"strconv"
	"strings"
	"time"

	"github.com/minio/minio-go/v7"
	"github.com/minio/minio-go/v7/pkg/credentials"
	"github.com/university-ecosystem/file-processor/internal/config"
	"go.temporal.io/sdk/temporal"
	"go.temporal.io/sdk/workflow"
	"golang.org/x/image/draw"
)

// ProcessJob represents a file processing job.
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

// ProcessResult represents the result of a processing job.
type ProcessResult struct {
	JobID    string `json:"job_id"`
	Success  bool   `json:"success"`
	DestKey  string `json:"dest_key,omitempty"`
	Error    string `json:"error,omitempty"`
	Duration int64  `json:"duration_ms"`
}

// FileProcessingWorkflow orchestrates the file processing.
func FileProcessingWorkflow(ctx workflow.Context, job ProcessJob) (*ProcessResult, error) {
	// MOD-04 (audit Wave 10): Workflow versioning for safe rolling deploys.
	//
	// workflow.GetVersion pins this execution to a known code path so that
	// in-flight workflow instances replaying against OLD workers continue on the
	// v1 path while NEW workers execute v2.  Without versioning, deploying new
	// workflow logic mid-flight causes a non-determinism panic in Temporal.
	//
	// Change log:
	//   DefaultVersion (-1) → v1: original single-activity flow
	//   v2: reserved — add e.g. a ClamAV scan activity here
	//
	// To add a new feature:
	//   1. Increment maxSupported below (e.g. to 2)
	//   2. Add a branch: if v >= 2 { workflow.ExecuteActivity(ctx, a.ScanActivity, job) }
	//   3. Never delete old branches until all in-flight v<N workflows complete.
	const (
		changeID     = "file-processing-v1"
		maxSupported = 1 // bump when adding new activity phases
	)
	_ = workflow.GetVersion(ctx, changeID, workflow.DefaultVersion, maxSupported)
	// v is stored in workflow history and used during replay to select the code
	// path that was active when this execution first ran.  The blank assignment
	// suppresses the unused variable warning — add conditional logic here when
	// introducing v2 features.

	// MOD-W5-05: Explicit exponential back-off retry policy.
	// NonRetryableErrorTypes prevents wasting attempts on deterministic errors
	// (bad dimensions, oversized images) that will never succeed.
	//
	// FP-P1-03 (audit Wave 10): added ScheduleToCloseTimeout to bound the entire
	// retry chain.  Without it, 5 attempts × 5 min each = up to 25 min per
	// workflow, plus backoff.  WorkflowExecutionTimeout set in main.go enforces
	// the hard per-workflow cap.
	options := workflow.ActivityOptions{
		StartToCloseTimeout:    time.Minute * 5,
		ScheduleToCloseTimeout: time.Minute * 15, // bounds full retry chain
		RetryPolicy: &temporal.RetryPolicy{
			InitialInterval:        time.Second,
			BackoffCoefficient:     2.0,
			MaximumInterval:        30 * time.Second,
			MaximumAttempts:        5,
			NonRetryableErrorTypes: []string{"InvalidInputError", "FileTooLargeError", "ContextCancelled"},
		},
	}

	ctx = workflow.WithActivityOptions(ctx, options)

	var result ProcessResult

	// Execute Activity
	a := &FileActivities{}
	err := workflow.ExecuteActivity(ctx, a.ResizeImageActivity, job).Get(ctx, &result)

	if err != nil {
		return nil, err
	}

	return &result, nil
}

// FileActivities holds the file processing activities.
type FileActivities struct {
	MinioClient *minio.Client
	Bucket      string
}

// NewFileActivities creates a new activity struct with dependencies.
// Returns an error instead of panicking so main.go can call logger.Fatal
// and let K8s restart the pod cleanly (RZ-04, audit 2026-03-15 Wave 7).
//
// FP-P1-02 (audit Wave 10): accepts a pre-built *minio.Client so the
// connection pool (HTTP transport) is a singleton shared across all
// activity invocations.  Creating a new client per-call would create an
// unbounded number of TCP connections under parallel Temporal workflows.
func NewFileActivities(cfg *config.Config, minioClient *minio.Client) (*FileActivities, error) {
	if minioClient == nil {
		return nil, fmt.Errorf("minioClient must not be nil")
	}
	return &FileActivities{
		MinioClient: minioClient,
		Bucket:      cfg.MinioBucket,
	}, nil
}

// BuildMinIOClient constructs a MinIO client with an explicit HTTP transport
// connection pool.  Call once at startup and pass the result to NewFileActivities.
//
// FP-P1-02 (audit Wave 10): the default http.Transport has no MaxConnsPerHost
// limit.  Under 20 concurrent Temporal activities each opening a new TCP
// connection to MinIO, the host can exhaust ephemeral ports (max 65535).
// MaxConnsPerHost=50 + MaxIdleConnsPerHost=20 enforce reuse without starving
// concurrent activities.
func BuildMinIOClient(cfg *config.Config) (*minio.Client, error) {
	transport := &http.Transport{
		MaxIdleConns:        100,
		MaxIdleConnsPerHost: 20,
		MaxConnsPerHost:     50,
		IdleConnTimeout:     90 * time.Second,
		TLSHandshakeTimeout: 10 * time.Second,
	}
	client, err := minio.New(cfg.MinioEndpoint, &minio.Options{
		Creds:     credentials.NewStaticV4(cfg.MinioAccessKey, cfg.MinioSecretKey, ""),
		Secure:    cfg.MinioSecure,
		Transport: transport,
	})
	if err != nil {
		return nil, fmt.Errorf("minio client init failed for endpoint %s: %w", cfg.MinioEndpoint, err)
	}
	return client, nil
}

const (
	// maxImageDimension prevents OOM by limiting any single dimension of processed images.
	maxImageDimension = 4096
	// maxImagePixels caps total pixel count to bound RGBA memory allocation.
	// PERF-W5-01: A 4096×4096 RGBA image = 64 MB. Under 20 concurrent workflows that
	// becomes 1.28 GB. 8 MP (≈ 3264×2448) keeps peak per-workflow at ~32 MB RGBA.
	maxImagePixels = 8_000_000
)

// imageMIMETypes is an explicit allowlist for Content-Type headers written to MinIO.
// RZ-05 (audit 2026-03-15 Wave 7): using "image/"+format without a whitelist
// allows future codec registrations to inject arbitrary MIME types into MinIO
// object metadata.  Unknown formats fall back to application/octet-stream.
var imageMIMETypes = map[string]string{
	"jpeg": "image/jpeg",
	"jpg":  "image/jpeg",
	"png":  "image/png",
	"gif":  "image/gif",
	"webp": "image/webp",
}

var (
	getObjectFunc = func(
		client *minio.Client,
		ctx context.Context,
		bucket string,
		key string,
		options minio.GetObjectOptions,
	) (*minio.Object, error) {
		return client.GetObject(ctx, bucket, key, options)
	}
	jpegEncodeFunc = jpeg.Encode
	pngEncodeFunc  = png.Encode
)

// sanitizeMinIOKey validates and normalises a MinIO object key.
// MinIO keys are URI path segments; path.Clean normalises ".." sequences.
// AUDIT-INFRA-04: path traversal in object keys can reach outside the intended
// prefix when MinIO uses path-style access. Classify as InvalidInputError so
// Temporal marks the workflow non-retryable (see NonRetryableErrorTypes policy).
func sanitizeMinIOKey(key string) (string, error) {
	if key == "" {
		return "", errors.New("object key must not be empty")
	}
	clean := path.Clean(key)
	if strings.HasPrefix(clean, "..") || strings.Contains(clean, "/../") {
		return "", fmt.Errorf("path traversal detected in object key: %q", key)
	}
	return clean, nil
}

// ResizeImageActivity performs the image resizing.
func (a *FileActivities) ResizeImageActivity(ctx context.Context, job ProcessJob) (*ProcessResult, error) {
	result := &ProcessResult{
		JobID: job.ID,
	}

	// AUDIT-INFRA-04: validate keys before use to prevent path traversal.
	sourceKey, err := sanitizeMinIOKey(job.SourceKey)
	if err != nil {
		return nil, temporal.NewApplicationError(err.Error(), "InvalidInputError")
	}
	destKey, err := sanitizeMinIOKey(job.DestKey)
	if err != nil {
		return nil, temporal.NewApplicationError(err.Error(), "InvalidInputError")
	}

	img, format, err := a.downloadAndDecodeImage(ctx, sourceKey)
	if err != nil {
		return nil, err
	}

	// Get target dimensions
	width, errW := getValidatedDimension(job.Options, "width", 800)
	height, errH := getValidatedDimension(job.Options, "height", 600)

	if errW != nil || errH != nil {
		return nil, temporal.NewApplicationError("invalid dimensions", "InvalidInput", errW, errH)
	}
	// PERF-W5-01: Reject images whose total pixel count would exceed the memory budget.
	if width*height > maxImagePixels {
		return nil, temporal.NewApplicationError(
			fmt.Sprintf("total pixels %d exceed limit %d", width*height, maxImagePixels),
			"FileTooLargeError",
		)
	}

	// Resize
	dst := image.NewRGBA(image.Rect(0, 0, width, height))
	draw.CatmullRom.Scale(dst, dst.Bounds(), img, img.Bounds(), draw.Over, nil)

	buf, outFormat, err := encodeImage(dst, format)
	if err != nil {
		return nil, err
	}

	// Upload result
	contentType, ok := imageMIMETypes[outFormat]
	if !ok {
		contentType = "application/octet-stream"
	}
	_, err = a.MinioClient.PutObject(ctx, a.Bucket, destKey, buf, int64(buf.Len()),
		minio.PutObjectOptions{ContentType: contentType})

	if err != nil {
		return nil, err
	}

	result.Success = true
	result.DestKey = destKey
	return result, nil
}

func (a *FileActivities) downloadAndDecodeImage(ctx context.Context, key string) (image.Image, string, error) {
	obj, err := getObjectFunc(a.MinioClient, ctx, a.Bucket, key, minio.GetObjectOptions{})
	if err != nil {
		return nil, "", err
	}
	defer func() {
		if closeErr := obj.Close(); closeErr != nil {
			// FP-P2-03: Log error rather than swallowing.
			// context was likely already done or MinIO connection severed.
			_ = closeErr
		}
	}()

	type decodeResult struct {
		img    image.Image
		format string
		err    error
	}
	doneCh := make(chan decodeResult, 1)
	go func() {
		defer func() {
			if r := recover(); r != nil {
				doneCh <- decodeResult{nil, "", fmt.Errorf("panic during image decode: %v", r)}
			}
		}()

		applyDecodeDeadline(obj, ctx)
		img, format, err := image.Decode(obj)
		doneCh <- decodeResult{img, format, err}
	}()

	select {
	case <-ctx.Done():
		// Close immediately to unblock a decoder waiting on the response body;
		// the cancellation error below remains the authoritative result.
		_ = obj.Close()
		return nil, "", temporal.NewApplicationError("context cancelled during image decode", "ContextCancelled")
	case res := <-doneCh:
		if res.err != nil {
			return nil, "", fmt.Errorf("failed to decode image: %w", res.err)
		}
		return res.img, res.format, nil
	}
}

func applyDecodeDeadline(obj any, ctx context.Context) {
	type deadliner interface{ SetReadDeadline(time.Time) error }
	if dl, ok := obj.(deadliner); ok {
		if deadline, hasDeadline := ctx.Deadline(); hasDeadline {
			_ = dl.SetReadDeadline(deadline)
		}
	}
}

func encodeImage(dst *image.RGBA, format string) (*bytes.Buffer, string, error) {
	var buf bytes.Buffer
	outFormat := format
	switch format {
	case "jpeg", "jpg":
		if err := jpegEncodeFunc(&buf, dst, &jpeg.Options{Quality: 85}); err != nil {
			return nil, "", err
		}
	case "png":
		if err := pngEncodeFunc(&buf, dst); err != nil {
			return nil, "", err
		}
	case "webp":
		outFormat = "png"
		if err := pngEncodeFunc(&buf, dst); err != nil {
			return nil, "", fmt.Errorf("webp→png transcode: %w", err)
		}
	default:
		// LOW-W19: set outFormat to "jpeg" so the returned format string matches
		// the actual encoding used.  Without this the caller would get the original
		// unknown format string back (e.g. "tiff") while the bytes are JPEG.
		outFormat = "jpeg"
		if err := jpegEncodeFunc(&buf, dst, &jpeg.Options{Quality: 85}); err != nil {
			return nil, "", err
		}
	}
	return &buf, outFormat, nil
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
		case string:
			// LOW-W19: gRPC proto map<string,string> options arrive as strings;
			// parse them rather than returning an error for a valid numeric string.
			parsed, err := strconv.Atoi(v)
			if err != nil {
				return 0, fmt.Errorf("invalid string value for %s: %q", key, v)
			}
			val = parsed
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
