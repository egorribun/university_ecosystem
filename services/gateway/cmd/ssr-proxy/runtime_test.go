package main

import (
	"context"
	"crypto/x509"
	"net"
	"path/filepath"
	"testing"
	"time"

	"github.com/spiffe/go-spiffe/v2/proto/spiffe/workload"
	"github.com/spiffe/go-spiffe/v2/svid/x509svid"
	"github.com/stretchr/testify/require"
	"google.golang.org/grpc"
)

type proxyWorkloadAPI struct {
	workload.UnimplementedSpiffeWorkloadAPIServer
	response *workload.X509SVIDResponse
}

func (s *proxyWorkloadAPI) FetchX509SVID(_ *workload.X509SVIDRequest, stream grpc.ServerStreamingServer[workload.X509SVIDResponse]) error {
	if err := stream.Send(s.response); err != nil {
		return err
	}
	<-stream.Context().Done()
	return nil
}

func startProxyWorkloadAPI(t *testing.T, svid *x509svid.SVID, ca *x509.Certificate) string {
	t.Helper()
	key, err := x509.MarshalPKCS8PrivateKey(svid.PrivateKey)
	require.NoError(t, err)
	socket := filepath.Join(t.TempDir(), "agent.sock")
	listener, err := net.Listen("unix", socket)
	require.NoError(t, err)
	server := grpc.NewServer()
	workload.RegisterSpiffeWorkloadAPIServer(server, &proxyWorkloadAPI{
		response: &workload.X509SVIDResponse{Svids: []*workload.X509SVID{{
			SpiffeId:    svid.ID.String(),
			X509Svid:    svid.Certificates[0].Raw,
			X509SvidKey: key,
			Bundle:     ca.Raw,
		}}},
	})
	done := make(chan error, 1)
	go func() { done <- server.Serve(listener) }()
	t.Cleanup(func() {
		server.Stop()
		require.NoError(t, <-done)
	})
	return "unix://" + socket
}

func TestProxyRunUsesRealWorkloadClientAndStops(t *testing.T) {
	values := proxyEnvironment()
	cfg, err := readConfig(func(key string) string { return values[key] })
	require.NoError(t, err)
	ca, key := tlsFixtureCA(t)
	svid := tlsFixtureSVID(t, ca, key, cfg.self, time.Now().Add(time.Hour))
	values["SPIFFE_ENDPOINT_SOCKET"] = startProxyWorkloadAPI(t, svid, ca)
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	done := make(chan error, 1)
	go func() { done <- execute(ctx, nil, func(key string) string { return values[key] }) }()
	require.Eventually(t, func() bool {
		return probe(ctx, "http://"+listenAddress+"/_ssr_proxy/live") == nil
	}, 5*time.Second, 10*time.Millisecond)
	cancel()
	select {
	case err := <-done:
		require.NoError(t, err)
	case <-time.After(3 * time.Second):
		t.Fatal("proxy failed to stop")
	}
}

func TestProxyRunRejectsOccupiedListenerAfterIdentityValidation(t *testing.T) {
	values := proxyEnvironment()
	cfg, err := readConfig(func(key string) string { return values[key] })
	require.NoError(t, err)
	ca, key := tlsFixtureCA(t)
	svid := tlsFixtureSVID(t, ca, key, cfg.self, time.Now().Add(time.Hour))
	cfg.socket = startProxyWorkloadAPI(t, svid, ca)
	listener, err := net.Listen("tcp4", listenAddress)
	require.NoError(t, err)
	defer listener.Close()
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	require.Error(t, run(ctx, cfg))
}
