package hub

import (
	"context"
	"encoding/json"
	"errors"
	"strings"
	"testing"
	"time"

	"github.com/nats-io/nats.go"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestDecodeChatAudienceRejectsMalformedJSONBoundaries(t *testing.T) {
	for name, input := range map[string]string{
		"empty input":            "",
		"non-object root":        `[]`,
		"malformed object key":   `{"`,
		"malformed object value": `{"room":}`,
		"incomplete object":      `{"room":1`,
		"trailing JSON value":    `{} {}`,
		"trailing invalid bytes": `{}x`,
	} {
		t.Run(name, func(t *testing.T) {
			_, _, err := decodeChatAudience([]byte(input))
			require.Error(t, err)
		})
	}

	for name, input := range map[string]string{
		"empty raw audience":              "",
		"non-array raw audience":          `null`,
		"non-string audience member":      `[1]`,
		"incomplete audience array":       `[` + `"` + audienceFixtureID(3) + `"`,
		"trailing JSON after audience":    `[] []`,
		"trailing invalid audience bytes": `[]x`,
		"short identity":                  `[` + `"short"` + `]`,
		"wrong UUID separator":            `[` + `"00000000x0000-4000-8000-000000000001"` + `]`,
	} {
		t.Run(name, func(t *testing.T) {
			_, _, err := decodeChatAudienceMembers(json.RawMessage(input))
			require.Error(t, err)
		})
	}

	assert.True(t, isCanonicalAudienceUUID(audienceFixtureID(4)))
	assert.False(t, isCanonicalAudienceUUID("short"))
	assert.False(t, isLowerHexASCII('A'))
}

func TestDeliverValidOfflineMessageRejectsTokenAndBackpressureThenAckFailure(t *testing.T) {
	oldAck := ackOfflineMessageFunc
	oldNak := nakOfflineMessageFunc
	t.Cleanup(func() {
		ackOfflineMessageFunc = oldAck
		nakOfflineMessageFunc = oldNak
	})

	t.Run("resume token prerequisites fail", func(t *testing.T) {
		h := setupTestHub()
		client := &Client{UserID: audienceFixtureID(5), Hub: h}
		assert.False(t, client.deliverValidOfflineMessage(
			context.Background(), "room", &nats.Msg{}, map[string]any{}, "CHAT_EVENTS", 1, new(uint64)))
	})

	t.Run("cancelled delivery is NAKed", func(t *testing.T) {
		h := setupTestHub()
		enableSecureReplayForTest(h)
		client := &Client{UserID: audienceFixtureID(5), Hub: h, Send: make(chan []byte, 1)}
		ctx, cancel := context.WithCancel(context.Background())
		cancel()
		nakCount := 0
		nakOfflineMessageFunc = func(*nats.Msg, time.Duration) error { nakCount++; return nil }
		assert.False(t, client.deliverValidOfflineMessage(
			ctx, "room", &nats.Msg{}, map[string]any{"payload": "event"}, h.streamChat, 1, new(uint64)))
		assert.Equal(t, 1, nakCount)
	})

	t.Run("successful queue logs ack failure", func(t *testing.T) {
		h := setupTestHub()
		enableSecureReplayForTest(h)
		client := &Client{UserID: audienceFixtureID(5), Hub: h, Send: make(chan []byte, 1)}
		ackOfflineMessageFunc = func(*nats.Msg) error { return errors.New("synthetic ack failure") }
		maxSequence := uint64(0)
		assert.True(t, client.deliverValidOfflineMessage(
			context.Background(), "room", &nats.Msg{}, map[string]any{"payload": "event"}, h.streamChat, 17, &maxSequence))
		assert.Equal(t, uint64(17), maxSequence)
		select {
		case raw := <-client.Send:
			var frame map[string]any
			require.NoError(t, json.Unmarshal(raw, &frame))
			assert.Equal(t, float64(17), frame["seq"])
			assert.Equal(t, true, frame["replayed"])
		default:
			t.Fatal("valid replay was not queued")
		}
	})
}

func TestProcessChatDeliveryRejectsSequencedAudienceAndCheckpointFailures(t *testing.T) {
	oldMarshal := hubJSONMarshalFunc
	oldAck := jetStreamAckFunc
	oldTerm := jetStreamTermFunc
	t.Cleanup(func() {
		hubJSONMarshalFunc = oldMarshal
		jetStreamAckFunc = oldAck
		jetStreamTermFunc = oldTerm
	})

	for _, test := range []struct {
		name            string
		data            string
		failMarshal     bool
		requireSequence bool
	}{
		{name: "invalid audience is terminated", data: `{"type":"new_message","room":"room","payload":{"chat_id":"room"},"audience":null}`, requireSequence: true},
		{name: "checkpoint marshal failure is terminated", data: `{"type":"new_message","room":"room","payload":{"type":"new_message","chat_id":"room"}}`, failMarshal: true, requireSequence: true},
		{name: "unsequenced checkpoint marshal failure is acknowledged", data: `{"type":"new_message","room":"room","payload":{"type":"new_message","chat_id":"room"}}`, failMarshal: true},
	} {
		t.Run(test.name, func(t *testing.T) {
			h := setupTestHub()
			enableSecureReplayForTest(h)
			ackCount, termCount := 0, 0
			jetStreamAckFunc = func(*nats.Msg) error { ackCount++; return nil }
			jetStreamTermFunc = func(*nats.Msg) error { termCount++; return nil }
			if test.failMarshal {
				hubJSONMarshalFunc = func(any) ([]byte, error) { return nil, errors.New("synthetic checkpoint marshal failure") }
			} else {
				hubJSONMarshalFunc = json.Marshal
			}

			h.processChatDelivery(context.Background(), &nats.Msg{
				Subject: "chat.room",
				Reply:   "$JS.ACK.CHAT_EVENTS.offline-replay.1.17.17.1690000000000000000.0",
				Sub:     &nats.Subscription{},
				Data:    []byte(test.data),
			}, test.requireSequence)
			if test.requireSequence {
				assert.Zero(t, ackCount)
				assert.Equal(t, 1, termCount)
			} else {
				assert.Equal(t, 1, ackCount)
				assert.Zero(t, termCount)
			}
			assert.Empty(t, h.Broadcast)
		})
	}
}

func TestReadChatAudienceFieldRejectsMalformedKeyToken(t *testing.T) {
	decoder := json.NewDecoder(strings.NewReader(`{"`))
	_, err := decoder.Token()
	require.NoError(t, err)
	_, _, err = readChatAudienceField(decoder)
	require.Error(t, err)
}

func TestDecodeChatAudienceArrayRejectsInvalidOpeningToken(t *testing.T) {
	for name, input := range map[string]string{
		"empty decoder": "",
		"object token":  `{}`,
	} {
		t.Run(name, func(t *testing.T) {
			_, err := decodeChatAudienceArray(json.NewDecoder(strings.NewReader(input)))
			require.Error(t, err)
		})
	}
}
