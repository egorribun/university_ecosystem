//go:build integration

package hub

import (
	"context"
	"encoding/json"
	"testing"
	"time"
)

func TestIntegration_ClientHandleMessage_JetStreamFallback(t *testing.T) {
	nc, cleanup := startNATSContainer(t)
	t.Cleanup(cleanup)

	// Subscribe to raw NATS topic to verify fallback delivery
	sub, err := nc.SubscribeSync("chat.fallback-room")
	if err != nil {
		t.Fatalf("Failed to subscribe to core NATS: %v", err)
	}
	defer sub.Unsubscribe()

	h := newIntegrationHub(t, nc, 16, 10)
	ctx, cancel := context.WithCancel(context.Background())
	t.Cleanup(cancel)

	client := &Client{
		ID:     "client-fallback",
		UserID: "user-fallback",
		Rooms:  map[string]bool{"fallback-room": true},
		Send:   make(chan []byte, 10),
		Hub:    h,
		ctx:    ctx,
	}

	h.handleRegister(ctx, client)

	// Construct message
	msg := Message{
		Type:    "message",
		Room:    "fallback-room",
		Payload: json.RawMessage(`{"text":"test fallback"}`),
	}
	raw, _ := json.Marshal(msg)

	// In the testcontainer, JetStream is NOT enabled.
	// handleMessage will try JetStream(), fail, and fallback to core NATS Publish.
	client.handleMessage(msg, raw)

	// Wait for the message on the NATS subscription
	receivedMsg, err := sub.NextMsg(2 * time.Second)
	if err != nil {
		t.Fatalf("Failed to receive fallback message on core NATS: %v", err)
	}

	var canonical Message
	if err := json.Unmarshal(receivedMsg.Data, &canonical); err != nil {
		t.Fatalf("Failed to decode canonical NATS payload: %v", err)
	}
	if canonical.From != client.UserID || canonical.Room != msg.Room {
		t.Errorf("Expected authenticated sender %q in room %q, got %+v", client.UserID, msg.Room, canonical)
	}
}
