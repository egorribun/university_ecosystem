package main

import (
	"context"
	"errors"
	"log/slog"
	"net/http"
	"os"
	"testing"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/quic-go/quic-go/http3"
	"github.com/stretchr/testify/require"
	"github.com/university-ecosystem/gateway/internal/config"
)

func TestRunServer_ShutsDownOnInjectedSignal(t *testing.T) {
	quit := make(chan os.Signal, 1)
	done := make(chan error, 1)
	cfg := &config.Config{
		Port:       "0",
		BackendURL: "http://127.0.0.1:1",
	}

	go func() {
		done <- runServer(cfg, gin.New(), slog.New(slog.NewTextHandler(os.Stderr, nil)), quit)
	}()

	quit <- os.Interrupt

	select {
	case err := <-done:
		require.NoError(t, err)
	case <-time.After(2 * time.Second):
		t.Fatal("runServer did not shut down after the injected signal")
	}
}

func TestRunServer_LogsHTTPShutdownError(t *testing.T) {
	hooksMu.Lock()
	oldShutdown := shutdownHTTPServerFunc
	t.Cleanup(func() {
		hooksMu.Lock()
		shutdownHTTPServerFunc = oldShutdown
		hooksMu.Unlock()
	})
	shutdownHTTPServerFunc = func(server *http.Server, ctx context.Context) error {
		// Preserve the injected error without leaking the real listener.
		return errors.Join(
			oldShutdown(server, ctx),
			server.Close(),
			errors.New("synthetic shutdown failure"),
		)
	}
	hooksMu.Unlock()

	quit := make(chan os.Signal, 1)
	done := make(chan error, 1)
	go func() {
		done <- runServer(&config.Config{Port: "0"}, gin.New(), slog.New(slog.NewTextHandler(os.Stderr, nil)), quit)
	}()
	quit <- os.Interrupt

	select {
	case err := <-done:
		require.NoError(t, err)
	case <-time.After(2 * time.Second):
		t.Fatal("runServer did not shut down after the injected signal")
	}
}

func TestRunServer_InvalidHTTP3AddressDoesNotBlockShutdown(t *testing.T) {
	listenDone := make(chan struct{})
	var listenErr error
	hooksMu.Lock()
	oldListenAndServeH3 := listenAndServeH3ServerFunc
	oldShutdownH3 := shutdownH3ServerFunc
	t.Cleanup(func() {
		hooksMu.Lock()
		listenAndServeH3ServerFunc = oldListenAndServeH3
		shutdownH3ServerFunc = oldShutdownH3
		hooksMu.Unlock()
	})
	listenAndServeH3ServerFunc = func(server *http3.Server) error {
		// Keep the real invalid-address failure, but observe its completion.
		listenErr = oldListenAndServeH3(server)
		close(listenDone)
		return listenErr
	}
	shutdownH3ServerFunc = func(*http3.Server, context.Context) error {
		return errors.New("synthetic HTTP/3 shutdown failure")
	}
	hooksMu.Unlock()

	quit := make(chan os.Signal, 1)
	done := make(chan error, 1)
	serverStopped := make(chan struct{})
	// Stop the owned server even if a readiness assertion fails. This cleanup
	// runs before hook restoration; neither wait relies on a scheduling sleep.
	t.Cleanup(func() {
		close(quit)
		select {
		case <-serverStopped:
		case <-time.After(2 * time.Second):
			t.Error("runServer did not stop during test cleanup")
		}
		select {
		case <-listenDone:
		case <-time.After(2 * time.Second):
			t.Error("HTTP/3 listener did not return during test cleanup")
		}
	})
	go func() {
		defer close(serverStopped)
		done <- runServer(&config.Config{Port: "0", H3Enabled: true, H3Port: "not-a-port"}, gin.New(), slog.New(slog.NewTextHandler(os.Stderr, nil)), quit)
	}()

	select {
	case <-listenDone:
		require.Error(t, listenErr)
	case <-time.After(2 * time.Second):
		t.Fatal("HTTP/3 listener did not return its invalid-address error")
	}
	quit <- os.Interrupt

	select {
	case err := <-done:
		require.NoError(t, err)
	case <-time.After(2 * time.Second):
		t.Fatal("runServer with invalid HTTP/3 address did not shut down")
	}
}

func TestRunServer_LogsHTTP3ListenError(t *testing.T) {
	hooksMu.Lock()
	oldListenAndServeH3 := listenAndServeH3ServerFunc
	t.Cleanup(func() {
		hooksMu.Lock()
		listenAndServeH3ServerFunc = oldListenAndServeH3
		hooksMu.Unlock()
	})
	called := make(chan struct{})
	listenAndServeH3ServerFunc = func(*http3.Server) error {
		close(called)
		return errors.New("synthetic HTTP/3 listen failure")
	}
	hooksMu.Unlock()

	quit := make(chan os.Signal, 1)
	done := make(chan error, 1)
	go func() {
		done <- runServer(&config.Config{Port: "0", H3Enabled: true, H3Port: "0"}, gin.New(), slog.New(slog.NewTextHandler(os.Stderr, nil)), quit)
	}()

	select {
	case <-called:
	case <-time.After(2 * time.Second):
		t.Fatal("HTTP/3 listener was not started")
	}
	quit <- os.Interrupt

	select {
	case err := <-done:
		require.NoError(t, err)
	case <-time.After(2 * time.Second):
		t.Fatal("runServer did not shut down after the injected signal")
	}
}
