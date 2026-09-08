package workflow

import (
	"context"
	"errors"
	"testing"

	"github.com/minio/minio-go/v7"
	"github.com/stretchr/testify/require"
	"go.temporal.io/sdk/temporal"
)

func TestSanitizeMinIOKeyRejectsWindowsDriveKeys(t *testing.T) {
	driveKeys := []struct {
		name string
		key  string
	}{
		{name: "backslash_absolute", key: `C:\Windows\system32\drivers\etc\hosts`},
		{name: "slash_absolute", key: "C:/Windows/system32/drivers/etc/hosts"},
		{name: "drive_relative", key: "C:tenant/object"},
		{name: "lowercase_drive_relative", key: "z:tenant/object"},
	}

	for _, tc := range driveKeys {
		t.Run(tc.name, func(t *testing.T) {
			_, err := sanitizeMinIOKey(tc.key)
			require.Error(t, err)
			require.ErrorContains(t, err, "absolute path")
		})
	}
}

func TestSanitizeMinIOKeyAcceptsNonDriveColonKey(t *testing.T) {
	const key = "tenant:archive/object"

	cleaned, err := sanitizeMinIOKey(key)

	require.NoError(t, err)
	require.Equal(t, key, cleaned)
}

func TestResizeImageActivityMapsWindowsDriveKeyToInvalidInputError(t *testing.T) {
	originalGetObject := getObjectFunc
	getObjectFunc = func(
		*minio.Client,
		context.Context,
		string,
		string,
		minio.GetObjectOptions,
	) (*minio.Object, error) {
		return nil, errors.New("unexpected storage access")
	}
	t.Cleanup(func() { getObjectFunc = originalGetObject })

	activities := &FileActivities{MinioClient: &minio.Client{}, Bucket: "bucket"}
	job := ProcessJob{
		ID:        "windows-drive-key",
		SourceKey: "C:/Windows/system32/drivers/etc/hosts",
		DestKey:   "output/result.png",
	}

	_, err := activities.ResizeImageActivity(context.Background(), job)
	require.Error(t, err)

	var applicationErr *temporal.ApplicationError
	require.ErrorAs(t, err, &applicationErr)
	require.Equal(t, "InvalidInputError", applicationErr.Type())
}
