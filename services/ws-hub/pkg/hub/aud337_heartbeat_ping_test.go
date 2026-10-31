package hub

import (
	"context"
	"encoding/json"
	"errors"
	"net"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	"github.com/gorilla/websocket"
	"github.com/prometheus/client_golang/prometheus/testutil"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func aud337ValidNonce() string { return strings.Repeat("a", 32) }

func newAUD337Hub() (*Hub, *atomic.Int32) {
	h := setupTestHub()
	var revocationChecks atomic.Int32
	h.sessionRevocationCheck = func(context.Context, string) error {
		revocationChecks.Add(1)
		return nil
	}
	return h, &revocationChecks
}

func startAUD337Client(
	t *testing.T,
	h *Hub,
	sendBuffer int,
	startWriter bool,
) (*Client, *websocket.Conn) {
	client, conn, _ := startAUD337ClientWithBeforePumps(t, h, sendBuffer, startWriter, nil)
	return client, conn
}

func startAUD337ClientWithBeforePumps(
	t *testing.T,
	h *Hub,
	sendBuffer int,
	startWriter bool,
	beforePumps func(*Client, <-chan struct{}),
) (*Client, *websocket.Conn, <-chan struct{}) {
	t.Helper()

	runCtx, cancelRun := context.WithCancel(context.Background())
	runDone := make(chan struct{})
	go func() {
		defer close(runDone)
		h.Run(runCtx)
	}()
	require.Eventually(t, func() bool {
		ctx := hubLifecycleContext(h)
		return ctx != nil && ctx.Err() == nil
	}, 2*time.Second, 10*time.Millisecond, "Hub.Run should publish its live context")

	serverConn, clientConn := newConnPair(t)
	client := newClientOn(h, serverConn, "aud337-client", "aud337-user")
	if sendBuffer >= 0 {
		client.Send = make(chan []byte, sendBuffer)
	}
	h.Register <- client
	require.Eventually(t, func() bool {
		h.mu.RLock()
		defer h.mu.RUnlock()
		return h.Clients[client.ID] == client
	}, 2*time.Second, 10*time.Millisecond, "Hub.Run should register the real transport client")

	writeDone := make(chan struct{})
	if beforePumps != nil {
		beforePumps(client, writeDone)
	}

	readDone := make(chan struct{})
	go func() {
		defer close(readDone)
		client.ReadPump(client.ctx)
	}()

	if startWriter {
		go func() {
			defer close(writeDone)
			client.WritePump()
		}()
	} else {
		close(writeDone)
	}

	t.Cleanup(func() {
		_ = clientConn.Close()
		select {
		case <-readDone:
		case <-time.After(2 * time.Second):
			t.Errorf("ReadPump did not exit during cleanup")
		}
		select {
		case <-writeDone:
		case <-time.After(2 * time.Second):
			t.Errorf("WritePump did not exit during cleanup")
		}
		cancelRun()
		select {
		case <-runDone:
		case <-time.After(2 * time.Second):
			t.Errorf("Hub.Run did not exit during cleanup")
		}
	})

	return client, clientConn, writeDone
}

func installAUD337WriterCancelBarrier(
	t *testing.T,
	client *Client,
	writerDone <-chan struct{},
) {
	originalCancel := client.cancel
	client.cancel = func() {
		originalCancel()
		select {
		case <-writerDone:
		case <-time.After(2 * time.Second):
			t.Error("WritePump did not finish after cancellation")
		}
	}
}

func sendAUD337Text(t *testing.T, conn *websocket.Conn, payload string) {
	t.Helper()
	require.NoError(t, conn.WriteMessage(websocket.TextMessage, []byte(payload)))
}

func readAUD337JSON(t *testing.T, conn *websocket.Conn) ([]byte, map[string]any) {
	t.Helper()
	require.NoError(t, conn.SetReadDeadline(time.Now().Add(2*time.Second)))
	messageType, payload, err := conn.ReadMessage()
	require.NoError(t, err)
	require.Equal(t, websocket.TextMessage, messageType)
	var decoded map[string]any
	require.NoError(t, json.Unmarshal(payload, &decoded))
	return payload, decoded
}

func assertAUD337NoData(t *testing.T, conn *websocket.Conn) {
	t.Helper()
	require.NoError(t, conn.SetReadDeadline(time.Now().Add(100*time.Millisecond)))
	_, _, err := conn.ReadMessage()
	var networkError net.Error
	if !errors.As(err, &networkError) {
		t.Fatalf("expected a network timeout error, got %T: %v", err, err)
	}
	if networkError == nil {
		t.Fatal("expected errors.As to provide a network timeout error")
	}
	if !networkError.Timeout() {
		t.Fatalf("expected no queued WebSocket response, got non-timeout error: %v", err)
	}
}

func TestAUD337HeartbeatPingEchoesNonceOverRealHubTransport(t *testing.T) {
	h, revocationChecks := newAUD337Hub()
	client, conn := startAUD337Client(t, h, 8, true)

	sendAUD337Text(t, conn, `{"type":"heartbeat_ping","nonce":"`+aud337ValidNonce()+`"}`)
	payload, response := readAUD337JSON(t, conn)
	require.JSONEq(t, `{"type":"heartbeat_pong","nonce":"`+aud337ValidNonce()+`"}`, string(payload))
	require.Equal(t, "heartbeat_pong", response["type"])
	require.Equal(t, aud337ValidNonce(), response["nonce"])
	require.EqualValues(t, 1, revocationChecks.Load(), "the action must be authorized before pong")
	assert.Empty(t, client.Rooms, "heartbeat must not change client room membership")
	h.mu.RLock()
	assert.Empty(t, h.Rooms, "heartbeat must not create or mutate a room")
	h.mu.RUnlock()
	assert.Nil(t, h.Nats, "the test hub has no NATS connection; heartbeat must stay local")
}

func TestAUD337HeartbeatPingRejectsInvalidNonceOverRealHubTransport(t *testing.T) {
	cases := []struct {
		name  string
		frame string
	}{
		{name: "missing", frame: `{"type":"heartbeat_ping"}`},
		{name: "malformed_type", frame: `{"type":"heartbeat_ping","nonce":123}`},
		{name: "overlong", frame: `{"type":"heartbeat_ping","nonce":"` + strings.Repeat("a", 33) + `"}`},
		{name: "nonhex", frame: `{"type":"heartbeat_ping","nonce":"` + strings.Repeat("g", 32) + `"}`},
		{name: "uppercase_hex", frame: `{"type":"heartbeat_ping","nonce":"` + strings.ToUpper(aud337ValidNonce()) + `"}`},
	}

	for _, testCase := range cases {
		t.Run(testCase.name, func(t *testing.T) {
			h, revocationChecks := newAUD337Hub()
			client, conn := startAUD337Client(t, h, 8, true)

			sendAUD337Text(t, conn, testCase.frame)
			payload, response := readAUD337JSON(t, conn)
			require.Less(t, len(payload), 256, "invalid input error must stay bounded")
			require.Equal(t, "error", response["type"])
			require.Equal(t, "invalid_heartbeat_nonce", response["code"])
			require.Equal(t, "heartbeat nonce must be 32 lowercase hexadecimal characters", response["detail"])
			require.EqualValues(t, 1, revocationChecks.Load(), "invalid nonce handling follows revocation authorization")
			require.Empty(t, client.Rooms)
			h.mu.RLock()
			require.Empty(t, h.Rooms)
			h.mu.RUnlock()

			sendAUD337Text(t, conn, `{"type":"heartbeat_ping","nonce":"`+aud337ValidNonce()+`"}`)
			pongPayload, pong := readAUD337JSON(t, conn)
			require.JSONEq(t, `{"type":"heartbeat_pong","nonce":"`+aud337ValidNonce()+`"}`, string(pongPayload))
			require.Equal(t, aud337ValidNonce(), pong["nonce"], "invalid values must not poison the next valid ping")
			require.EqualValues(t, 2, revocationChecks.Load())
		})
	}
}

func TestAUD337UnknownHeartbeatTypesRemainRejected(t *testing.T) {
	h, revocationChecks := newAUD337Hub()
	_, conn := startAUD337Client(t, h, 8, true)
	before := testutil.ToFloat64(UnknownMsgTypeTotal)
	for _, messageType := range []string{"heartbeat_pong", "heartbeat", "ping", "unknown"} {
		sendAUD337Text(t, conn, `{"type":"`+messageType+`","nonce":"`+aud337ValidNonce()+`"}`)
	}
	require.Eventually(t, func() bool {
		return testutil.ToFloat64(UnknownMsgTypeTotal) >= before+4
	}, 2*time.Second, 10*time.Millisecond)
	require.Zero(t, revocationChecks.Load(), "unknown types must be rejected before action authorization")
	assertAUD337NoData(t, conn)
	h.mu.RLock()
	assert.Empty(t, h.Rooms)
	h.mu.RUnlock()
}

func TestAUD337HeartbeatPingConsumesPerClientRateLimit(t *testing.T) {
	h, revocationChecks := newAUD337Hub()
	h.clientMsgRateLimit = 1e-9
	h.clientMsgRateBurst = 1
	_, conn := startAUD337Client(t, h, 8, true)

	sendAUD337Text(t, conn, `{"type":"heartbeat_ping","nonce":"`+aud337ValidNonce()+`"}`)
	_, first := readAUD337JSON(t, conn)
	require.Equal(t, "heartbeat_pong", first["type"])

	sendAUD337Text(t, conn, `{"type":"heartbeat_ping","nonce":"`+aud337ValidNonce()+`"}`)
	_, limited := readAUD337JSON(t, conn)
	require.Equal(t, "rate_limit_exceeded", limited["type"])
	require.EqualValues(t, 1, revocationChecks.Load(), "rate-limited frames must not reach the revocation check")
}

func TestAUD337HeartbeatPingOversizeStillPrecedesRateAndRevocationChecks(t *testing.T) {
	h, revocationChecks := newAUD337Hub()
	h.clientMsgRateLimit = 1e-9
	h.clientMsgRateBurst = 1
	_, conn := startAUD337Client(t, h, 8, true)

	oversized := `{"type":"heartbeat_ping","nonce":"` + strings.Repeat("a", 61*1024) + `"}`
	require.Greater(t, len(oversized), 60*1024)
	require.Less(t, len(oversized), 64*1024, "the frame must reach the app guard, not the transport limit")
	sendAUD337Text(t, conn, oversized)
	_, tooLarge := readAUD337JSON(t, conn)
	require.Equal(t, "error", tooLarge["type"])
	require.Equal(t, "message_too_large", tooLarge["code"])
	require.EqualValues(t, 1, revocationChecks.Load(), "the queued oversized-frame error is authorized on delivery")

	sendAUD337Text(t, conn, `{"type":"heartbeat_ping","nonce":"`+aud337ValidNonce()+`"}`)
	_, pong := readAUD337JSON(t, conn)
	require.Equal(t, "heartbeat_pong", pong["type"], "oversized frame must be dropped before spending a rate token")
	require.EqualValues(t, 2, revocationChecks.Load(), "one outbound error delivery plus the valid inbound ping")
}

func TestAUD337HeartbeatPingFailClosesAfterRevocationCheck(t *testing.T) {
	h, _ := newAUD337Hub()
	var revocationChecks atomic.Int32
	h.sessionRevocationCheck = func(context.Context, string) error {
		revocationChecks.Add(1)
		return errors.New("revocation backend denied")
	}
	client, conn, _ := startAUD337ClientWithBeforePumps(t, h, 8, true, func(client *Client, writerDone <-chan struct{}) {
		installAUD337WriterCancelBarrier(t, client, writerDone)
	})

	sendAUD337Text(t, conn, `{"type":"heartbeat_ping","nonce":"`+aud337ValidNonce()+`"}`)
	require.Eventually(t, func() bool { return client.sessionRevoked.Load() }, 2*time.Second, 10*time.Millisecond)
	require.NoError(t, conn.SetReadDeadline(time.Now().Add(2*time.Second)))
	_, _, err := conn.ReadMessage()
	require.Error(t, err)
	require.True(t, websocket.IsCloseError(err, websocket.ClosePolicyViolation), "revoked session must not receive pong")
	require.EqualValues(t, 1, revocationChecks.Load())
	h.mu.RLock()
	require.Empty(t, h.Rooms)
	h.mu.RUnlock()
}

func TestAUD337BatchDisconnectPathsPreserveRequestedCloseCode(t *testing.T) {
	tests := []struct {
		name       string
		closeCode  int
		disconnect func(*Hub, *Client)
	}{
		{
			name:      "session revocation",
			closeCode: websocket.ClosePolicyViolation,
			disconnect: func(h *Hub, client *Client) {
				h.disconnectSessionContext(context.Background(), client.SessionJTI, websocket.ClosePolicyViolation, "Session revoked")
			},
		},
		{
			name:      "user disconnect",
			closeCode: websocket.ClosePolicyViolation,
			disconnect: func(h *Hub, client *Client) {
				h.DisconnectUser(client.UserID, websocket.ClosePolicyViolation, "Session revoked")
			},
		},
		{
			name:      "hub shutdown",
			closeCode: websocket.CloseGoingAway,
			disconnect: func(h *Hub, _ *Client) {
				h.closeActiveClients(context.Background())
			},
		},
		{
			name:      "shutdown after stopped eviction",
			closeCode: websocket.CloseGoingAway,
			disconnect: func(h *Hub, client *Client) {
				h.stopped.Store(true)
				h.scheduleClientEviction(client)
				h.closeActiveClients(context.Background())
			},
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			h, _ := newAUD337Hub()
			client, conn, _ := startAUD337ClientWithBeforePumps(t, h, 8, true, func(client *Client, writerDone <-chan struct{}) {
				client.SessionJTI = "aud337-session-jti"
				installAUD337WriterCancelBarrier(t, client, writerDone)
			})

			tt.disconnect(h, client)

			require.NoError(t, conn.SetReadDeadline(time.Now().Add(2*time.Second)))
			_, _, err := conn.ReadMessage()
			require.Error(t, err)
			require.True(t, websocket.IsCloseError(err, tt.closeCode), "client must receive the requested close code")
			h.mu.RLock()
			require.Empty(t, h.Rooms)
			h.mu.RUnlock()
		})
	}
}

func TestAUD337HeartbeatPingUsesNonblockingSendQueue(t *testing.T) {
	t.Run("full queue drops pong", func(t *testing.T) {
		h, revocationChecks := newAUD337Hub()
		checkedSessionJTIs := make(chan string, 2)
		h.sessionRevocationCheck = func(_ context.Context, sessionJTI string) error {
			revocationChecks.Add(1)
			select {
			case checkedSessionJTIs <- sessionJTI:
			default:
			}
			return nil
		}

		serverConn, conn := newConnPair(t)
		client := newClientOn(h, serverConn, "aud337-client", "aud337-user")
		client.Send = make(chan []byte, 1)
		client.Send <- []byte("sentinel")
		client.setupConnection()
		t.Cleanup(client.cancel)

		sendAUD337Text(t, conn, `{"type":"heartbeat_ping","nonce":"`+aud337ValidNonce()+`"}`)
		processed := make(chan bool, 1)
		go func() {
			processed <- client.processNextMessage(client.ctx)
		}()

		// Revocation authorization runs before the heartbeat handler. Waiting for
		// processNextMessage to return proves its safeSend attempt has completed.
		select {
		case continueReading := <-processed:
			require.True(t, continueReading, "a valid heartbeat ping should be processed")
		case <-time.After(2 * time.Second):
			if err := conn.Close(); err != nil {
				t.Errorf("close client socket while settling the processor: %v", err)
			}
			if err := serverConn.Close(); err != nil {
				t.Errorf("close server socket while settling the processor: %v", err)
			}
			// Free the full queue only in failure cleanup, so a regressed blocking
			// send cannot leave the owned processor goroutine behind.
			select {
			case <-client.Send:
			default:
			}
			select {
			case <-processed:
			case <-time.After(2 * time.Second):
				t.Fatal("processNextMessage did not settle after closing the test sockets")
			}
			t.Fatal("processNextMessage did not finish within the bounded nonblocking window")
		}

		require.EqualValues(t, 1, revocationChecks.Load(), "the valid heartbeat must perform one session check")
		require.Len(t, checkedSessionJTIs, 1, "the heartbeat must authorize exactly one retained session")
		require.Equal(t, "test-aud337-client", <-checkedSessionJTIs)
		require.Equal(t, 1, len(client.Send), "the queue must remain full until safeSend has returned")
		require.Equal(t, "sentinel", string(<-client.Send), "full queue must retain its original item")
		require.Empty(t, client.Send, "failed enqueue must not block or append a pong")
		assertAUD337NoData(t, conn)
		assert.Empty(t, client.Rooms, "heartbeat must not change client room membership")
		h.mu.RLock()
		assert.Empty(t, h.Rooms, "heartbeat must not change hub room membership")
		h.mu.RUnlock()
		assert.Nil(t, h.Nats, "heartbeat must remain local")
	})

	t.Run("closed queue does not panic or write directly", func(t *testing.T) {
		h, revocationChecks := newAUD337Hub()
		client, conn := startAUD337Client(t, h, 1, false)
		close(client.Send)

		sendAUD337Text(t, conn, `{"type":"heartbeat_ping","nonce":"`+aud337ValidNonce()+`"}`)
		require.Eventually(t, func() bool { return revocationChecks.Load() == 1 }, 2*time.Second, 10*time.Millisecond)
		assertAUD337NoData(t, conn)
	})
}

func TestAUD337LegacyWebSocketControlPingStillPongs(t *testing.T) {
	h, revocationChecks := newAUD337Hub()
	_, conn := startAUD337Client(t, h, 8, true)
	pongs := make(chan string, 1)
	conn.SetPongHandler(func(appData string) error {
		pongs <- appData
		return nil
	})
	readerDone := make(chan struct{})
	go func() {
		defer close(readerDone)
		for {
			if _, _, err := conn.ReadMessage(); err != nil {
				return
			}
		}
	}()

	require.NoError(t, conn.WriteControl(websocket.PingMessage, []byte("legacy"), time.Now().Add(time.Second)))
	select {
	case pong := <-pongs:
		require.Equal(t, "legacy", pong)
	case <-time.After(2 * time.Second):
		t.Fatal("legacy WebSocket control ping did not receive its pong")
	}
	require.Zero(t, revocationChecks.Load(), "control ping remains a transport control frame")
	require.NoError(t, conn.Close())
	select {
	case <-readerDone:
	case <-time.After(2 * time.Second):
		t.Fatal("control-ping reader did not stop after socket close")
	}
}
