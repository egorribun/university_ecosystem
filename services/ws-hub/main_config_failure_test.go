package main

import (
	"context"
	"errors"
	"log/slog"
	"path/filepath"
	"strings"
	"testing"

	sdktrace "go.opentelemetry.io/otel/sdk/trace"

	"github.com/nats-io/nats.go"
	"github.com/university-ecosystem/ws-hub/pkg/config"
)

func TestRun_FailsClosedOnConfiguredSecretFileBeforeExternalStartup(t *testing.T) {
	resetBootstrapSeams(t)
	missingPath := filepath.Join(t.TempDir(), "missing-nats-url")
	t.Setenv("NATS_URL_FILE", missingPath)

	natsCalled := false
	tracerCalled := false
	initTracerFunc = func(context.Context, *config.Config) (*sdktrace.TracerProvider, error) {
		tracerCalled = true
		return nil, nil
	}
	setTestInitNATS(t, func(context.Context, *config.Config, *slog.Logger) (*nats.Conn, error) {
		natsCalled = true
		return nil, errors.New("NATS must not initialize after config failure")
	})

	err := run()

	if err == nil {
		t.Fatal("run() accepted a missing configured NATS secret file")
	}
	if natsCalled {
		t.Fatal("NATS initialized after configuration failed")
	}
	if tracerCalled {
		t.Fatal("tracing initialized after configuration failed")
	}
	if !strings.Contains(err.Error(), "NATS_URL_FILE") || strings.Contains(err.Error(), missingPath) {
		t.Fatalf("run() returned an unexpected or path-disclosing config error: %v", err)
	}
}
