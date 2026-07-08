package hub

// hub_edge_cases_test.go — W17 edge-case coverage for pkg/hub.
//
// Tests in this file are intentionally white-box (same package) so they can
// reach private fields and internal channels without an exported API.
//
// Why these tests are needed:
//   - MaxClients: handleRegister's capacity branch was already exercised in
//     hub_test.go (TestHub_HandleRegister_MaxClientsReject), but that test uses
//     MaxClients=1. This file covers the "101st client" boundary with 100 already
//     admitted to make the business rule explicit.
//   - safeSend full-buffer: the capacity-256 broadcast buffer path is exercised
//     here to confirm no deadlock occurs when a client's Send channel is full.
//   - Empty-room broadcast: collectRecipients must return nil without panicking
//     when the target room has no registered clients.
//   - Concurrent close + send: verifies safeSend's recover() guard prevents data
//     races when Close and Send happen simultaneously.
//   - Per-client rate limit: handleMessage's token-bucket limit notification path
//     is confirmed to produce a rate_limit_exceeded notice.

import (
	"context"
	"encoding/json"
	"sync"
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"go.opentelemetry.io/otel"
)

// ---------------------------------------------------------------------------
// Тест 1: MaxClients — 101-й клиент получает отказ
// ---------------------------------------------------------------------------

// TestHub_MaxClients_101stClientRejected fills the hub to exactly MaxClients
// and verifies that the next connection attempt:
//   - is not admitted to the Clients map
//   - has its Send channel closed (signalling rejection to the caller)
func TestHub_MaxClients_101stClientRejected(t *testing.T) {
	const maxClients = 100

	h := setupTestHub()
	h.maxClients = maxClients
	ctx := context.Background()

	// Register maxClients real websocket connections so the hub is at capacity.
	// We use newConnPair (defined in client_unit_test.go) to get real *websocket.Conn
	// pairs — handleRegister calls client.Conn.Close() on reject, which requires a
	// non-nil Conn to avoid a nil-pointer panic.
	registered := make([]*Client, 0, maxClients)
	for i := 0; i < maxClients; i++ {
		srv, _ := newConnPair(t)
		c := newClientOn(h, srv, generateID(i), "user")
		h.handleRegister(ctx, c)
		registered = append(registered, c)
	}

	h.mu.RLock()
	require.Len(t, h.Clients, maxClients, "precondition: hub must be at capacity")
	h.mu.RUnlock()

	// 101st client — must be rejected.
	srv101, _ := newConnPair(t)
	c101 := newClientOn(h, srv101, "client-101", "user-101")
	h.handleRegister(ctx, c101)

	h.mu.RLock()
	_, in101 := h.Clients["client-101"]
	h.mu.RUnlock()

	assert.False(t, in101, "101st client must not appear in Clients map after rejection")

	// The rejection path calls closeOnce.Do(close(Send)).
	// A receive on a closed, empty channel returns immediately with ok=false.
	select {
	case _, open := <-c101.Send:
		assert.False(t, open, "rejected client's Send channel must be closed")
	default:
		t.Error("expected rejected client's Send channel to be closed")
	}

	// Sanity: Clients count is still exactly maxClients.
	h.mu.RLock()
	assert.Len(t, h.Clients, maxClients)
	h.mu.RUnlock()

	// Cleanup: unregister all admitted clients so test-cleanup goroutines drain.
	for _, c := range registered {
		h.handleUnregister(ctx, c)
	}
}

// generateID produces a unique string ID for admission-filling.
func generateID(i int) string {
	return "fill-client-" + string(rune('a'+i%26)) + string(rune('0'+i/26%10))
}

// ---------------------------------------------------------------------------
// Тест 2: client.Send заполнен (256-буфер) — safeSend дропает без дедлока
// ---------------------------------------------------------------------------

// TestSafeSend_FullBuffer_NoDeadlock verifies that safeSend returns false
// immediately — without blocking — when the target channel is full. The test
// uses a channel sized to match the Hub's default BroadcastBufferSize (256)
// to exercise the production-realistic scenario.
func TestSafeSend_FullBuffer_NoDeadlock(t *testing.T) {
	const bufferSize = 256
	ch := make(chan []byte, bufferSize)

	// Saturate the buffer.
	for i := 0; i < bufferSize; i++ {
		ch <- []byte("fill")
	}

	// safeSend must return false without blocking; if it blocks, the test times out.
	done := make(chan bool, 1)
	go func() {
		sent := safeSend(ch, []byte("overflow"))
		done <- sent
	}()

	select {
	case sent := <-done:
		assert.False(t, sent, "safeSend on a full channel must return false")
	case <-time.After(1 * time.Second):
		t.Fatal("safeSend deadlocked on full channel — test timed out")
	}
}

// ---------------------------------------------------------------------------
// Тест 3: broadcast к room с 0 участников — ничего не происходит
// ---------------------------------------------------------------------------

// TestBroadcast_EmptyRoom_NoOp confirms that sending a broadcast to a room that
// has no registered clients completes without panic and without delivering any
// message. collectRecipients is the unit under test; broadcastMessage wraps it
// but adds NATS/OTel dependencies — testing collectRecipients directly is cleaner.
func TestBroadcast_EmptyRoom_NoOp(t *testing.T) {
	h := setupTestHub()
	ctx := context.Background()

	// The room "ghost-room" is not in h.Rooms — collectRecipients must return nil.
	msg := &Message{Room: "ghost-room", Type: "chat"}
	_, span := otel.Tracer("test").Start(ctx, "test-empty-room")
	defer span.End()

	recipients := h.collectRecipients(msg, span)
	assert.Nil(t, recipients, "collectRecipients for an unknown room must return nil")
	assert.Len(t, recipients, 0, "no recipients for an empty room")

	// Sanity: the Room entry was NOT created by collectRecipients.
	h.mu.RLock()
	_, roomCreated := h.Rooms["ghost-room"]
	h.mu.RUnlock()
	assert.False(t, roomCreated, "collectRecipients must not create a room entry")
}

// ---------------------------------------------------------------------------
// Тест 4: concurrent close + Send — нет data race (run with -race)
// ---------------------------------------------------------------------------

// TestConcurrentClose_Send_NoDataRace exercises safeSend and closeOnce
// concurrently to surface any data race detected by the Go race detector.
// The test must be run with `go test -race` to be meaningful; it also serves
// as a correctness check that neither operation panics.
func TestConcurrentClose_Send_NoDataRace(t *testing.T) {
	const goroutines = 50

	ch := make(chan []byte, 32)
	var closeOnce sync.Once
	var wg sync.WaitGroup

	// Goroutines that continuously try to send.
	for i := 0; i < goroutines; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for j := 0; j < 100; j++ {
				safeSend(ch, []byte("payload"))
				// Brief yield to increase scheduling interleaving.
				time.Sleep(0)
			}
		}()
	}

	// One goroutine closes the channel partway through.
	wg.Add(1)
	go func() {
		defer wg.Done()
		// Let senders start before we close.
		time.Sleep(2 * time.Millisecond)
		closeOnce.Do(func() { safeClose(ch) })
	}()

	// Wait with a timeout so a deadlock fails the test rather than hanging CI.
	done := make(chan struct{})
	go func() {
		wg.Wait()
		close(done)
	}()

	select {
	case <-done:
		// All goroutines finished without panic — success.
	case <-time.After(5 * time.Second):
		t.Fatal("concurrent close+send test timed out — possible deadlock or panic")
	}
}

// ---------------------------------------------------------------------------
// Тест 5: ratelimit превышен per-client
// ---------------------------------------------------------------------------

// TestHandleMessage_RateLimit_PerClient verifies that when a client's token
// bucket is exhausted, handleMessage:
//  1. does NOT forward the message to NATS
//  2. writes a {"type":"rate_limit_exceeded"} JSON notice to client.Send
func TestHandleMessage_RateLimit_PerClient(t *testing.T) {
	h := setupTestHub()
	// Deny all messages from the start by setting rate to 0 tokens/sec with burst 0.
	h.clientMsgRateLimit = 0
	h.clientMsgRateBurst = 0

	srv, _ := newConnPair(t)
	c := newClientOn(h, srv, "rate-test-client", "rate-user")

	data := []byte(`{"type":"message","room":"test-room","payload":{"text":"hello"}}`)
	msg := Message{Type: "message", Room: "test-room"}

	// handleMessage with exhausted bucket must return early without touching NATS.
	// Since NATS is nil, a panic would indicate the rate limit check was bypassed.
	require.NotPanics(t, func() {
		c.handleMessage(msg, data)
	}, "handleMessage must not reach NATS when rate-limited")

	// Confirm the rate_limit_exceeded notice was queued.
	select {
	case notice := <-c.Send:
		var raw map[string]string
		require.NoError(t, json.Unmarshal(notice, &raw), "notice must be valid JSON")
		assert.Equal(t, "rate_limit_exceeded", raw["type"],
			"rate-limited message must produce a rate_limit_exceeded notice")
	default:
		t.Fatal("expected rate_limit_exceeded notice in client.Send channel")
	}
}

// ---------------------------------------------------------------------------
// Тест 6 (бонус): handleUnregister double-call is idempotent
// ---------------------------------------------------------------------------

// TestHub_HandleUnregister_Idempotent verifies that calling handleUnregister
// twice on the same client does not panic (closeOnce ensures the channel is
// closed exactly once) and leaves h.Clients in a consistent state.
func TestHub_HandleUnregister_Idempotent(t *testing.T) {
	h := setupTestHub()
	ctx := context.Background()

	srv, _ := newConnPair(t)
	c := newClientOn(h, srv, "idem-client", "idem-user")
	h.handleRegister(ctx, c)

	h.mu.RLock()
	require.Contains(t, h.Clients, "idem-client", "client must be registered before unregister")
	h.mu.RUnlock()

	// First unregister: normal path.
	assert.NotPanics(t, func() { h.handleUnregister(ctx, c) })
	h.mu.RLock()
	_, stillPresent := h.Clients["idem-client"]
	h.mu.RUnlock()
	assert.False(t, stillPresent, "client must be removed after first unregister")

	// Second unregister: closeOnce must prevent double-close panic.
	assert.NotPanics(t, func() { h.handleUnregister(ctx, c) })
}
