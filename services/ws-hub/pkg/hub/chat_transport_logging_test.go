package hub

import (
	"bytes"
	"errors"
	"log/slog"
	"testing"
	"time"

	"github.com/nats-io/nats.go"
	"github.com/stretchr/testify/assert"
)

func TestChatTransportWarningsOmitRoomIdentifiers(t *testing.T) {
	const room = "synthetic-private-conversation"
	const subject = "chat.synthetic-subject-conversation"
	const errorDetail = "synthetic transport error detail"
	msg := &nats.Msg{Subject: subject}
	wsMsg := &Message{Room: room, MessageReplayMetadata: &MessageReplayMetadata{Seq: 42}}
	oldTerm, oldNak := jetStreamTermFunc, jetStreamNakFunc
	t.Cleanup(func() { jetStreamTermFunc, jetStreamNakFunc = oldTerm, oldNak })
	jetStreamTermFunc = func(*nats.Msg) error { return nil }
	jetStreamNakFunc = func(*nats.Msg, time.Duration) error { return nil }

	var logs bytes.Buffer
	h := &Hub{
		Logger:    slog.New(slog.NewJSONHandler(&logs, nil)),
		Broadcast: make(chan *Message, 1),
	}
	assertWarning := func(t *testing.T, warning string) string {
		t.Helper()
		output := logs.String()
		assert.Contains(t, output, warning)
		assert.NotContains(t, output, room)
		assert.NotContains(t, output, subject)
		return output
	}

	t.Run("missing JetStream metadata", func(t *testing.T) {
		logs.Reset()
		assert.False(t, h.applyChatSequence(t.Context(), msg, &Message{}, true))
		assertWarning(t, "unsequenced JetStream chat message rejected")
	})

	t.Run("termination failure", func(t *testing.T) {
		logs.Reset()
		previous := jetStreamTermFunc
		t.Cleanup(func() { jetStreamTermFunc = previous })
		jetStreamTermFunc = func(*nats.Msg) error { return errors.New(errorDetail) }
		h.terminateChatMessage(t.Context(), msg, "room binding mismatch")
		output := assertWarning(t, "Failed to terminate rejected NATS chat message")
		assert.Contains(t, output, `"reason":"room binding mismatch"`)
		assert.NotContains(t, output, errorDetail)
	})

	t.Run("sequenced message cannot be broadcast", func(t *testing.T) {
		logs.Reset()
		h.rejectUndeliverableSequencedChat(t.Context(), msg, wsMsg, "oversized")
		output := assertWarning(t, "sequenced chat message cannot be broadcast")
		assert.Contains(t, output, `"sequence":42`)
		assert.Contains(t, output, `"reason":"oversized"`)
	})

	t.Run("broadcast queue full", func(t *testing.T) {
		logs.Reset()
		h.Broadcast <- &Message{}
		h.enqueueChatDelivery(t.Context(), msg, wsMsg, "", false)
		assertWarning(t, "Broadcast channel full, dropping NATS chat message")
		assert.Len(t, h.Broadcast, 1)
	})
}
