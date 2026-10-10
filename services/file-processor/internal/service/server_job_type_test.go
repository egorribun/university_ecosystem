package service

import (
	"context"
	"testing"

	"github.com/stretchr/testify/require"
	pb "github.com/university-ecosystem/core/gen/go/file_processor/v1"
	"go.temporal.io/sdk/client"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

func TestProcessFileRejectsUnimplementedTypesBeforeTemporal(t *testing.T) {
	for _, typ := range []string{"image_compress", "pdf_preview", "video_transcode"} {
		t.Run(typ, func(t *testing.T) {
			started := false
			server := &Server{TemporalClient: &mockTemporalClient{executeFunc: func(context.Context, client.StartWorkflowOptions, interface{}, ...interface{}) (client.WorkflowRun, error) {
				started = true
				return &mockWorkflowRun{id: "unexpected"}, nil
			}}}
			result, err := server.ProcessFile(context.Background(), &pb.ProcessFileRequest{
				Id: "unsupported-job", Type: typ, SourceKey: "in/file", DestKey: "out/file",
			})
			require.Nil(t, result)
			require.Equal(t, codes.InvalidArgument, status.Code(err))
			require.ErrorContains(t, err, "unsupported file type")
			require.False(t, started, "unsupported jobs must not start Temporal workflows")
		})
	}
}
