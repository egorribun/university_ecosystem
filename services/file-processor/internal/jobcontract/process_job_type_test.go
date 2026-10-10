package jobcontract

import "testing"

func TestValidateRejectsUnimplementedTypes(t *testing.T) {
	for _, typ := range []string{"image_compress", "pdf_preview", "video_transcode"} {
		t.Run(typ, func(t *testing.T) {
			requireCode(t, Validate("job", typ, "in/file", "out/file", nil), "unsupported_type")
		})
	}
}
