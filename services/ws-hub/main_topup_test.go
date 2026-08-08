package main

import (
	"errors"
	"io"
	"log/slog"
	"net"
	"net/http"
	"os"
	"testing"
	"time"

	"github.com/quic-go/quic-go/http3"
	"github.com/quic-go/webtransport-go"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"github.com/university-ecosystem/ws-hub/pkg/config"
	"github.com/university-ecosystem/ws-hub/pkg/hub"
)

func TestStartupPacketConn_ForwardsOperationsAndSignalsOnce(t *testing.T) {
	conn, err := net.ListenUDP("udp", &net.UDPAddr{IP: net.IPv4(127, 0, 0, 1), Port: 0})
	require.NoError(t, err)
	t.Cleanup(func() { _ = conn.Close() }) //nolint:errcheck // test cleanup

	ready := make(chan struct{})
	wrapped := &startupPacketConn{PacketConn: conn, ready: ready}

	assert.Equal(t, conn.LocalAddr(), wrapped.LocalAddr())
	select {
	case <-ready:
	case <-time.After(time.Second):
		t.Fatal("startup barrier was not signalled")
	}

	// The barrier is a sync.Once: all delegated operations remain safe after it
	// has fired and continue to return the underlying socket errors.
	localAddr := conn.LocalAddr()
	require.NoError(t, conn.Close())
	_, _, err = wrapped.ReadFrom(make([]byte, 1))
	assert.Error(t, err)
	_, err = wrapped.WriteTo([]byte("x"), localAddr)
	assert.Error(t, err)
	wrapped.signalReady()
}

func TestServeWebTransport_RejectsInvalidAddressAndCertificate(t *testing.T) {
	logger := slog.New(slog.NewTextHandler(io.Discard, nil))
	cfg := &config.Config{}

	err := serveWebTransport(&webtransport.Server{H3: &http3.Server{}}, "not-a-port", cfg, logger, make(chan struct{}))
	assert.Error(t, err)

	cfg.TLSCertFile = t.TempDir() + "\\missing-cert.pem"
	cfg.TLSKeyFile = t.TempDir() + "\\missing-key.pem"
	err = serveWebTransport(&webtransport.Server{H3: &http3.Server{}}, "0", cfg, logger, make(chan struct{}))
	assert.Error(t, err)
}

func TestWaitForWebTransportStartup_AllTerminalBranches(t *testing.T) {
	logger := slog.New(slog.NewTextHandler(io.Discard, nil))
	t.Run("ready", func(t *testing.T) {
		ready := make(chan struct{})
		close(ready)
		err, requested := waitForWebTransportStartup(make(chan os.Signal), ready, make(chan struct{}), make(chan error), logger)
		assert.NoError(t, err)
		assert.False(t, requested)
	})
	t.Run("done", func(t *testing.T) {
		done := make(chan struct{})
		close(done)
		err, requested := waitForWebTransportStartup(make(chan os.Signal), make(chan struct{}), done, make(chan error), logger)
		assert.NoError(t, err)
		assert.False(t, requested)
	})
	t.Run("server error", func(t *testing.T) {
		ready := make(chan struct{})
		done := make(chan struct{})
		errCh := make(chan error)
		want := errors.New("webtransport failed")
		go func() {
			errCh <- want
			close(done)
		}()
		err, requested := waitForWebTransportStartup(make(chan os.Signal), ready, done, errCh, logger)
		assert.ErrorIs(t, err, want)
		assert.True(t, requested)
	})
	t.Run("signal", func(t *testing.T) {
		ready := make(chan struct{})
		done := make(chan struct{})
		quit := make(chan os.Signal)
		go func() {
			quit <- os.Interrupt
			close(done)
		}()
		err, requested := waitForWebTransportStartup(quit, ready, done, make(chan error), logger)
		assert.NoError(t, err)
		assert.True(t, requested)
	})
}

func TestWaitForShutdown_AllTerminalBranches(t *testing.T) {
	logger := slog.New(slog.NewTextHandler(io.Discard, nil))
	t.Run("server error", func(t *testing.T) {
		errCh := make(chan error, 1)
		want := errors.New("tcp failed")
		errCh <- want
		assert.ErrorIs(t, waitForShutdown(make(chan os.Signal), errCh, logger), want)
	})
	t.Run("signal", func(t *testing.T) {
		quit := make(chan os.Signal, 1)
		quit <- os.Interrupt
		assert.NoError(t, waitForShutdown(quit, make(chan error), logger))
	})
}

func TestRunServer_WaitsForShutdownAfterWebTransportReady(t *testing.T) {
	oldServe := webTransportServeFunc
	t.Cleanup(func() { webTransportServeFunc = oldServe })
	ready := make(chan struct{})
	webTransportServeFunc = func(_ *webtransport.Server, conn net.PacketConn) error {
		_ = conn.LocalAddr()
		close(ready)
		return nil
	}

	quit := make(chan os.Signal, 1)
	cfg := &config.Config{Port: "0", WebTransportPort: "0"}
	h := hub.NewHub(nil, slog.New(slog.NewTextHandler(io.Discard, nil)), nil, cfg, nil)
	done := make(chan error, 1)
	go func() {
		done <- runServer(cfg, slog.New(slog.NewTextHandler(io.Discard, nil)), h, http.NewServeMux(), quit)
	}()

	select {
	case <-ready:
	case <-time.After(time.Second):
		t.Fatal("WebTransport server did not signal readiness")
	}
	quit <- os.Interrupt

	select {
	case err := <-done:
		assert.NoError(t, err)
	case <-time.After(2 * time.Second):
		t.Fatal("runServer did not enter and leave the shutdown wait path")
	}
}

func TestShutdownWebTransport_ClosesWhenNotAlreadyDone(t *testing.T) {
	wtServer := &webtransport.Server{H3: &http3.Server{}}
	done := make(chan struct{})
	returned := make(chan struct{})
	go func() {
		shutdownWebTransport(wtServer, done)
		close(returned)
	}()

	select {
	case <-time.After(100 * time.Millisecond):
		close(done)
	case <-returned:
		// A server that was already closed still must not make the helper hang.
		return
	}
	select {
	case <-returned:
	case <-time.After(time.Second):
		t.Fatal("shutdownWebTransport did not return after completion signal")
	}
}

func TestSetupSignalChannel_UsesInjectedAndOwnsDefault(t *testing.T) {
	injected := make(chan os.Signal, 1)
	got, stop := setupSignalChannel(injected)
	assert.Equal(t, (<-chan os.Signal)(injected), got)
	stop()

	got, stop = setupSignalChannel()
	assert.NotNil(t, got)
	stop()
}
