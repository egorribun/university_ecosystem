package spiffe

import (
	"context"
	"log/slog"
	"os"
	"testing"
	"time"
)

func TestUninitializedClient(t *testing.T) {
	var client *Client

	if err := client.Close(); err != nil {
		t.Errorf("expected nil error closing nil client, got %v", err)
	}
	if src := client.Source(); src != nil {
		t.Errorf("expected nil source for nil client, got %v", src)
	}

	if _, err := client.ServerTLSConfig(); err == nil {
		t.Errorf("expected error from ServerTLSConfig on nil client")
	}
	if _, err := client.ClientTLSConfig("spiffe://university.ecosystem/ns/default/sa/app"); err == nil {
		t.Errorf("expected error from ClientTLSConfig on nil client")
	}
	if _, err := client.GRPCCerverCredentials(); err == nil {
		t.Errorf("expected error from GRPCCerverCredentials on nil client")
	}
	if _, err := client.GRPCClientCredentials("spiffe://university.ecosystem/ns/default/sa/app"); err == nil {
		t.Errorf("expected error from GRPCClientCredentials on nil client")
	}
}

func TestInvalidIDsInTLSConfig(t *testing.T) {
	client := &Client{
		source: nil, // We test validation before source is called if uninitialized check passes
	}

	// Nil source check
	_, err := client.ServerTLSConfig("invalid spiffe id")
	if err == nil {
		t.Errorf("expected error for nil source in ServerTLSConfig")
	}

	_, err = client.ClientTLSConfig("invalid spiffe id")
	if err == nil {
		t.Errorf("expected error for nil source in ClientTLSConfig")
	}
}

func TestNewClientTimeoutOnMissingSocket(t *testing.T) {
	logger := slog.New(slog.NewJSONHandler(os.Stdout, nil))
	cfg := Config{
		Enabled:        true,
		SocketPath:     "unix:///nonexistent/path/spire-agent.sock",
		TrustDomain:    "university.ecosystem",
		ConnectTimeout: 100 * time.Millisecond,
	}

	ctx, cancel := context.WithTimeout(context.Background(), 500*time.Millisecond)
	defer cancel()

	_, err := NewClient(ctx, cfg, logger)
	if err == nil {
		t.Fatalf("expected connection error for nonexistent socket path")
	}
}
