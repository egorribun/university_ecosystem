package spiffe

import (
	"context"
	"log/slog"
	"os"
	"testing"
	"time"
)

func TestDisabledClient(t *testing.T) {
	logger := slog.New(slog.NewJSONHandler(os.Stdout, nil))
	cfg := Config{
		Enabled: false,
	}

	client, err := NewClient(context.Background(), cfg, logger)
	if err != nil {
		t.Fatalf("unexpected error creating disabled client: %v", err)
	}
	if client != nil {
		t.Fatalf("expected nil client when Enabled is false")
	}

	err = client.Close()
	if err != nil {
		t.Fatalf("unexpected error closing nil client: %v", err)
	}
}

func TestInvalidTrustDomain(t *testing.T) {
	logger := slog.New(slog.NewJSONHandler(os.Stdout, nil))
	cfg := Config{
		Enabled:        true,
		TrustDomain:    "invalid trust domain with spaces!",
		ConnectTimeout: 100 * time.Millisecond,
	}

	_, err := NewClient(context.Background(), cfg, logger)
	if err == nil {
		t.Fatalf("expected error for invalid trust domain")
	}
}
