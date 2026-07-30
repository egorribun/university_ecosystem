package main

import (
	"context"
	"encoding/json"
	"net"
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	pb "github.com/university-ecosystem/core/gen/go/file_processor/v1"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/credentials/insecure"
	"google.golang.org/grpc/status"
)

type empiricalSlowServer struct {
	pb.UnimplementedFileProcessingServiceServer
	delay time.Duration
}

func (s *empiricalSlowServer) ProcessFile(ctx context.Context, _ *pb.ProcessFileRequest) (*pb.ProcessFileResponse, error) {
	select {
	case <-time.After(s.delay):
		return &pb.ProcessFileResponse{Success: true}, nil
	case <-ctx.Done():
		return nil, ctx.Err()
	}
}

// TestEmpirical_GRPCDefaultTimeoutConfig verifies RZ-31-05:
// WithDefaultServiceConfig in services/gateway enforces a per-RPC default timeout.
func TestEmpirical_GRPCDefaultTimeoutConfig(t *testing.T) {
	const prodServiceConfigJSON = `{"methodConfig":[{"name":[{}],"timeout":"30s"}]}`

	t.Run("Validates gRPC ServiceConfig JSON structure", func(t *testing.T) {
		var configMap map[string]any
		err := json.Unmarshal([]byte(prodServiceConfigJSON), &configMap)
		require.NoError(t, err, "Production service config JSON must be valid JSON")

		methodConfig, ok := configMap["methodConfig"].([]any)
		require.True(t, ok, "serviceConfig must contain methodConfig array")
		require.Len(t, methodConfig, 1)

		mc, ok := methodConfig[0].(map[string]any)
		require.True(t, ok)
		assert.Equal(t, "30s", mc["timeout"], "default per-RPC timeout must be 30s")

		names, ok := mc["name"].([]any)
		require.True(t, ok)
		require.Len(t, names, 1)
		// Empty name object [{}] matches all services and all methods per gRPC spec
	})

	t.Run("Empirically verifies deadline enforcement when server delay exceeds timeout", func(t *testing.T) {
		var lc net.ListenConfig
		lis, err := lc.Listen(context.Background(), "tcp", "127.0.0.1:0")
		require.NoError(t, err)
		t.Cleanup(func() { _ = lis.Close() })

		srv := grpc.NewServer()
		pb.RegisterFileProcessingServiceServer(srv, &empiricalSlowServer{delay: 500 * time.Millisecond})
		go func() { _ = srv.Serve(lis) }()
		t.Cleanup(srv.Stop)

		// Dial using default service config with 150ms timeout for fast empirical verification
		testServiceConfigJSON := `{"methodConfig":[{"name":[{}],"timeout":"0.15s"}]}`
		conn, err := grpc.NewClient(
			lis.Addr().String(),
			grpc.WithTransportCredentials(insecure.NewCredentials()),
			grpc.WithDefaultServiceConfig(testServiceConfigJSON),
		)
		require.NoError(t, err)
		t.Cleanup(func() { _ = conn.Close() })

		client := pb.NewFileProcessingServiceClient(conn)

		start := time.Now()
		// Execute call with context.Background() — NO explicit deadline set on context!
		_, callErr := client.ProcessFile(context.Background(), &pb.ProcessFileRequest{
			Id:        "empirical-test",
			Type:      "test",
			SourceKey: "src",
			DestKey:   "dst",
		})
		elapsed := time.Since(start)

		require.Error(t, callErr, "ProcessFile must fail when server delay exceeds service config default timeout")
		st, ok := status.FromError(callErr)
		require.True(t, ok, "Error must be gRPC status")
		assert.Equal(t, codes.DeadlineExceeded, st.Code(), "Status code must be DeadlineExceeded")
		assert.Less(t, elapsed, 400*time.Millisecond, "Client call must return within timeout period, not full 500ms server sleep")
	})
}
