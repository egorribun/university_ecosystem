package workflow

import (
	"bytes"
	"context"
	"image"
	"image/draw"
	"image/png"
	"net/http"
	"net/http/httptest"
	"os"
	"testing"

	"github.com/stretchr/testify/require"
)

func TestDecodeBoundedImageWebP(t *testing.T) {
	// Do not import the WebP codec here: registration must come from production.
	data, err := os.ReadFile("testdata/gopher-doc.1bpp.lossless.webp")
	require.NoError(t, err)
	img, format, err := decodeBoundedImage(bytes.NewReader(data))
	require.NoError(t, err)
	require.Equal(t, "webp", format)
	require.Positive(t, img.Bounds().Dx())
	require.Positive(t, img.Bounds().Dy())
}

func TestResizeImageActivityWebPSource(t *testing.T) {
	data, err := os.ReadFile("testdata/gopher-doc.1bpp.lossless.webp")
	require.NoError(t, err)
	fs := &fakeS3{getBody: data}
	uploadedContentType := make(chan string, 1)
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method == http.MethodPut {
			uploadedContentType <- r.Header.Get("Content-Type")
		}
		fs.handler().ServeHTTP(w, r)
	}))
	defer srv.Close()

	activities := &FileActivities{MinioClient: minioClientFor(t, srv.URL), Bucket: "bucket"}
	result, err := activities.ResizeImageActivity(context.Background(), ProcessJob{
		ID:        "webp-source",
		Type:      "image_resize",
		SourceKey: "in/source.webp",
		DestKey:   "out/resized.png",
		Options:   map[string]interface{}{"width": 8, "height": 6},
	})
	require.NoError(t, err)
	require.True(t, result.Success)
	require.Equal(t, "out/resized.png", result.DestKey)
	require.Equal(t, "image/png", <-uploadedContentType)
}

func TestWebPDecodeStillAppliesSourceDimensionLimit(t *testing.T) {
	data, err := os.ReadFile("testdata/gopher-doc.1bpp.lossless.webp")
	require.NoError(t, err)
	// The VP8L image header stores width-1 in its low 14 bits. Advertise an
	// 8192x1 source, beyond the 4096 per-dimension cap, before pixel decoding.
	data[21], data[22], data[23], data[24] = 0xff, 0x1f, 0, 0
	_, _, err = decodeBoundedImage(bytes.NewReader(data))
	require.ErrorContains(t, err, "source image dimensions 8192x1 exceed image limits")
}

func TestWebPEncoderProducesRealPNG(t *testing.T) {
	data, err := os.ReadFile("testdata/gopher-doc.1bpp.lossless.webp")
	require.NoError(t, err)
	img, format, err := decodeBoundedImage(bytes.NewReader(data))
	require.NoError(t, err)
	// Exercise the real WebP-to-PNG encoder without importing the decoder
	// from test code or relying on the activity's AWS-chunked PUT body.
	dst := image.NewRGBA(img.Bounds())
	draw.Draw(dst, dst.Bounds(), img, img.Bounds().Min, draw.Src)
	encoded, outFormat, err := encodeImage(dst, format)
	require.NoError(t, err)
	require.Equal(t, "png", outFormat)
	decoded, err := png.Decode(bytes.NewReader(encoded.Bytes()))
	require.NoError(t, err)
	require.Equal(t, img.Bounds(), decoded.Bounds())
}
