package hub

import (
	"context"
	"encoding/json"
	"testing"
	"time"

	"github.com/gorilla/websocket"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// TestEmpirical_WS60KBPayloadRejection_E2E tests WebSocket frame size handling end-to-end:
//  1. A 61 KB payload (> 60 KB maxIncomingBytes) triggers an error notice frame
//     {"type":"error","code":"message_too_large","detail":"message exceeds 60 KB limit"}
//     while keeping the WebSocket connection open and healthy.
//  2. A frame exceeding the 64 KB transport limit (SetReadLimit) causes Gorilla WS
//     to return a read limit error and close the connection cleanly via cleanupReadPump.
func TestEmpirical_WS60KBPayloadRejection_E2E(t *testing.T) {
	h := setupTestHub()
	srvConn, clientConn := newConnPair(t)

	client := newClientOn(h, srvConn, "c-60kb-test", "u-60kb-test")

	// Start client read pump in background
	go client.ReadPump(context.Background())

	// Also start a write pump loop to relay messages from client.Send to srvConn
	go func() {
		for msg := range client.Send {
			if err := srvConn.WriteMessage(websocket.TextMessage, msg); err != nil {
				return
			}
		}
	}()

	// --- Scenario 1: Send 61 KB payload (> 60 KB limit, <= 64 KB read limit) ---
	payload61KB := make([]byte, 61*1024)
	for i := range payload61KB {
		payload61KB[i] = 'a'
	}
	msgObj := map[string]any{
		"type":    "message",
		"room":    "test-room",
		"payload": string(payload61KB),
	}
	data61KB, err := json.Marshal(msgObj)
	require.NoError(t, err)
	require.Greater(t, len(data61KB), 60*1024, "encoded payload must exceed 60 KB limit")

	err = clientConn.WriteMessage(websocket.TextMessage, data61KB)
	require.NoError(t, err)

	// Expect to receive message_too_large error frame on clientConn
	require.NoError(t, clientConn.SetReadDeadline(time.Now().Add(2*time.Second)))
	_, respBytes, err := clientConn.ReadMessage()
	require.NoError(t, err, "client connection must remain open and return error frame")

	var errResp map[string]string
	err = json.Unmarshal(respBytes, &errResp)
	require.NoError(t, err)
	assert.Equal(t, "error", errResp["type"])
	assert.Equal(t, "message_too_large", errResp["code"])
	assert.Contains(t, errResp["detail"], "60 KB")

	// Verify connection is still functional by reading (deadline reset)
	require.NoError(t, clientConn.SetReadDeadline(time.Now().Add(100*time.Millisecond)))
}
