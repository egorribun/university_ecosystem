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

	readDone := make(chan struct{})
	go func() {
		defer close(readDone)
		client.ReadPump(client.ctx)
	}()

	writeDone := make(chan struct{})
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

	return client, clientConn
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
	require.ErrorAs(t, err, &networkError)
	require.True(t, networkError.Timeout(), "expected no queued WebSocket response")
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
	client, conn := startAUD337Client(t, h, 8, true)

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

func TestAUD337HeartbeatPingUsesNonblockingSendQueue(t *testing.T) {
	t.Run("full queue drops pong", func(t *testing.T) {
		h, revocationChecks := newAUD337Hub()
		client, conn := startAUD337Client(t, h, 1, false)
		client.Send <- []byte("sentinel")

		sendAUD337Text(t, conn, `{"type":"heartbeat_ping","nonce":"`+aud337ValidNonce()+`"}`)
		require.Eventually(t, func() bool { return revocationChecks.Load() == 1 }, 2*time.Second, 10*time.Millisecond)
		require.Equal(t, "sentinel", string(<-client.Send), "full queue must retain its original item")
		require.Empty(t, client.Send, "failed enqueue must not block or append a pong")
		assertAUD337NoData(t, conn)
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
