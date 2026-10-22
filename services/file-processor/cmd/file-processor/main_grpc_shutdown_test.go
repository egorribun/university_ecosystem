package main

import (
	"context"
	"net"
	"testing"
	"time"

	"github.com/stretchr/testify/require"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
	"google.golang.org/grpc/health"
	"google.golang.org/grpc/health/grpc_health_v1"
)

// AUD-095: a Health.Watch stream stays open until its client disconnects, so an
// unbounded GracefulStop used to block shutdown while the watcher stayed connected.
func TestStopGRPCServerForcesStopWhileHealthWatchStaysOpen(t *testing.T) {
	listener, err := net.Listen("tcp", "127.0.0.1:0")
	require.NoError(t, err)

	server := grpc.NewServer()
	healthServer := health.NewServer()
	grpc_health_v1.RegisterHealthServer(server, healthServer)
	healthServer.SetServingStatus("", grpc_health_v1.HealthCheckResponse_SERVING)
	served := make(chan struct{})
	go func() {
		defer close(served)
		_ = server.Serve(listener)
	}()

	conn, err := grpc.NewClient(
		listener.Addr().String(),
		grpc.WithTransportCredentials(insecure.NewCredentials()),
	)
	require.NoError(t, err)
	defer func() { require.NoError(t, conn.Close()) }()

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	watch, err := grpc_health_v1.NewHealthClient(conn).Watch(
		ctx,
		&grpc_health_v1.HealthCheckRequest{},
	)
	require.NoError(t, err)
	first, err := watch.Recv()
	require.NoError(t, err)
	require.Equal(t, grpc_health_v1.HealthCheckResponse_SERVING, first.GetStatus())

	stopped := make(chan struct{})
	go func() {
		defer close(stopped)
		stopGRPCServer(server, 50*time.Millisecond, discardLogger())
	}()
	select {
	case <-stopped:
	case <-time.After(5 * time.Second):
		t.Fatal("stopGRPCServer blocked on an open Health.Watch stream")
	}
	<-served

	_, err = watch.Recv()
	require.Error(t, err, "the forced stop must end the watch stream")
}

func TestStopGRPCServerReturnsImmediatelyWhenCallsDrain(t *testing.T) {
	server := grpc.NewServer()

	stopped := make(chan struct{})
	go func() {
		defer close(stopped)
		stopGRPCServer(server, time.Minute, discardLogger())
	}()
	select {
	case <-stopped:
	case <-time.After(5 * time.Second):
		t.Fatal("stopGRPCServer did not return for an idle server")
	}
}
