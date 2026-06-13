package service

// Coverage tests (testing session 10) for validateProcessFileRequest arms that
// TestGRPCPathTraversalRejection (path-traversal + oversized-key) does not
// reach: empty id, unsupported type, empty source/dest, options-count limit,
// and oversized option key/value. Direct gRPC-handler calls with a nil
// TemporalClient — every case returns at the validation boundary before any
// workflow start, so no Temporal connection is needed.

import (
	"context"
	"strings"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	pb "github.com/university-ecosystem/core/gen/go/file_processor/v1"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

func TestValidateProcessFileRequest_RejectionArms(t *testing.T) {
	s := &Server{TemporalClient: nil}
	ctx := context.Background()

	bigOptions := make(map[string]string, maxOptionsCount+1)
	for i := 0; i < maxOptionsCount+1; i++ {
		bigOptions[string(rune('a'+i))] = "1"
	}

	cases := []struct {
		name         string
		req          *pb.ProcessFileRequest
		wantContains string
	}{
		{
			name:         "empty id",
			req:          &pb.ProcessFileRequest{Type: "image_resize", SourceKey: "s", DestKey: "d"},
			wantContains: "id is required",
		},
		{
			name:         "unsupported type",
			req:          &pb.ProcessFileRequest{Id: "x", Type: "audio_normalize", SourceKey: "s", DestKey: "d"},
			wantContains: "unsupported file type",
		},
		{
			name:         "empty source key",
			req:          &pb.ProcessFileRequest{Id: "x", Type: "image_resize", SourceKey: "", DestKey: "d"},
			wantContains: "source_key and dest_key are required",
		},
		{
			name:         "empty dest key",
			req:          &pb.ProcessFileRequest{Id: "x", Type: "image_resize", SourceKey: "s", DestKey: ""},
			wantContains: "source_key and dest_key are required",
		},
		{
			name: "options count over limit",
			req: &pb.ProcessFileRequest{
				Id: "x", Type: "image_resize", SourceKey: "s", DestKey: "d", Options: bigOptions,
			},
			wantContains: "options count",
		},
		{
			name: "option key too long",
			req: &pb.ProcessFileRequest{
				Id: "x", Type: "image_resize", SourceKey: "s", DestKey: "d",
				Options: map[string]string{strings.Repeat("k", maxOptionKeyLen+1): "v"},
			},
			wantContains: "exceeds size limit",
		},
		{
			name: "option value too long",
			req: &pb.ProcessFileRequest{
				Id: "x", Type: "image_resize", SourceKey: "s", DestKey: "d",
				Options: map[string]string{"width": strings.Repeat("v", maxOptionValueLen+1)},
			},
			wantContains: "exceeds size limit",
		},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			_, err := s.ProcessFile(ctx, tc.req)
			require.Error(t, err)
			st, ok := status.FromError(err)
			require.True(t, ok, "expected a gRPC status error")
			assert.Equal(t, codes.InvalidArgument, st.Code())
			assert.Contains(t, st.Message(), tc.wantContains)
		})
	}
}
