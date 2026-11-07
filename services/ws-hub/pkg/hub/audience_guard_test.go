package hub

import (
	"context"
	"encoding/json"
	"fmt"
	"testing"

	"github.com/nats-io/nats.go"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func audienceFixtureID(number int) string {
	return fmt.Sprintf("00000000-0000-4000-8000-%012x", number)
}

func TestDecodeChatAudiencePresenceAndFailClosedValidation(t *testing.T) {
	tests := []struct {
		name      string
		data      string
		present   bool
		wantIDs   []string
		wantError bool
	}{
		{
			name:    "legacy field is absent",
			data:    `{"room":"room"}`,
			present: false,
		},
		{
			name:    "explicit empty audience denies every recipient",
			data:    `{"room":"room","audience":[]}`,
			present: true,
		},
		{
			name:    "canonical UUID list is retained",
			data:    fmt.Sprintf(`{"room":"room","audience":[%q]}`, audienceFixtureID(1)),
			present: true,
			wantIDs: []string{audienceFixtureID(1)},
		},
		{name: "null is not legacy", data: `{"room":"room","audience":null}`, present: true, wantError: true},
		{name: "wrong type is rejected", data: `{"room":"room","audience":"user"}`, present: true, wantError: true},
		{name: "duplicate top-level field is rejected", data: fmt.Sprintf(`{"room":"room","audience":[%q],"audience":[]}`, audienceFixtureID(1)), present: true, wantError: true},
		{name: "case alias is rejected", data: `{"room":"room","Audience":[]}`, wantError: true},
		{name: "duplicate identity is rejected", data: fmt.Sprintf(`{"audience":[%q,%q]}`, audienceFixtureID(1), audienceFixtureID(1)), present: true, wantError: true},
		{name: "noncanonical identity is rejected", data: `{"audience":["00000000-0000-4000-8000-00000000000A"]}`, present: true, wantError: true},
		{name: "oversized list is rejected", data: oversizedAudienceJSON(t), present: true, wantError: true},
	}

	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			gotIDs, gotPresent, err := decodeChatAudience([]byte(test.data))
			if test.wantError {
				require.Error(t, err)
				return
			}
			require.NoError(t, err)
			assert.Equal(t, test.present, gotPresent)
			assert.Len(t, gotIDs, len(test.wantIDs))
			for _, userID := range test.wantIDs {
				assert.Contains(t, gotIDs, userID)
			}
		})
	}
}

func TestMissingAudienceCheckpointRefreshRequiresMatchingPersistedTypes(t *testing.T) {
	tests := []struct {
		name         string
		envelopeType string
		payloadType  string
		wantRefresh  bool
	}{
		{name: "new message", envelopeType: "new_message", payloadType: "new_message", wantRefresh: true},
		{name: "message edit", envelopeType: "message_edited", payloadType: "message_edited", wantRefresh: true},
		{name: "message deletion", envelopeType: "message_deleted", payloadType: "message_deleted", wantRefresh: true},
		{name: "reaction change", envelopeType: "reaction_changed", payloadType: "reaction_changed", wantRefresh: true},
		{name: "read receipt", envelopeType: "read", payloadType: "read", wantRefresh: true},
		{name: "ephemeral typing", envelopeType: "typing", payloadType: "typing"},
		{name: "unknown event", envelopeType: "future_event", payloadType: "future_event"},
		{name: "type mismatch", envelopeType: "new_message", payloadType: "typing"},
		{name: "missing payload type", envelopeType: "new_message"},
		{name: "case alias", envelopeType: "New_Message", payloadType: "New_Message"},
	}

	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			assert.Equal(t, test.wantRefresh,
				shouldRefreshMissingAudienceCheckpoint(test.envelopeType, test.payloadType))
		})
	}
}

func oversizedAudienceJSON(t *testing.T) string {
	t.Helper()
	userIDs := make([]string, maxChatAudienceMembers+1)
	for index := range userIDs {
		userIDs[index] = audienceFixtureID(index + 1)
	}
	encoded, err := json.Marshal(map[string]any{"audience": userIDs})
	require.NoError(t, err)
	return string(encoded)
}

func TestChatAudienceLiveFilterIntersectsCurrentRoomMembership(t *testing.T) {
	const (
		roomID     = "room"
		allowedID  = "00000000-0000-4000-8000-000000000001"
		staleID    = "00000000-0000-4000-8000-000000000002"
		externalID = "00000000-0000-4000-8000-000000000003"
	)
	h := setupTestHub()
	allowed := &Client{ID: "allowed-conn", UserID: allowedID}
	stale := &Client{ID: "stale-conn", UserID: staleID}
	outsideRoom := &Client{ID: "outside-conn", UserID: externalID}
	h.mu.Lock()
	h.Rooms[roomID] = map[*Client]bool{allowed: true, stale: true}
	h.mu.Unlock()

	data := []byte(fmt.Sprintf(
		`{"type":"new_message","room":"room","payload":{"chat_id":"room"},"audience":[%q,%q]}`,
		allowedID,
		externalID,
	))
	message := &nats.Msg{Subject: "chat.room", Data: data}
	h.processChatDelivery(context.Background(), message, false)

	var delivered *Message
	select {
	case delivered = <-h.Broadcast:
	default:
		t.Fatal("valid audience message was not queued")
	}
	require.True(t, delivered.audiencePresent)
	assert.Contains(t, delivered.audienceUserIDs, allowedID)
	assert.Contains(t, delivered.audienceUserIDs, externalID)

	recipients := h.collectRecipients(delivered, nil)
	require.Len(t, recipients, 1)
	assert.Same(t, allowed, recipients[0].client)
	assert.NotContains(t, recipients, recipient{client: stale})
	assert.NotContains(t, recipients, recipient{client: outsideRoom}, "audience cannot create a room membership")

	encoded, err := json.Marshal(delivered)
	require.NoError(t, err)
	assert.NotContains(t, string(encoded), `"audience"`, "recipient policy must stay off the browser wire")
}

func TestChatAudienceExplicitEmptyDropsLiveMessageAndClientCannotSetPolicy(t *testing.T) {
	h := setupTestHub()
	userID := audienceFixtureID(7)
	client := &Client{ID: "room-member", UserID: userID}
	h.mu.Lock()
	h.Rooms["room"] = map[*Client]bool{client: true}
	h.mu.Unlock()

	h.processChatDelivery(context.Background(), &nats.Msg{
		Subject: "chat.room",
		Data:    []byte(`{"type":"new_message","room":"room","payload":{"chat_id":"room"},"audience":[]}`),
	}, false)
	var delivered *Message
	select {
	case delivered = <-h.Broadcast:
	default:
		t.Fatal("explicit empty audience message was not queued for filtering")
	}
	require.True(t, delivered.audiencePresent)
	assert.Empty(t, h.collectRecipients(delivered, nil))

	var clientMessage Message
	require.NoError(t, json.Unmarshal([]byte(fmt.Sprintf(
		`{"type":"new_message","room":"room","payload":{"chat_id":"room"},"audience":[%q]}`,
		userID,
	)), &clientMessage))
	assert.False(t, clientMessage.audiencePresent, "ordinary client JSON decoding must not authorize an audience")
	assert.Empty(t, clientMessage.audienceUserIDs)
	encoded, err := json.Marshal(clientMessage)
	require.NoError(t, err)
	assert.NotContains(t, string(encoded), `"audience"`)
}

func TestChatAudienceMalformedLiveMessageDoesNotFallBackToRoomBroadcast(t *testing.T) {
	h := setupTestHub()
	h.processChatDelivery(context.Background(), &nats.Msg{
		Subject: "chat.room",
		Data:    []byte(`{"type":"new_message","room":"room","payload":{"chat_id":"room"},"audience":null}`),
	}, false)
	assert.Empty(t, h.Broadcast)
}

func TestChatAudienceMissingLiveEmitsPayloadFreeCheckpoint(t *testing.T) {
	tests := []struct {
		name            string
		reply           string
		requireSequence bool
		wantSequence    uint64
	}{
		{
			name:            "JetStream keeps the server sequence and per-user cursor",
			reply:           "$JS.ACK.CHAT_EVENTS.offline-replay.1.17.17.1690000000000000000.0",
			requireSequence: true,
			wantSequence:    17,
		},
		{
			name: "Core NATS does not invent a cursor",
		},
	}

	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			h := setupTestHub()
			if test.wantSequence > 0 {
				enableSecureReplayForTest(h)
			}
			clients := []*Client{
				{ID: "member-one", UserID: audienceFixtureID(21), Hub: h, ctx: context.Background(), Send: make(chan []byte, 1)},
				{ID: "member-two", UserID: audienceFixtureID(22), Hub: h, ctx: context.Background(), Send: make(chan []byte, 1)},
			}
			h.mu.Lock()
			h.Rooms["room"] = map[*Client]bool{clients[0]: true, clients[1]: true}
			h.mu.Unlock()

			oldAck := jetStreamAckFunc
			t.Cleanup(func() { jetStreamAckFunc = oldAck })
			ackCount := 0
			jetStreamAckFunc = func(*nats.Msg) error { ackCount++; return nil }

			message := &nats.Msg{
				Subject: "chat.room",
				Reply:   test.reply,
				Sub:     &nats.Subscription{},
				Data: []byte(
					`{"type":"new_message","room":"room","seq":999,"resume_token":"publisher-token","payload":{"type":"new_message","chat_id":"room","secret_content":"must-not-reach-browsers"}}`,
				),
			}
			h.processChatDelivery(context.Background(), message, test.requireSequence)
			require.Equal(t, 1, ackCount, "the original NATS row is acknowledged after enqueue")

			var queued *Message
			select {
			case queued = <-h.Broadcast:
			default:
				t.Fatal("missing-audience checkpoint was not queued")
			}
			assert.Equal(t, "room", queued.Room)
			if test.wantSequence > 0 {
				require.NotNil(t, queued.MessageReplayMetadata)
				assert.Equal(t, test.wantSequence, queued.Seq)
				assert.Equal(t, "CHAT_EVENTS", queued.Stream)
			} else {
				assert.Nil(t, queued.MessageReplayMetadata)
			}
			var queuedPayload map[string]any
			require.NoError(t, json.Unmarshal(queued.Payload, &queuedPayload))
			assert.Equal(t, "replay_checkpoint", queuedPayload["type"])
			assert.Equal(t, "room", queuedPayload["chat_id"])
			assert.Equal(t, true, queuedPayload["refresh_required"])
			assert.NotContains(t, string(queued.Payload), "secret_content")

			h.broadcastMessage(context.Background(), queued)
			resumeTokens := make([]string, 0, len(clients))
			for _, client := range clients {
				var frame map[string]any
				select {
				case data := <-client.Send:
					require.NoError(t, json.Unmarshal(data, &frame))
				default:
					t.Fatalf("room member %s did not receive a checkpoint", client.ID)
				}
				assert.Equal(t, "room", frame["room"])
				assert.Equal(t, "new_message", frame["type"], "live envelope retains the original trusted event type")
				payload, ok := frame["payload"].(map[string]any)
				require.True(t, ok)
				assert.Equal(t, "replay_checkpoint", payload["type"])
				assert.Equal(t, "room", payload["chat_id"])
				assert.Equal(t, true, payload["refresh_required"])
				encodedFrame, marshalErr := json.Marshal(frame)
				require.NoError(t, marshalErr)
				assert.NotContains(t, string(encodedFrame), "secret_content")
				assert.NotContains(t, frame, "audience")
				if test.wantSequence > 0 {
					assert.Equal(t, float64(test.wantSequence), frame["seq"])
					token, ok := frame["resume_token"].(string)
					require.True(t, ok)
					require.NotEmpty(t, token)
					assert.NotEqual(t, "publisher-token", token)
					resumeTokens = append(resumeTokens, token)
				} else {
					assert.NotContains(t, frame, "seq")
					assert.NotContains(t, frame, "resume_token")
					assert.NotContains(t, frame, "replayed")
				}
			}
			if test.wantSequence > 0 {
				assert.NotEqual(t, resumeTokens[0], resumeTokens[1], "resume tokens are bound to each user")
			}
		})
	}
}

func TestChatAudienceMissingLiveCheckpointRefreshesPersistedTypes(t *testing.T) {
	for _, eventType := range []string{
		"new_message", "message_edited", "message_deleted", "reaction_changed", "read",
	} {
		t.Run(eventType, func(t *testing.T) {
			h := setupTestHub()
			messageData, err := json.Marshal(map[string]any{
				"type": eventType,
				"room": "room",
				"payload": map[string]any{
					"type":           eventType,
					"chat_id":        "room",
					"secret_content": "must-not-reach-browser",
				},
			})
			require.NoError(t, err)
			h.processChatDelivery(context.Background(), &nats.Msg{
				Subject: "chat.room",
				Data:    messageData,
			}, false)

			var queued *Message
			select {
			case queued = <-h.Broadcast:
			default:
				t.Fatal("missing-audience checkpoint was not queued")
			}
			var checkpoint map[string]any
			require.NoError(t, json.Unmarshal(queued.Payload, &checkpoint))
			assert.Equal(t, "replay_checkpoint", checkpoint["type"])
			assert.Equal(t, "room", checkpoint["chat_id"])
			assert.Equal(t, true, checkpoint["refresh_required"])
			assert.NotContains(t, string(queued.Payload), "secret_content")
		})
	}
}

func TestChatAudienceMissingLiveCheckpointOmitsRefreshForEphemeralAndUnknownTypes(t *testing.T) {
	tests := []struct {
		name         string
		envelopeType string
		payloadType  string
	}{
		{name: "typing", envelopeType: "typing", payloadType: "typing"},
		{name: "unknown event", envelopeType: "future_event", payloadType: "future_event"},
		{name: "mismatched type", envelopeType: "new_message", payloadType: "typing"},
	}

	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			h := setupTestHub()
			messageData, err := json.Marshal(map[string]any{
				"type": test.envelopeType,
				"room": "room",
				"payload": map[string]any{
					"type":           test.payloadType,
					"chat_id":        "room",
					"secret_content": "must-not-reach-browser",
				},
			})
			require.NoError(t, err)
			message := &nats.Msg{Subject: "chat.room", Data: messageData}

			h.processChatDelivery(context.Background(), message, false)
			var queued *Message
			select {
			case queued = <-h.Broadcast:
			default:
				t.Fatal("missing-audience checkpoint was not queued")
			}
			var payload map[string]any
			require.NoError(t, json.Unmarshal(queued.Payload, &payload))
			assert.Equal(t, "replay_checkpoint", payload["type"])
			assert.NotContains(t, payload, "refresh_required")
			assert.NotContains(t, string(queued.Payload), "secret_content")
		})
	}
}

func TestChatAudienceDeliveryStillRechecksCurrentRoomMembership(t *testing.T) {
	h := setupTestHub()
	client := &Client{
		ID: "removed-after-snapshot", UserID: audienceFixtureID(8),
		Rooms: map[string]bool{"room": true}, Send: make(chan []byte, 1), Hub: h,
		ctx: context.Background(),
	}
	h.mu.Lock()
	h.Rooms["room"] = map[*Client]bool{client: true}
	h.mu.Unlock()
	message := &Message{
		Type: "new_message", Room: "room", Payload: json.RawMessage(`{"chat_id":"room"}`),
		audiencePresent: true, audienceUserIDs: map[string]struct{}{client.UserID: {}},
	}
	recipients := h.collectRecipients(message, nil)
	require.Len(t, recipients, 1)

	h.mu.Lock()
	delete(h.Rooms["room"], client)
	h.mu.Unlock()
	h.deliverBroadcastRecipient(context.Background(), message, []byte(`{"room":"room"}`), recipients[0])
	assert.Empty(t, client.Send, "membership lost after recipient collection must still block delivery")
}

func TestChatAudienceReplayFiltersExcludedRowsAndStripsAllowedAudience(t *testing.T) {
	const allowedID = "00000000-0000-4000-8000-000000000011"
	h := setupTestHub()
	enableSecureReplayForTest(h)
	oldAck := ackOfflineMessageFunc
	t.Cleanup(func() { ackOfflineMessageFunc = oldAck })
	ackCount := 0
	ackOfflineMessageFunc = func(*nats.Msg) error { ackCount++; return nil }

	excluded := &Client{UserID: "00000000-0000-4000-8000-000000000012", Hub: h, ctx: context.Background(), Send: make(chan []byte, 2)}
	excludedMessage := replayMessage(42)
	excludedMessage.Data = []byte(fmt.Sprintf(
		`{"type":"new_message","room":"room","payload":{"chat_id":"room","n":42},"audience":[%q]}`,
		allowedID,
	))
	foundLastMsgID := true
	maxSequence := uint64(41)
	require.True(t, excluded.deliverOfflineMessageBatch(context.Background(), "room", []*nats.Msg{excludedMessage}, "", &foundLastMsgID, &maxSequence))
	var checkpoint map[string]any
	require.NoError(t, json.Unmarshal(<-excluded.Send, &checkpoint))
	assert.Equal(t, "replay_checkpoint", checkpoint["type"])
	assert.Equal(t, float64(42), checkpoint["seq"])
	assert.NotContains(t, checkpoint, "audience")
	checkpointPayload, ok := checkpoint["payload"].(map[string]any)
	require.True(t, ok)
	assert.NotContains(t, checkpointPayload, "n", "excluded replay must not carry original event content")
	assert.NotContains(t, checkpointPayload, "refresh_required", "audience-excluded rows must not trigger REST refresh")
	assert.Equal(t, uint64(42), maxSequence)

	allowed := &Client{UserID: allowedID, Hub: h, ctx: context.Background(), Send: make(chan []byte, 2)}
	allowedMessage := replayMessage(43)
	allowedMessage.Data = []byte(fmt.Sprintf(
		`{"type":"new_message","room":"room","payload":{"chat_id":"room","n":43},"audience":[%q]}`,
		allowedID,
	))
	foundLastMsgID = true
	maxSequence = 42
	require.True(t, allowed.deliverOfflineMessageBatch(context.Background(), "room", []*nats.Msg{allowedMessage}, "", &foundLastMsgID, &maxSequence))
	var replayed map[string]any
	require.NoError(t, json.Unmarshal(<-allowed.Send, &replayed))
	assert.Equal(t, float64(43), replayed["seq"])
	assert.NotContains(t, replayed, "audience", "allowed replay must not expose the internal recipient list")
	assert.Equal(t, 2, ackCount)
}

func TestChatAudienceMissingReplayUsesCheckpointAndAcksWithoutContent(t *testing.T) {
	h := setupTestHub()
	enableSecureReplayForTest(h)
	client := &Client{UserID: audienceFixtureID(23), Hub: h, ctx: context.Background(), Send: make(chan []byte, 1)}
	message := replayMessage(44)
	message.Data = []byte(`{"type":"new_message","room":"room","payload":{"type":"new_message","chat_id":"room","secret_content":"must-not-reach-browser"}}`)
	oldAck, oldTerm := ackOfflineMessageFunc, termOfflineMessageFunc
	t.Cleanup(func() { ackOfflineMessageFunc, termOfflineMessageFunc = oldAck, oldTerm })
	ackCount, termCount := 0, 0
	ackOfflineMessageFunc = func(*nats.Msg) error { ackCount++; return nil }
	termOfflineMessageFunc = func(*nats.Msg) error { termCount++; return nil }
	foundLastMsgID := true
	maxSequence := uint64(43)
	require.True(t, client.deliverOfflineMessageBatch(context.Background(), "room", []*nats.Msg{message}, "", &foundLastMsgID, &maxSequence))
	var checkpoint map[string]any
	require.NoError(t, json.Unmarshal(<-client.Send, &checkpoint))
	assert.Equal(t, "replay_checkpoint", checkpoint["type"])
	assert.Equal(t, float64(44), checkpoint["seq"])
	assert.Equal(t, true, checkpoint["replayed"])
	assert.NotEmpty(t, checkpoint["resume_token"])
	encodedCheckpoint, marshalErr := json.Marshal(checkpoint)
	require.NoError(t, marshalErr)
	assert.NotContains(t, string(encodedCheckpoint), "secret_content")
	assert.NotContains(t, checkpoint, "audience")
	checkpointPayload, ok := checkpoint["payload"].(map[string]any)
	require.True(t, ok)
	assert.Equal(t, true, checkpointPayload["refresh_required"])
	assert.Equal(t, uint64(44), maxSequence)
	assert.Equal(t, 1, ackCount)
	assert.Zero(t, termCount, "a missing field is a checkpointed legacy row, not a poison row")
}

func TestChatAudienceMissingReplayCheckpointRefreshesPersistedTypes(t *testing.T) {
	for index, eventType := range []string{
		"new_message", "message_edited", "message_deleted", "reaction_changed", "read",
	} {
		t.Run(eventType, func(t *testing.T) {
			h := setupTestHub()
			enableSecureReplayForTest(h)
			sequence := uint64(60 + index)
			client := &Client{
				UserID: audienceFixtureID(40 + index), Hub: h,
				ctx: context.Background(), Send: make(chan []byte, 1),
			}
			message := replayMessage(sequence)
			message.Data = []byte(fmt.Sprintf(
				`{"type":%q,"room":"room","payload":{"type":%q,"chat_id":"room","secret_content":"must-not-reach-browser"}}`,
				eventType, eventType,
			))
			oldAck := ackOfflineMessageFunc
			t.Cleanup(func() { ackOfflineMessageFunc = oldAck })
			ackCount := 0
			ackOfflineMessageFunc = func(*nats.Msg) error { ackCount++; return nil }
			foundLastMsgID := true
			maxSequence := sequence - 1

			require.True(t, client.deliverOfflineMessageBatch(
				context.Background(), "room", []*nats.Msg{message}, "", &foundLastMsgID, &maxSequence,
			))
			var checkpoint map[string]any
			require.NoError(t, json.Unmarshal(<-client.Send, &checkpoint))
			assert.Equal(t, "replay_checkpoint", checkpoint["type"])
			assert.Equal(t, float64(sequence), checkpoint["seq"])
			payload, ok := checkpoint["payload"].(map[string]any)
			require.True(t, ok)
			assert.Equal(t, true, payload["refresh_required"])
			encoded, marshalErr := json.Marshal(checkpoint)
			require.NoError(t, marshalErr)
			assert.NotContains(t, string(encoded), "secret_content")
			assert.Equal(t, sequence, maxSequence)
			assert.Equal(t, 1, ackCount)
		})
	}
}

func TestChatAudienceMalformedReplayIsCheckpointedWithoutEventContent(t *testing.T) {
	h := setupTestHub()
	enableSecureReplayForTest(h)
	client := &Client{UserID: "replay-user", Hub: h, ctx: context.Background(), Send: make(chan []byte, 1)}
	message := replayMessage(45)
	message.Data = []byte(`{"type":"new_message","room":"room","payload":{"chat_id":"room","n":45},"audience":null}`)
	oldTerm := termOfflineMessageFunc
	t.Cleanup(func() { termOfflineMessageFunc = oldTerm })
	termCount := 0
	termOfflineMessageFunc = func(*nats.Msg) error { termCount++; return nil }
	foundLastMsgID := true
	maxSequence := uint64(44)

	require.True(t, client.deliverOfflineMessageBatch(context.Background(), "room", []*nats.Msg{message}, "", &foundLastMsgID, &maxSequence))
	require.Equal(t, 1, termCount)
	var checkpoint map[string]any
	require.NoError(t, json.Unmarshal(<-client.Send, &checkpoint))
	assert.Equal(t, "replay_checkpoint", checkpoint["type"])
	assert.NotContains(t, checkpoint, "audience")
	checkpointPayload, ok := checkpoint["payload"].(map[string]any)
	require.True(t, ok)
	assert.NotContains(t, checkpointPayload, "refresh_required", "poison rows must not trigger REST refresh")
	assert.Equal(t, uint64(45), maxSequence)
}

func TestChatAudienceMissingReplayCheckpointOmitsRefreshForEphemeralAndUnknownTypes(t *testing.T) {
	tests := []struct {
		name         string
		envelopeType string
		payloadType  string
	}{
		{name: "typing", envelopeType: "typing", payloadType: "typing"},
		{name: "unknown event", envelopeType: "future_event", payloadType: "future_event"},
		{name: "mismatched type", envelopeType: "new_message", payloadType: "typing"},
	}

	for index, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			h := setupTestHub()
			enableSecureReplayForTest(h)
			client := &Client{UserID: audienceFixtureID(30 + index), Hub: h, ctx: context.Background(), Send: make(chan []byte, 1)}
			message := replayMessage(uint64(50 + index))
			message.Data = []byte(fmt.Sprintf(
				`{"type":%q,"room":"room","payload":{"type":%q,"chat_id":"room","secret_content":"must-not-reach-browser"}}`,
				test.envelopeType, test.payloadType,
			))
			oldAck := ackOfflineMessageFunc
			t.Cleanup(func() { ackOfflineMessageFunc = oldAck })
			ackCount := 0
			ackOfflineMessageFunc = func(*nats.Msg) error { ackCount++; return nil }
			foundLastMsgID := true
			maxSequence := uint64(49 + index)

			require.True(t, client.deliverOfflineMessageBatch(context.Background(), "room", []*nats.Msg{message}, "", &foundLastMsgID, &maxSequence))
			var checkpoint map[string]any
			require.NoError(t, json.Unmarshal(<-client.Send, &checkpoint))
			payload, ok := checkpoint["payload"].(map[string]any)
			require.True(t, ok)
			assert.NotContains(t, payload, "refresh_required")
			encoded, marshalErr := json.Marshal(checkpoint)
			require.NoError(t, marshalErr)
			assert.NotContains(t, string(encoded), "secret_content")
			assert.Equal(t, uint64(50+index), maxSequence)
			assert.Equal(t, 1, ackCount)
		})
	}
}
