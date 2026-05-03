//go:build integration

// Package hub integration tests, gated behind the `integration` build tag.
//
// Per ADR-022, these tests exercise the ws-hub against real NATS containers
// spun up via testcontainers-go. They are NOT part of the default `go test`
// run (which uses in-process fakes for fast feedback). Run them via:
//
//	make test-integration
//
// Or directly:
//
//	go test -tags integration -timeout 5m ./pkg/hub/...
//
// Docker daemon must be reachable (testcontainers-go fails fast otherwise).
package hub

import (
	"context"
	"encoding/json"
	"log/slog"
	"os"
	"strings"
	"testing"
	"time"

	"github.com/nats-io/nats.go"
	"github.com/testcontainers/testcontainers-go"
	tclog "github.com/testcontainers/testcontainers-go/log"
	tcnats "github.com/testcontainers/testcontainers-go/modules/nats"
	"github.com/university-ecosystem/ws-hub/pkg/config"
)

// startNATSContainer spins up a real NATS server in a Docker container and
// returns a connected nats.Conn plus a cleanup function. The cleanup
// terminates the container and closes the connection — call it via t.Cleanup
// so failures don't leak resources.
func startNATSContainer(t *testing.T) (*nats.Conn, func()) {
	t.Helper()
	ctx := context.Background()

	natsContainer, err := tcnats.Run(ctx,
		"nats:2.12-alpine",
		// JetStream not required for the cache.invalidate / chat.* / notifications.*
		// subjects this test suite covers — they run on core NATS pub/sub.
		// JetStream-specific tests (PERF-22-01 NakWithDelay redelivery) would
		// add `tcnats.WithArgument("jetstream", "")`.
		testcontainers.WithLogger(tclog.TestLogger(t)),
	)
	if err != nil {
		t.Fatalf("nats container start: %v", err)
	}

	connStr, err := natsContainer.ConnectionString(ctx)
	if err != nil {
		_ = natsContainer.Terminate(ctx)
		t.Fatalf("nats connection string: %v", err)
	}

	nc, err := nats.Connect(connStr,
		nats.RetryOnFailedConnect(true),
		nats.MaxReconnects(5),
		nats.ReconnectWait(500*time.Millisecond),
	)
	if err != nil {
		_ = natsContainer.Terminate(ctx)
		t.Fatalf("nats connect: %v", err)
	}

	cleanup := func() {
		nc.Close()
		_ = natsContainer.Terminate(context.Background())
	}
	return nc, cleanup
}

// newIntegrationHub builds a Hub wired to a real NATS connection using the
// existing setupTestHub auth fixture but with a sized Broadcast buffer +
// realistic worker pool. Logger is silenced unless the test fails (slog
// discard), keeping integration test output focused.
func newIntegrationHub(t *testing.T, nc *nats.Conn, broadcastBuf int, maxClients int) *Hub {
	t.Helper()
	logger := slog.New(slog.NewTextHandler(os.Stderr, &slog.HandlerOptions{Level: slog.LevelWarn}))
	cfg := &config.Config{
		MaxClients:          maxClients,
		BroadcastBufferSize: broadcastBuf,
		BroadcastWorkers:    2,
		ClientMsgRateLimit:  100,
		ClientMsgRateBurst:  100,
	}
	return NewHub(nc, logger, &mockAuthClient{allowed: true}, cfg, nil)
}

// TestIntegration_NATSChatMessageDelivery verifies the full pipeline:
//
//	NATS publisher
//	    → Hub.SubscribeToNATS handler (handleChat)
//	    → Hub.Broadcast channel
//
// This is the foundational integration check — it proves testcontainers-go
// successfully launches NATS, the production-path Hub.NewHub + SubscribeToNATS
// can connect to a real broker, and message delivery semantics on the
// `chat.*` subject behave as expected. All in-process unit tests use a nil
// nats.Conn, so this is the first place real broker behaviour is exercised.
func TestIntegration_NATSChatMessageDelivery(t *testing.T) {
	nc, cleanup := startNATSContainer(t)
	t.Cleanup(cleanup)

	h := newIntegrationHub(t, nc, 16, 0)

	ctx, cancel := context.WithCancel(context.Background())
	t.Cleanup(cancel)

	// SubscribeToNATS calls os.Exit(1) on subscription failure. In a
	// correctly wired test container that should never trip.
	h.SubscribeToNATS(ctx)
	t.Cleanup(h.Stop)

	// Publish a chat message on chat.{room_id}; handleChat unmarshals and
	// pushes to h.Broadcast.
	payload := Message{
		Type:    "chat.message",
		Room:    "test-room-1",
		Payload: json.RawMessage(`{"text":"hello from integration"}`),
		From:    "user-1",
	}
	body, err := json.Marshal(payload)
	if err != nil {
		t.Fatalf("marshal payload: %v", err)
	}

	if err := nc.Publish("chat.test-room-1", body); err != nil {
		t.Fatalf("nats publish: %v", err)
	}
	if err := nc.Flush(); err != nil {
		t.Fatalf("nats flush: %v", err)
	}

	// Drain Hub.Broadcast with a deadline. NATS in-memory delivery is
	// effectively instant; 2 s is generous enough to absorb container
	// jitter on slow CI runners.
	select {
	case got := <-h.Broadcast:
		if got.Type != payload.Type {
			t.Errorf("type: want %q got %q", payload.Type, got.Type)
		}
		if got.Room != payload.Room {
			t.Errorf("room: want %q got %q", payload.Room, got.Room)
		}
		if got.From != payload.From {
			t.Errorf("from: want %q got %q", payload.From, got.From)
		}
	case <-time.After(2 * time.Second):
		t.Fatal("timed out waiting for Hub.Broadcast — NATS msg did not propagate to broadcast channel")
	}
}

// TestIntegration_NATSMalformedMessageDropped covers the failure path of
// handleChat: a non-JSON payload on `chat.*` is logged and dropped, NOT
// forwarded to Broadcast. This is a defensive check to make sure malformed
// inbound NATS traffic cannot poison the in-memory broadcast pipeline.
//
// In production a misbehaving publisher could otherwise cause a malformed
// Message{} to reach a connected WebSocket client (panic on JSON marshal
// during broadcastMessage). The handler validates at the parse boundary
// (hub.go:444 json.Unmarshal returns; channel push is skipped).
func TestIntegration_NATSMalformedMessageDropped(t *testing.T) {
	nc, cleanup := startNATSContainer(t)
	t.Cleanup(cleanup)

	h := newIntegrationHub(t, nc, 4, 0)

	ctx, cancel := context.WithCancel(context.Background())
	t.Cleanup(cancel)
	h.SubscribeToNATS(ctx)
	t.Cleanup(h.Stop)

	// Garbage payload that cannot deserialize into Message.
	if err := nc.Publish("chat.bad-room", []byte("not-valid-json{")); err != nil {
		t.Fatalf("nats publish: %v", err)
	}
	if err := nc.Flush(); err != nil {
		t.Fatalf("nats flush: %v", err)
	}

	// Wait briefly — anything on Broadcast in this window is a regression.
	// 200 ms is long enough for the NATS callback to have run on a hot
	// container; the test fails fast in either direction.
	select {
	case got := <-h.Broadcast:
		// Surface the actual content so future regressions debug easily.
		buf, _ := json.Marshal(got)
		t.Fatalf("malformed NATS msg incorrectly reached Broadcast: %s", string(buf))
	case <-time.After(200 * time.Millisecond):
		// Expected path — handler dropped the message at parse boundary.
	}

	// Sanity: subsequent VALID messages still flow. This guards against a
	// regression where a malformed message could permanently break the
	// subscription (the production handler uses recover() to absorb panics
	// — see hub.go:418-423).
	good := Message{Type: "chat.message", Room: "ok", Payload: json.RawMessage(`{}`)}
	body, _ := json.Marshal(good)
	if err := nc.Publish("chat.ok", body); err != nil {
		t.Fatalf("nats publish (recovery): %v", err)
	}
	_ = nc.Flush()

	select {
	case got := <-h.Broadcast:
		if got.Room != "ok" {
			t.Errorf("recovery: want room=ok got %q", got.Room)
		}
	case <-time.After(2 * time.Second):
		t.Fatal("subscription did not recover after malformed message — handleChat panic guard may be broken")
	}
}

// connStrFromEnv is a small helper kept for future tests that need to opt
// out of the per-test container (e.g. when running locally against a
// developer's already-running NATS). Currently unused; kept as part of the
// integration test toolkit.
//
//nolint:unused // intentional: future tests will reuse this hook
func connStrFromEnv() (string, bool) {
	if v := os.Getenv("NATS_TEST_URL"); strings.TrimSpace(v) != "" {
		return v, true
	}
	return "", false
}
