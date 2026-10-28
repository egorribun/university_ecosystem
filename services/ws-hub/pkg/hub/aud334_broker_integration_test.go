//go:build integration

package hub

import (
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"net"
	"strings"
	"testing"
	"time"

	"github.com/gorilla/websocket"
	"github.com/nats-io/nats.go"
	"github.com/stretchr/testify/require"
	"golang.org/x/time/rate"
)

func aud334OwnedStream(t *testing.T, js nats.JetStreamContext) (string, string, time.Time) {
	t.Helper()
	var ownerBytes [16]byte
	_, err := rand.Read(ownerBytes[:])
	require.NoError(t, err)
	owner := hex.EncodeToString(ownerBytes[:])
	name := "AUD_" + strings.ToUpper(owner)
	room := "aud" + owner
	subject := "chat." + room
	_, err = js.StreamInfo(name)
	require.True(t, errors.Is(err, nats.ErrStreamNotFound), "test stream must not exist before creation")
	info, err := js.AddStream(&nats.StreamConfig{
		Name: name, Subjects: []string{subject}, Storage: nats.MemoryStorage,
		Retention: nats.LimitsPolicy, Metadata: map[string]string{"audit-test-owner": owner},
	})
	require.NoError(t, err)
	created := info.Created
	t.Cleanup(func() {
		current, lookupErr := js.StreamInfo(name)
		if lookupErr != nil {
			t.Errorf("verify test-owned stream before cleanup: %v", lookupErr)
			return
		}
		if !current.Created.Equal(created) || current.Config.Metadata["audit-test-owner"] != owner ||
			len(current.Config.Subjects) != 1 || current.Config.Subjects[0] != subject {
			t.Error("test stream identity changed; refusing cleanup")
			return
		}
		if deleteErr := js.DeleteStream(name); deleteErr != nil {
			t.Errorf("delete test-owned stream: %v", deleteErr)
		}
	})
	return name, room, created
}

func aud334AwaitPump(t *testing.T, done <-chan struct{}) {
	t.Helper()
	select {
	case <-done:
	case <-time.After(3 * time.Second):
		t.Error("test client pump did not stop during cleanup")
	}
}

func TestIntegrationAUD334RejectedResumeReconnectsAndReplaysFromJetStream(t *testing.T) {
	nc, js := startJetStreamNATSContainer(t)
	stream, room, created := aud334OwnedStream(t, js)
	subject := "chat." + room
	h := setupTestHub()
	h.Nats = nc
	h.js = js
	h.streamChat = stream
	h.internalSecret = stream + room
	h.chatStreamIncarnation = created.UTC().Format(time.RFC3339Nano)
	h.chatReplayAvailable.Store(true)
	t.Cleanup(h.Stop)

	baseline, err := js.Publish(subject, []byte(fmt.Sprintf(
		`{"type":"new_message","room":%q,"payload":{"chat_id":%q,"text":"baseline"}}`, room, room)))
	require.NoError(t, err)
	missed, err := js.Publish(subject, []byte(fmt.Sprintf(
		`{"type":"new_message","room":%q,"payload":{"chat_id":%q,"text":"missed"}}`, room, room)))
	require.NoError(t, err)
	require.Equal(t, baseline.Sequence+1, missed.Sequence)
	token, err := h.issueResumeToken("replay-user", room, stream, baseline.Sequence)
	require.NoError(t, err)
	payload, err := json.Marshal(joinPayload{ResumeToken: token})
	require.NoError(t, err)
	join, err := json.Marshal(Message{Type: "join", Room: room, Payload: payload})
	require.NoError(t, err)

	firstServer, firstBrowser := newConnPair(t)
	rejected := newClientOn(h, firstServer, "rejected", "replay-user")
	rejected.Send = make(chan []byte, 1)
	rejected.Send <- []byte("pending")
	rejected.replayJoinLimiter = rate.NewLimiter(0, 0)
	h.handleRegister(rejected.ctx, rejected)
	readDone := make(chan struct{})
	go func() { rejected.ReadPump(rejected.ctx); close(readDone) }()
	t.Cleanup(func() {
		rejected.cancelConnection()
		_ = firstBrowser.Close()
		_ = firstServer.Close()
		aud334AwaitPump(t, readDone)
	})
	require.NoError(t, firstBrowser.WriteMessage(websocket.TextMessage, join))
	require.NoError(t, firstBrowser.SetReadDeadline(time.Now().Add(3*time.Second)))
	_, _, err = firstBrowser.ReadMessage()
	require.Error(t, err)
	var netErr net.Error
	if errors.As(err, &netErr) {
		require.False(t, netErr.Timeout(), "a timeout is not a closed transport")
	}
	select {
	case <-readDone:
	case <-time.After(3 * time.Second):
		t.Fatal("the rejected connection's read pump did not stop")
	}
	h.mu.RLock()
	_, stillRegistered := h.Clients[rejected.ID]
	h.mu.RUnlock()
	require.False(t, stillRegistered)

	nextServer, nextBrowser := newConnPair(t)
	reconnected := newClientOn(h, nextServer, "reconnected", rejected.UserID)
	reconnected.replayJoinLimiter = rate.NewLimiter(rate.Inf, 1)
	h.handleRegister(reconnected.ctx, reconnected)
	reconnectedReadDone, reconnectedWriteDone := make(chan struct{}), make(chan struct{})
	go func() { reconnected.ReadPump(reconnected.ctx); close(reconnectedReadDone) }()
	go func() { reconnected.WritePump(); close(reconnectedWriteDone) }()
	t.Cleanup(func() {
		reconnected.cancelConnection()
		_ = nextBrowser.Close()
		_ = nextServer.Close()
		aud334AwaitPump(t, reconnectedReadDone)
		aud334AwaitPump(t, reconnectedWriteDone)
	})
	require.NoError(t, nextBrowser.WriteMessage(websocket.TextMessage, join))
	require.NoError(t, nextBrowser.SetReadDeadline(time.Now().Add(3*time.Second)))
	_, data, err := nextBrowser.ReadMessage()
	require.NoError(t, err)
	var frame map[string]any
	require.NoError(t, json.Unmarshal(data, &frame))
	require.Equal(t, float64(missed.Sequence), frame["seq"])
	require.Equal(t, true, frame["replayed"])
	messagePayload, ok := frame["payload"].(map[string]any)
	require.True(t, ok)
	require.Equal(t, "missed", messagePayload["text"])
	cursor, ok := frame["resume_token"].(string)
	require.True(t, ok)
	sequence, err := h.verifyResumeToken(cursor, rejected.UserID, room)
	require.NoError(t, err)
	require.Equal(t, missed.Sequence, sequence)
}
