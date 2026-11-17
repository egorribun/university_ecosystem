package hub

import (
	"context"
	"crypto/tls"
	"errors"
	"net"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"syscall"
	"testing"
	"time"

	"github.com/alicebob/miniredis/v2"
	goredis "github.com/redis/go-redis/v9"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func trackedSessionConnections(subscriber *sessionRevocationSubscriber) []net.Conn {
	subscriber.mu.Lock()
	defer subscriber.mu.Unlock()
	connections := make([]net.Conn, 0, len(subscriber.connections))
	for connection := range subscriber.connections {
		connections = append(connections, connection)
	}
	return connections
}

func TestRevocationSubscriberReleasesClosedReconnectConnections(t *testing.T) {
	server := miniredis.RunT(t)
	source := goredis.NewClient(&goredis.Options{Addr: server.Addr()})
	t.Cleanup(func() { require.NoError(t, source.Close()) })
	subscriber := newSessionRevocationSubscriber(source)
	t.Cleanup(func() { require.NoError(t, subscriber.close()) })
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	pubsub := subscriber.client.Subscribe(ctx, sessionRevocationsChannel)
	t.Cleanup(func() { _ = pubsub.Close() })
	_, err := pubsub.ReceiveTimeout(ctx, time.Second)
	require.NoError(t, err)

	for range 8 {
		connections := trackedSessionConnections(subscriber)
		require.Len(t, connections, 1)
		require.NoError(t, connections[0].Close())
		require.Empty(t, trackedSessionConnections(subscriber))
		// The real pinned go-redis reader observes the closed transport and
		// synchronously reconnects/resubscribes before returning its read error.
		_, err = pubsub.ReceiveTimeout(ctx, time.Second)
		require.Error(t, err)
		_, err = pubsub.ReceiveTimeout(ctx, time.Second)
		require.NoError(t, err)
		require.Len(t, trackedSessionConnections(subscriber), 1)
	}
	require.NoError(t, pubsub.Close())
	require.Empty(t, trackedSessionConnections(subscriber))
}

func TestRevocationSubscriberDialFinishingAfterStopCannotRetainConnection(t *testing.T) {
	local, peer := net.Pipe()
	t.Cleanup(func() {
		_ = local.Close()
		_ = peer.Close()
	})
	entered := make(chan struct{})
	release := make(chan struct{})
	source := goredis.NewClient(&goredis.Options{
		Dialer: func(context.Context, string, string) (net.Conn, error) {
			close(entered)
			<-release
			return local, nil
		},
	})
	t.Cleanup(func() { require.NoError(t, source.Close()) })
	subscriber := newSessionRevocationSubscriber(source)
	done := make(chan error, 1)
	go func() {
		connection, err := subscriber.client.Options().Dialer(context.Background(), "tcp", "unused")
		if connection != nil {
			_ = connection.Close()
		}
		done <- err
	}()
	<-entered
	require.NoError(t, subscriber.close())
	close(release)
	require.ErrorIs(t, <-done, net.ErrClosed)
	require.Empty(t, trackedSessionConnections(subscriber))
	_, err := peer.Write([]byte("closed"))
	require.Error(t, err)
}

func TestRevocationSubscriberConcurrentCloseAndStop(t *testing.T) {
	local, peer := net.Pipe()
	t.Cleanup(func() { _ = peer.Close() })
	source := goredis.NewClient(&goredis.Options{
		Dialer: func(context.Context, string, string) (net.Conn, error) { return local, nil },
	})
	t.Cleanup(func() { require.NoError(t, source.Close()) })
	subscriber := newSessionRevocationSubscriber(source)
	connection, err := subscriber.client.Options().Dialer(context.Background(), "tcp", "unused")
	require.NoError(t, err)
	var wg sync.WaitGroup
	for range 16 {
		wg.Go(func() { assert.NoError(t, connection.Close()) })
		wg.Go(func() { assert.NoError(t, subscriber.close()) })
	}
	wg.Wait()
	require.Empty(t, trackedSessionConnections(subscriber))
}

type revocationCloseErrorConn struct {
	net.Conn
	err error
}

func (c *revocationCloseErrorConn) Close() error {
	_ = c.Conn.Close()
	return c.err
}

func TestRevocationSubscriberPreservesCloseErrorAndDropsReference(t *testing.T) {
	local, peer := net.Pipe()
	t.Cleanup(func() { _ = peer.Close() })
	sentinel := errors.New("synthetic close error")
	source := goredis.NewClient(&goredis.Options{
		Dialer: func(context.Context, string, string) (net.Conn, error) {
			return &revocationCloseErrorConn{Conn: local, err: sentinel}, nil
		},
	})
	t.Cleanup(func() { require.NoError(t, source.Close()) })
	subscriber := newSessionRevocationSubscriber(source)
	t.Cleanup(func() { require.NoError(t, subscriber.close()) })
	connection, err := subscriber.client.Options().Dialer(context.Background(), "tcp", "unused")
	require.NoError(t, err)
	require.ErrorIs(t, connection.Close(), sentinel)
	require.Empty(t, trackedSessionConnections(subscriber))
}

func TestRevocationSubscriberTLSRetainsVerifiedTransportWithoutRawSocketExposure(t *testing.T) {
	server := httptest.NewTLSServer(http.HandlerFunc(func(http.ResponseWriter, *http.Request) {}))
	t.Cleanup(server.Close)
	tlsConfig := server.Client().Transport.(*http.Transport).TLSClientConfig.Clone()
	tlsConfig.MinVersion = tls.VersionTLS13
	source := goredis.NewClient(&goredis.Options{TLSConfig: tlsConfig})
	t.Cleanup(func() { require.NoError(t, source.Close()) })
	subscriber := newSessionRevocationSubscriber(source)
	t.Cleanup(func() { require.NoError(t, subscriber.close()) })
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	connection, err := subscriber.client.Options().Dialer(ctx, "tcp", strings.TrimPrefix(server.URL, "https://"))
	require.NoError(t, err)
	_, directSocket := connection.(syscall.Conn)
	require.False(t, directSocket, "TLS records must not be mistaken for plaintext socket bytes")
	underlying := connection.(interface{ NetConn() net.Conn }).NetConn()
	secure := underlying.(*tls.Conn)
	require.True(t, secure.ConnectionState().HandshakeComplete)
	require.NotEmpty(t, secure.ConnectionState().VerifiedChains)
	require.Equal(t, uint16(tls.VersionTLS13), secure.ConnectionState().Version)
	require.NoError(t, connection.Close())
	require.Empty(t, trackedSessionConnections(subscriber))
}

func TestRevocationSubscriberPreservesDirectSocketInspection(t *testing.T) {
	server := miniredis.RunT(t)
	source := goredis.NewClient(&goredis.Options{Addr: server.Addr()})
	t.Cleanup(func() { require.NoError(t, source.Close()) })
	subscriber := newSessionRevocationSubscriber(source)
	t.Cleanup(func() { require.NoError(t, subscriber.close()) })
	connection, err := subscriber.client.Options().Dialer(context.Background(), "tcp", server.Addr())
	require.NoError(t, err)
	socket, ok := connection.(syscall.Conn)
	require.True(t, ok)
	_, err = socket.SyscallConn()
	require.NoError(t, err)
	require.NoError(t, connection.Close())
	require.Empty(t, trackedSessionConnections(subscriber))
}
