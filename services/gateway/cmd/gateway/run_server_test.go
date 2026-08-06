package main

import (
	"log/slog"
	"os"
	"testing"
	"time"

	"github.com/gin-gonic/gin"
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
