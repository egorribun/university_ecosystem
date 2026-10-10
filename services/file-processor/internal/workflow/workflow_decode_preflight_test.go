package workflow

import (
	"bytes"
	"image"
	"io"
	"sync/atomic"
	"testing"

	"github.com/stretchr/testify/require"
	"go.temporal.io/sdk/temporal"
)

const preflightImageMagic = "PFIL"

var (
	preflightConfigCalls  atomic.Int32
	preflightDecodeCalls  atomic.Int32
	preflightConfigWidth  int
	preflightConfigHeight int
)

func init() {
	image.RegisterFormat(
		"workflow-preflight-test",
		preflightImageMagic,
		func(io.Reader) (image.Image, error) {
			preflightDecodeCalls.Add(1)
			return nil, io.ErrUnexpectedEOF
		},
		func(io.Reader) (image.Config, error) {
			preflightConfigCalls.Add(1)
			return image.Config{Width: preflightConfigWidth, Height: preflightConfigHeight}, nil
		},
	)
}

func TestDecodeBoundedImageRejectsSourceBeforeFullDecode(t *testing.T) {
	tests := []struct {
		name   string
		width  int
		height int
	}{
		{name: "single dimension cap", width: maxImageDimension + 1, height: 1},
		{name: "pixel cap", width: 3000, height: 2667},
		{name: "dimension multiplication overflow", width: int(^uint(0) >> 1), height: 2},
	}

	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			preflightConfigCalls.Store(0)
			preflightDecodeCalls.Store(0)
			preflightConfigWidth = test.width
			preflightConfigHeight = test.height

			img, format, err := decodeBoundedImage(bytes.NewReader([]byte(preflightImageMagic)))

			require.Nil(t, img)
			require.Empty(t, format)
			require.Error(t, err)
			var applicationErr *temporal.ApplicationError
			require.ErrorAs(t, err, &applicationErr)
			require.Equal(t, "FileTooLargeError", applicationErr.Type())
			require.EqualValues(t, 1, preflightConfigCalls.Load(), "metadata must be inspected before pixel decoding")
			require.Zero(t, preflightDecodeCalls.Load(), "full decode must not run until source dimensions pass preflight")
		})
	}
}

func TestDecodeBoundedImageRejectsNonPositiveDimensionsBeforeFullDecode(t *testing.T) {
	tests := []struct {
		name   string
		width  int
		height int
	}{
		{name: "zero width", width: 0, height: 1},
		{name: "negative height", width: 1, height: -1},
	}

	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			preflightConfigCalls.Store(0)
			preflightDecodeCalls.Store(0)
			preflightConfigWidth = test.width
			preflightConfigHeight = test.height

			img, format, err := decodeBoundedImage(bytes.NewReader([]byte(preflightImageMagic)))

			require.Nil(t, img)
			require.Empty(t, format)
			require.Error(t, err)
			var applicationErr *temporal.ApplicationError
			require.ErrorAs(t, err, &applicationErr)
			require.Equal(t, "InvalidInputError", applicationErr.Type())
			require.EqualValues(t, 1, preflightConfigCalls.Load(), "metadata must be inspected before pixel decoding")
			require.Zero(t, preflightDecodeCalls.Load(), "non-positive dimensions must be rejected before full decode")
		})
	}
}
