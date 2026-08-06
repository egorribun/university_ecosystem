package main

import (
	"log/slog"
	"os"
	"testing"
	"time"

	"github.com/stretchr/testify/require"
	"github.com/university-ecosystem/ws-hub/pkg/config"
	"github.com/university-ecosystem/ws-hub/pkg/hub"
)

func TestRunServer_ShutsDownOnInjectedSignal(t *testing.T) {
	quit := make(chan os.Signal, 1)
	cfg := &config.Config{
		Port:             "0",
		WebTransportPort: "0",
	}
	logger := slog.New(slog.NewTextHandler(os.Stderr, nil))
	h := hub.NewHub(nil, logger, nil, cfg, nil)

	done := make(chan error, 1)
	go func() {
		done <- runServer(cfg, logger, h, nil, quit)
	}()

	quit <- os.Interrupt

	select {
	case err := <-done:
		require.NoError(t, err)
	case <-time.After(2 * time.Second):
		t.Fatal("runServer did not shut down after the injected signal")
	}
}
