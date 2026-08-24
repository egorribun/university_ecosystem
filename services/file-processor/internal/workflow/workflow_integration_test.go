//go:build integration

// Package workflow integration tests, gated behind the `integration` build tag.
//
// Per ADR-022, these tests use real MinIO containers via testcontainers-go to
// cover storage behavior the in-process fakes do not (real MinIO multipart,
// versioning, presigned URL TTLs). They are NOT part of the default `go test`
// run (which uses the existing unit tests). Run via:
//
//	make test-integration
//
// Or directly:
//
//	go test -tags integration -timeout 5m ./internal/workflow/...
//
// Docker daemon must be reachable.
package workflow

import (
	"bytes"
	"context"
	"image"
	"image/png"
	"testing"
	"time"

	"github.com/minio/minio-go/v7"
	"github.com/minio/minio-go/v7/pkg/credentials"
	"github.com/stretchr/testify/require"
	"github.com/testcontainers/testcontainers-go"
	tclog "github.com/testcontainers/testcontainers-go/log"
	tcminio "github.com/testcontainers/testcontainers-go/modules/minio"
)

// startMinIOContainer spins up a real MinIO server in a Docker container and
// returns a configured *minio.Client + bucket name + cleanup function. Mirrors
// the startNATSContainer pattern from ws-hub.
//
// Image tag is pinned to match the prod docker-compose (RELEASE.2025-09-07).
// Pinning ensures reproducibility — `latest` would drift between runs.
func startMinIOContainer(t *testing.T) (*minio.Client, string, func()) {
	t.Helper()
	ctx := context.Background()

	mc, err := tcminio.Run(ctx, "minio/minio:RELEASE.2025-09-07T16-13-09Z@sha256:14cea493d9a34af32f524e538b8346cf79f3321eff8e708c1e2960462bd8936e",
		testcontainers.WithLogger(tclog.TestLogger(t)),
	)
	if err != nil {
		t.Fatalf("minio container start: %v", err)
	}

	endpoint, err := mc.ConnectionString(ctx)
	if err != nil {
		_ = mc.Terminate(ctx) //nolint:errcheck // best-effort cleanup on test setup error
		t.Fatalf("minio connection string: %v", err)
	}

	// MinioContainer.Username / .Password are populated by testcontainers via
	// MINIO_ROOT_USER / MINIO_ROOT_PASSWORD env vars (defaults: minioadmin).
	client, err := minio.New(endpoint, &minio.Options{
		Creds:  credentials.NewStaticV4(mc.Username, mc.Password, ""),
		Secure: false,
	})
	if err != nil {
		_ = mc.Terminate(ctx) //nolint:errcheck // best-effort cleanup on test setup error
		t.Fatalf("minio client init: %v", err)
	}

	bucket := "test-bucket"
	if err := client.MakeBucket(ctx, bucket, minio.MakeBucketOptions{}); err != nil {
		_ = mc.Terminate(ctx) //nolint:errcheck // best-effort cleanup on test setup error
		t.Fatalf("create test bucket: %v", err)
	}

	cleanup := func() {
		_ = mc.Terminate(context.Background()) //nolint:errcheck // best-effort cleanup
	}
	return client, bucket, cleanup
}

// makeTestPNG returns the bytes of a valid 100×100 RGBA PNG for upload tests.
// Uses image.NewRGBA so the result decodes cleanly through the production
// downloadAndDecodeImage path.
func makeTestPNG(t *testing.T) []byte {
	t.Helper()
	img := image.NewRGBA(image.Rect(0, 0, 100, 100))
	var buf bytes.Buffer
	require.NoError(t, png.Encode(&buf, img))
	return buf.Bytes()
}

// TestIntegration_MinIOResizeImageHappyPath verifies the full activity path:
//
//	PutObject(source) → ResizeImageActivity → PutObject(dest) → GetObject(dest)
//
// Re-scoped from "MinIO + ClamAV" — ClamAV is not in production code (workflow.go:57
// has only "v2: reserved — add e.g. a ClamAV scan activity here" comment). This
// test validates the MinIO portion only; the ClamAV scan test is deferred per
// ADR-022 §Implementation Notes until the scan activity lands.
//
// Activity is exercised directly (not via Temporal) because the production
// production code path through ResizeImageActivity is what touches MinIO —
// Temporal orchestration is incidental and would add a 200 MB+ container pull
// for no additional coverage.
func TestIntegration_MinIOResizeImageHappyPath(t *testing.T) {
	mc, bucket, cleanup := startMinIOContainer(t)
	t.Cleanup(cleanup)

	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	t.Cleanup(cancel)

	// Upload source PNG via the same client the activity will use for GetObject.
	sourceKey := "input/test-100x100.png"
	pngBytes := makeTestPNG(t)
	_, err := mc.PutObject(ctx, bucket, sourceKey, bytes.NewReader(pngBytes), int64(len(pngBytes)),
		minio.PutObjectOptions{ContentType: "image/png"})
	require.NoError(t, err)

	// Build FileActivities pointing at the test MinIO client. This is the
	// production struct (workflow.go:109-112), so the test exercises the same
	// code path as the deployed Temporal worker.
	a := &FileActivities{
		MinioClient: mc,
		Bucket:      bucket,
	}

	job := ProcessJob{
		ID:        "test-job-1",
		Type:      "image_resize",
		SourceKey: sourceKey,
		DestKey:   "output/test-50x50.png",
		Options: map[string]interface{}{
			"width":  50,
			"height": 50,
		},
	}
	result, err := a.ResizeImageActivity(ctx, job)
	require.NoError(t, err, "ResizeImageActivity must succeed on a clean PNG round-trip")
	require.True(t, result.Success)
	require.Equal(t, "output/test-50x50.png", result.DestKey)
	require.Equal(t, "test-job-1", result.JobID)

	// Verify dest object exists in MinIO with correct content type.
	info, err := mc.StatObject(ctx, bucket, result.DestKey, minio.StatObjectOptions{})
	require.NoError(t, err)
	require.Greater(t, info.Size, int64(0), "dest object must have non-empty content")
	require.Equal(t, "image/png", info.ContentType)

	// Verify the dest is a valid 50×50 PNG. This bridges the activity-level
	// claim ("returned dest key") to the actual storage state.
	obj, err := mc.GetObject(ctx, bucket, result.DestKey, minio.GetObjectOptions{})
	require.NoError(t, err)
	defer func() { _ = obj.Close() }() //nolint:errcheck // best-effort body close
	decoded, _, err := image.Decode(obj)
	require.NoError(t, err)
	require.Equal(t, 50, decoded.Bounds().Dx(), "dest image width must be 50px")
	require.Equal(t, 50, decoded.Bounds().Dy(), "dest image height must be 50px")
}
