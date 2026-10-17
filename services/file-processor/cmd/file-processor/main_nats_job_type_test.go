package main

import (
	"bytes"
	"context"
	"testing"

	"github.com/stretchr/testify/require"
)

func TestHandleFileProcessDeliveryRejectsUnimplementedTypes(t *testing.T) {
	for _, typ := range []string{"image_compress", "pdf_preview", "video_transcode"} {
		t.Run(typ, func(t *testing.T) {
			message := &fakeProcessDeliveryMessage{payload: bytes.Replace(validProcessPayload(), []byte("image_resize"), []byte(typ), 1)}
			client := &natsTemporalClientStub{calls: make(chan struct{}, 1)}
			handleFileProcessDelivery(context.Background(), message, client, discardLogger())
			require.Equal(t, 1, message.termCount)
			require.Zero(t, message.ackCount)
			require.Zero(t, message.nakCount, "unsupported operations must not be retried")
			require.Empty(t, client.options, "unsupported jobs must not start Temporal workflows")
		})
	}
}
