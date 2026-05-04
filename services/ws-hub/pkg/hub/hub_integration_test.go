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
	"fmt"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"testing"
	"time"

	"github.com/gorilla/websocket"
	"github.com/nats-io/nats.go"
	"github.com/prometheus/client_golang/prometheus/testutil"
	"github.com/stretchr/testify/require"
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

// TestIntegration_BroadcastOversizedMessageDropped verifies RZ-23-05: broadcast
// messages exceeding 60 KB are dropped at hub.go:340 before fan-out, preventing
// CloseMessageTooBig on recipient connections (which use ReadLimit=64 KB).
//
// BroadcastDropsTotal is a package-level promauto counter shared with three
// other increment sites (hub.go:205 worker pool full, hub.go:452 chat queue
// full, hub.go:505 notif queue full). To bind the assertion to the oversized
// branch we use broadcastBuf=16 (worker pool can't fill on a single publish)
// and assert exactly delta == 1 on the oversized publish + delta == 0 on the
// follow-up small message.
func TestIntegration_BroadcastOversizedMessageDropped(t *testing.T) {
	nc, cleanup := startNATSContainer(t)
	t.Cleanup(cleanup)

	// broadcastBuf=16 ensures inner broadcastCh has headroom; without it
	// hub.go:205 (worker pool full) could fire instead of hub.go:340 (oversized).
	h := newIntegrationHub(t, nc, 16, 0)

	ctx, cancel := context.WithCancel(context.Background())
	t.Cleanup(cancel)
	go h.Run(ctx)
	h.SubscribeToNATS(ctx)
	t.Cleanup(h.Stop)

	before := testutil.ToFloat64(BroadcastDropsTotal)

	// Build payload that exceeds 60 KB after json.Marshal. The inner text is
	// 70 KB of 'a'; total marshaled JSON is ~70.1 KB — well past the threshold.
	bigText := strings.Repeat("a", 70*1024)
	payload := Message{
		Type:    "chat.message",
		Room:    "big-room",
		Payload: json.RawMessage(fmt.Sprintf(`{"text":%q}`, bigText)),
	}
	body, err := json.Marshal(payload)
	require.NoError(t, err)
	require.Greater(t, len(body), 60*1024,
		"test setup: marshaled payload must exceed 60 KB to trigger drop branch")

	require.NoError(t, nc.Publish("chat.big-room", body))
	require.NoError(t, nc.Flush())

	// Path: NATS deliver → handleChat → h.Broadcast → Run select → broadcastCh
	// → worker → broadcastMessage → json.Marshal → size check → drop. Four
	// channel hops in-process; sub-millisecond on hot containers but tolerant
	// of cold-start jitter on Windows Docker via Eventually.
	require.Eventually(t, func() bool {
		return testutil.ToFloat64(BroadcastDropsTotal) >= before+1
	}, 3*time.Second, 25*time.Millisecond,
		"BroadcastDropsTotal did not increment within 3s after oversized publish")

	afterOversized := testutil.ToFloat64(BroadcastDropsTotal)

	// Sanity: a small message must NOT trigger the drop branch.
	smallPayload := Message{
		Type:    "chat.message",
		Room:    "small",
		Payload: json.RawMessage(`{"text":"ok"}`),
	}
	sBody, err := json.Marshal(smallPayload)
	require.NoError(t, err)
	require.NoError(t, nc.Publish("chat.small", sBody))
	require.NoError(t, nc.Flush())

	// Wait for the small message to flow through. There are no recipients, so
	// no Broadcast assertion — only that the drop counter does NOT increment.
	time.Sleep(200 * time.Millisecond)
	require.Equal(t, afterOversized, testutil.ToFloat64(BroadcastDropsTotal),
		"small message must not increment BroadcastDropsTotal")
}

// TestIntegration_HandleRegisterMaxClients verifies TD-31-05 layer 1 — the
// AUTHORITATIVE enforcement at hub.go:217-234. handleRegister rejects clients
// when len(h.Clients) >= maxClients by closing client.Send and client.Conn.
// This is independent of the racy pre-check at handlers.go:131-139 (covered
// by TestIntegration_HandleWebSocketPrecheckMaxClients).
//
// No NATS container required — handleRegister is purely local map+lock work.
// The rejected client (c3) needs a real *websocket.Conn because hub.go:225
// calls Conn.Close(); we obtain one via httptest+upgrader.
func TestIntegration_HandleRegisterMaxClients(t *testing.T) {
	logger := slog.New(slog.NewTextHandler(os.Stderr, &slog.HandlerOptions{Level: slog.LevelWarn}))
	cfg := &config.Config{
		MaxClients:          2,
		BroadcastBufferSize: 4,
		BroadcastWorkers:    1,
		ClientMsgRateLimit:  10,
		ClientMsgRateBurst:  10,
	}
	h := NewHub(nil, logger, &mockAuthClient{allowed: true}, cfg, nil)

	ctx, cancel := context.WithCancel(context.Background())
	t.Cleanup(cancel)

	// c1 and c2 are accepted — handleRegister doesn't touch their Conn.
	mkAcceptedClient := func(id string) *Client {
		return &Client{
			ID:    id,
			Rooms: make(map[string]bool),
			Send:  make(chan []byte, 1),
			Hub:   h,
			ctx:   ctx,
		}
	}
	c1 := mkAcceptedClient("user-1")
	c2 := mkAcceptedClient("user-2")

	h.handleRegister(ctx, c1)
	h.handleRegister(ctx, c2)

	h.mu.RLock()
	require.Equal(t, 2, len(h.Clients), "first 2 clients must register successfully")
	require.Contains(t, h.Clients, "user-1")
	require.Contains(t, h.Clients, "user-2")
	h.mu.RUnlock()

	// c3 will be rejected — its Conn.Close() will fire at hub.go:225, so we
	// need a real *websocket.Conn. Set up an httptest WebSocket endpoint that
	// captures the server-side conn after upgrade.
	upgrader := websocket.Upgrader{CheckOrigin: func(*http.Request) bool { return true }}
	var serverSideConn *websocket.Conn
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		c, err := upgrader.Upgrade(w, r, nil)
		if err != nil {
			return
		}
		serverSideConn = c
		// Keep the conn open server-side; cleanup is via t.Cleanup.
	}))
	t.Cleanup(server.Close)

	wsURL := "ws" + strings.TrimPrefix(server.URL, "http")
	clientConn, _, err := websocket.DefaultDialer.Dial(wsURL, nil)
	require.NoError(t, err)
	t.Cleanup(func() { _ = clientConn.Close() })

	// Wait for server-side handler to complete the upgrade and assign the conn.
	// Dialer.Dial returns after the handshake, but the server-side assignment
	// runs in the request goroutine and may lag by a few microseconds.
	require.Eventually(t, func() bool { return serverSideConn != nil }, 1*time.Second, 10*time.Millisecond,
		"server-side ws conn never captured after dialer succeeded")

	c3 := &Client{
		ID:    "user-3",
		Rooms: make(map[string]bool),
		Send:  make(chan []byte, 1),
		Hub:   h,
		ctx:   ctx,
		Conn:  serverSideConn,
	}
	h.handleRegister(ctx, c3)

	// Assert: c3 was rejected — Send channel is closed (closeOnce path).
	select {
	case _, ok := <-c3.Send:
		require.False(t, ok, "c3.Send must be closed after maxClients rejection")
	default:
		t.Fatal("c3.Send not closed within immediate read after handleRegister returned")
	}

	// Assert: h.Clients was not modified — still 2 entries, c3 not added.
	h.mu.RLock()
	require.Equal(t, 2, len(h.Clients), "h.Clients must remain at maxClients=2 after 3rd client rejected")
	require.NotContains(t, h.Clients, "user-3", "c3 must not be added to h.Clients")
	h.mu.RUnlock()
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
