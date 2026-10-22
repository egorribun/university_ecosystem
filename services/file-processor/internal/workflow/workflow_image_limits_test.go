package workflow

import (
	"bytes"
	"context"
	"errors"
	"image"
	"io"
	"net/http/httptest"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"go.temporal.io/sdk/temporal"
)

func TestResizeImageActivityRejectsOversizedSourceBeforeUpload(t *testing.T) {
	tests := []struct {
		name   string
		width  int
		height int
	}{
		{name: "dimension limit", width: maxImageDimension + 1, height: 1},
		{name: "pixel limit", width: 3000, height: 2667},
	}

	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			fs := &fakeS3{getBody: makeRGBAPNG(t, test.width, test.height)}
			server := httptest.NewServer(fs.handler())
			defer server.Close()

			activities := &FileActivities{
				MinioClient: minioClientFor(t, server.URL),
				Bucket:      "bucket",
			}
			job := ProcessJob{
				ID:        "oversized-source",
				SourceKey: "in/large.png",
				DestKey:   "out/large.png",
			}

			result, err := activities.ResizeImageActivity(context.Background(), job)

			assert.Nil(t, result)
			require.Error(t, err)
			var applicationErr *temporal.ApplicationError
			require.ErrorAs(t, err, &applicationErr)
			assert.Equal(t, "FileTooLargeError", applicationErr.Type())
			assert.Empty(t, fs.putBody, "oversized source must be rejected before upload")
		})
	}
}

func TestValidateImageConfigBoundsDimensionsAndPixelCount(t *testing.T) {
	tests := []struct {
		name        string
		width       int
		height      int
		wantErrType string
	}{
		{name: "zero width", width: 0, height: 1, wantErrType: "InvalidInputError"},
		{name: "zero height", width: 1, height: 0, wantErrType: "InvalidInputError"},
		{name: "width over limit", width: maxImageDimension + 1, height: 1, wantErrType: "FileTooLargeError"},
		{name: "height over limit", width: 1, height: maxImageDimension + 1, wantErrType: "FileTooLargeError"},
		{name: "pixel count over limit", width: 3000, height: 2667, wantErrType: "FileTooLargeError"},
		{name: "pixel count at limit", width: 4000, height: 2000},
	}

	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			err := validateImageConfig(image.Config{Width: test.width, Height: test.height})
			if test.wantErrType == "" {
				require.NoError(t, err)
				return
			}

			require.Error(t, err)
			var applicationErr *temporal.ApplicationError
			require.True(t, errors.As(err, &applicationErr))
			assert.Equal(t, test.wantErrType, applicationErr.Type())
		})
	}
}

func TestDecodeBoundedImageRejectsOversizedMetadata(t *testing.T) {
	image.RegisterFormat(
		"oversized-header-test",
		"XHDR",
		func(io.Reader) (image.Image, error) {
			return nil, errors.New("decode should not run")
		},
		func(reader io.Reader) (image.Config, error) {
			read, err := io.Copy(io.Discard, reader)
			if err != nil {
				return image.Config{}, err
			}
			if read >= maxImageConfigBytes {
				return image.Config{}, errors.New("metadata fixture exceeds the config limit")
			}
			return image.Config{Width: 1, Height: 1}, nil
		},
	)
	data := append([]byte("XHDR"), bytes.Repeat([]byte{'x'}, maxImageConfigBytes+1)...)

	_, _, err := decodeBoundedImage(bytes.NewReader(data))

	require.Error(t, err)
	var applicationErr *temporal.ApplicationError
	require.True(t, errors.As(err, &applicationErr))
	assert.Equal(t, "FileTooLargeError", applicationErr.Type())
}
