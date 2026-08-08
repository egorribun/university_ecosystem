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
	oldShutdown := shutdownHTTPServerFunc
	t.Cleanup(func() { shutdownHTTPServerFunc = oldShutdown })
	shutdownHTTPServerFunc = func(*http.Server, context.Context) error {
		return errors.New("synthetic shutdown failure")
	}

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
	oldShutdownH3 := shutdownH3ServerFunc
	t.Cleanup(func() { shutdownH3ServerFunc = oldShutdownH3 })
	shutdownH3ServerFunc = func(*http3.Server, context.Context) error {
		return errors.New("synthetic HTTP/3 shutdown failure")
	}

	quit := make(chan os.Signal, 1)
	done := make(chan error, 1)
	go func() {
		done <- runServer(&config.Config{Port: "0", H3Enabled: true, H3Port: "not-a-port"}, gin.New(), slog.New(slog.NewTextHandler(os.Stderr, nil)), quit)
	}()
	time.Sleep(100 * time.Millisecond)
	quit <- os.Interrupt

	select {
	case err := <-done:
		require.NoError(t, err)
	case <-time.After(2 * time.Second):
		t.Fatal("runServer with invalid HTTP/3 address did not shut down")
	}
}
