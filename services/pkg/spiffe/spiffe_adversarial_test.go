package spiffe

import (
	"context"
	"log/slog"
	"os"
	"testing"
	"time"
)

func TestMissingSocketBehavior(t *testing.T) {
	logger := slog.New(slog.NewJSONHandler(os.Stdout, nil))
	cfg := Config{
		Enabled:        true,
		SocketPath:     "/tmp/nonexistent_spire_agent_socket_for_test.sock",
		TrustDomain:    "university.ecosystem",
		ConnectTimeout: 100 * time.Millisecond,
	}

	client, err := NewClient(context.Background(), cfg, logger)
	if err == nil {
		t.Fatalf("expected error connecting to non-existent SPIRE socket, got nil error")
	}
	if client != nil {
		t.Fatalf("expected nil client when connection fails")
	}
}

func TestInvalidSelfSPIFFEID(t *testing.T) {
	logger := slog.New(slog.NewJSONHandler(os.Stdout, nil))
	cfg := Config{
		Enabled:        true,
		TrustDomain:    "university.ecosystem",
		MySpiffeID:     "not-a-spiffe-uri",
		ConnectTimeout: 100 * time.Millisecond,
	}

	_, err := NewClient(context.Background(), cfg, logger)
	if err == nil {
		t.Fatalf("expected error for invalid MySpiffeID")
	}
}

func TestServerTLSConfigInvalidAllowedClient(t *testing.T) {
	client := &Client{
		source: nil, // uninitialized
	}
	_, err := client.ServerTLSConfig("invalid-spiffe-id")
	if err == nil {
		t.Fatalf("expected error when spiffe client source is nil")
	}
}

func TestClientTLSConfigInvalidServerID(t *testing.T) {
	client := &Client{
		source: nil,
	}
	_, err := client.ClientTLSConfig("invalid-spiffe-id")
	if err == nil {
		t.Fatalf("expected error when spiffe client source is nil")
	}
}
