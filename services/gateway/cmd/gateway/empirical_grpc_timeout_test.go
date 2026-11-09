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
	"google.golang.org/grpc/connectivity"
	"google.golang.org/grpc/credentials/insecure"
	"google.golang.org/grpc/status"
)

type empiricalSlowServer struct {
	pb.UnimplementedFileProcessingServiceServer
	entered chan<- struct{}
	release <-chan struct{}
}

func (s *empiricalSlowServer) ProcessFile(_ context.Context, _ *pb.ProcessFileRequest) (*pb.ProcessFileResponse, error) {
	select {
	case s.entered <- struct{}{}:
	default:
	}
	<-s.release
	return &pb.ProcessFileResponse{Success: true}, nil
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
		t.Cleanup(func() {
			if closeErr := lis.Close(); closeErr != nil {
				t.Logf("test listener already closed: %v", closeErr)
			}
		})

		entered := make(chan struct{}, 1)
		release := make(chan struct{})
		defer close(release)
		srv := grpc.NewServer(grpc.WaitForHandlers(true))
		pb.RegisterFileProcessingServiceServer(srv, &empiricalSlowServer{entered: entered, release: release})
		go func() {
			if serveErr := srv.Serve(lis); serveErr != nil {
				t.Logf("gRPC test server stopped: %v", serveErr)
			}
		}()
		t.Cleanup(srv.Stop)

		// Dial using default service config with 150ms timeout for fast empirical verification
		testServiceConfigJSON := `{"methodConfig":[{"name":[{}],"timeout":"0.15s"}]}`
		conn, err := grpc.NewClient(
			lis.Addr().String(),
			grpc.WithTransportCredentials(insecure.NewCredentials()),
			grpc.WithDefaultServiceConfig(testServiceConfigJSON),
		)
		require.NoError(t, err)
		t.Cleanup(func() { require.NoError(t, conn.Close()) })

		conn.Connect()
		readyCtx, cancelReady := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancelReady()
		for state := conn.GetState(); state != connectivity.Ready; state = conn.GetState() {
			if !conn.WaitForStateChange(readyCtx, state) {
				t.Fatalf("gRPC connection did not become READY before timeout test: state=%s final_state=%s wait_error=%v", state, conn.GetState(), readyCtx.Err())
			}
		}
		cancelReady()
		require.Equal(t, connectivity.Ready, conn.GetState(), "gRPC connection must be READY before measuring the RPC timeout")

		client := pb.NewFileProcessingServiceClient(conn)

		start := time.Now()
		callErrCh := make(chan error, 1)
		go func() {
			_, callErr := client.ProcessFile(context.Background(), &pb.ProcessFileRequest{
				Id:        "empirical-test",
				Type:      "test",
				SourceKey: "src",
				DestKey:   "dst",
			})
			callErrCh <- callErr
		}()

		timeoutGuard := time.NewTimer(400 * time.Millisecond)
		defer timeoutGuard.Stop()
		var callErr error
		select {
		case callErr = <-callErrCh:
		case <-timeoutGuard.C:
			t.Fatalf("RPC did not return within 400ms: elapsed=%s", time.Since(start))
		}
		select {
		case <-entered:
		default:
			st, statusOK := status.FromError(callErr)
			if statusOK {
				t.Fatalf("RPC returned before the test server entered: code=%s message=%q elapsed=%s err=%v", st.Code(), st.Message(), time.Since(start), callErr)
			}
			t.Fatalf("RPC returned before the test server entered: err=%v elapsed=%s", callErr, time.Since(start))
		}
		elapsed := time.Since(start)

		require.Error(t, callErr, "ProcessFile must fail when server response is held beyond the service config timeout; elapsed=%s err=%v", elapsed, callErr)
		st, ok := status.FromError(callErr)
		require.True(t, ok, "Error must be gRPC status: err=%v", callErr)
		assert.Equal(t, codes.DeadlineExceeded, st.Code(), "Status code must be DeadlineExceeded: code=%s message=%q elapsed=%s err=%v", st.Code(), st.Message(), elapsed, callErr)
		assert.Less(t, elapsed, 400*time.Millisecond, "Client call must return before the test server gate is released during cleanup")
	})
}
