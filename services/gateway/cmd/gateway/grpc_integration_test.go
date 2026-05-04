//go:build integration

package main

import (
	"context"
	"net"
	"testing"
	"time"

	pb "github.com/university-ecosystem/core/gen/go/file_processor/v1"
	"github.com/stretchr/testify/require"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/credentials/insecure"
	"google.golang.org/grpc/status"
)

// slowFileProcessor is a stub gRPC server that intentionally exceeds the
// configured timeout, used to verify WithDefaultServiceConfig enforcement.
type slowFileProcessor struct {
	pb.UnimplementedFileProcessingServiceServer
}

// ProcessFile sleeps 1 second OR until ctx is cancelled. With a client-side
// 200ms timeout from WithDefaultServiceConfig, the cancellation fires first.
func (s *slowFileProcessor) ProcessFile(ctx context.Context, _ *pb.ProcessFileRequest) (*pb.ProcessFileResponse, error) {
	select {
	case <-time.After(1 * time.Second):
		return &pb.ProcessFileResponse{Success: true}, nil
	case <-ctx.Done():
		return nil, ctx.Err()
	}
}

// TestIntegration_GRPCDefaultTimeout verifies RZ-31-05: WithDefaultServiceConfig
// at cmd/gateway/main.go:140 enforces a per-RPC timeout (production: 30s).
// We use 200ms here for a fast test of the SAME mechanism.
//
// Path:
//   client.ProcessFile(ctx, req)
//     → grpc-go applies methodConfig timeout (200ms here, 30s in prod)
//     → server sleep > timeout
//     → client returns codes.DeadlineExceeded
func TestIntegration_GRPCDefaultTimeout(t *testing.T) {
	// Spin up a real in-process gRPC server on a random port.
	lis, err := net.Listen("tcp", "127.0.0.1:0")
	require.NoError(t, err)
	t.Cleanup(func() { _ = lis.Close() })

	srv := grpc.NewServer()
	pb.RegisterFileProcessingServiceServer(srv, &slowFileProcessor{})
	go func() { _ = srv.Serve(lis) }()
	t.Cleanup(srv.Stop)

	// Production wiring (matches cmd/gateway/main.go:140) but with 200ms
	// timeout instead of 30s for fast test feedback. The methodConfig name
	// `[{}]` matches every method on every service (gRPC service config spec).
	conn, err := grpc.NewClient(
		lis.Addr().String(),
		grpc.WithTransportCredentials(insecure.NewCredentials()),
		grpc.WithDefaultServiceConfig(`{"methodConfig":[{"name":[{}],"timeout":"0.2s"}]}`),
	)
	require.NoError(t, err)
	t.Cleanup(func() { _ = conn.Close() })

	client := pb.NewFileProcessingServiceClient(conn)

	start := time.Now()
	_, err = client.ProcessFile(context.Background(), &pb.ProcessFileRequest{
		Id:        "test",
		Type:      "image_resize",
		SourceKey: "x",
		DestKey:   "y",
	})
	elapsed := time.Since(start)

	require.Error(t, err, "ProcessFile must fail when server exceeds methodConfig timeout")
	st, ok := status.FromError(err)
	require.True(t, ok, "error must be a gRPC status, got %T: %v", err, err)
	require.Equal(t, codes.DeadlineExceeded, st.Code(),
		"WithDefaultServiceConfig must enforce timeout with DeadlineExceeded, got %v", err)
	require.Less(t, elapsed, 800*time.Millisecond,
		"timeout must fire fast (~200ms), not wait the full 1s server sleep")
}
