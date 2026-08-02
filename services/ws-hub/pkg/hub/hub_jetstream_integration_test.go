//go:build integration

package hub

import (
	"context"
	"encoding/json"
	"log/slog"
	"os"
	"strconv"
	"testing"
	"time"

	"github.com/nats-io/nats.go"
	"github.com/stretchr/testify/require"
	"github.com/testcontainers/testcontainers-go"
	tclog "github.com/testcontainers/testcontainers-go/log"
	tcnats "github.com/testcontainers/testcontainers-go/modules/nats"
	"github.com/university-ecosystem/ws-hub/pkg/config"
)

func startJetStreamNATSContainer(t *testing.T) (*nats.Conn, nats.JetStreamContext, func()) {
	t.Helper()
	ctx := context.Background()

	container, err := tcnats.Run(
		ctx,
		"nats:2.12.6-alpine",
		tcnats.WithArgument("jetstream", ""),
		testcontainers.WithLogger(tclog.TestLogger(t)),
	)
	if err != nil {
		t.Fatalf("JetStream NATS container start: %v", err)
	}

	connectionString, err := container.ConnectionString(ctx)
	if err != nil {
		_ = container.Terminate(ctx)
		t.Fatalf("JetStream NATS connection string: %v", err)
	}

	nc, err := nats.Connect(connectionString)
	if err != nil {
		_ = container.Terminate(ctx)
		t.Fatalf("JetStream NATS connect: %v", err)
	}
	js, err := nc.JetStream()
	if err != nil {
		nc.Close()
		_ = container.Terminate(ctx)
		t.Fatalf("JetStream context: %v", err)
	}

	cleanup := func() {
		nc.Close()
		if err := container.Terminate(context.Background()); err != nil {
			t.Logf("JetStream NATS container cleanup: %v", err)
		}
	}
	return nc, js, cleanup
}

func TestIntegration_SubscribeToNATSJetStreamConsumers(t *testing.T) {
	nc, js, cleanup := startJetStreamNATSContainer(t)
	t.Cleanup(cleanup)

	for _, stream := range []nats.StreamConfig{
		{
			Name:      "CHAT_EVENTS",
			Subjects:  []string{"chat.>"},
			Storage:   nats.MemoryStorage,
			Retention: nats.LimitsPolicy,
		},
		{
			Name:      "NOTIFICATIONS_EVENTS",
			Subjects:  []string{"notifications.>"},
			Storage:   nats.MemoryStorage,
			Retention: nats.LimitsPolicy,
		},
	} {
		_, err := js.AddStream(&stream)
		require.NoError(t, err)
	}

	cfg := &config.Config{
		MaxClients:               10,
		BroadcastBufferSize:      10,
		BroadcastWorkers:         1,
		ClientMsgRateLimit:       10,
		ClientMsgRateBurst:       10,
		EnableJetStream:          true,
		NatsStreamChat:           "CHAT_EVENTS",
		NatsStreamNotifications:  "NOTIFICATIONS_EVENTS",
		NatsDurableChat:          "integration-chat",
		NatsDurableNotifications: "integration-notifications",
	}
	logger := slog.New(slog.NewTextHandler(os.Stderr, &slog.HandlerOptions{Level: slog.LevelWarn}))
	h := trackTestHub(NewHub(nc, logger, &mockAuthClient{allowed: true}, cfg, nil))
	t.Cleanup(h.Stop)

	ctx, cancel := context.WithCancel(context.Background())
	t.Cleanup(cancel)
	require.NoError(t, h.SubscribeToNATS(ctx))
	require.Len(t, h.subs, 5, "chat, notifications, cache, control, and JWKS subscriptions")

	chatConsumer, err := js.ConsumerInfo("CHAT_EVENTS", "integration-chat")
	require.NoError(t, err)
	require.Equal(t, "integration-chat", chatConsumer.Name)
	notificationConsumer, err := js.ConsumerInfo("NOTIFICATIONS_EVENTS", "integration-notifications")
	require.NoError(t, err)
	require.Equal(t, "integration-notifications", notificationConsumer.Name)
}

func TestIntegration_ClientReplayOfflineMessagesFromJetStream(t *testing.T) {
	nc, js, cleanup := startJetStreamNATSContainer(t)
	t.Cleanup(cleanup)

	_, err := js.AddStream(&nats.StreamConfig{
		Name:      "CHAT_EVENTS",
		Subjects:  []string{"chat.>"},
		Storage:   nats.MemoryStorage,
		Retention: nats.LimitsPolicy,
	})
	require.NoError(t, err)

	cfg := &config.Config{
		MaxClients:          10,
		BroadcastBufferSize: 10,
		BroadcastWorkers:    1,
		ClientMsgRateLimit:  10,
		ClientMsgRateBurst:  10,
		EnableJetStream:     true,
		NatsStreamChat:      "CHAT_EVENTS",
	}
	logger := slog.New(slog.NewTextHandler(os.Stderr, &slog.HandlerOptions{Level: slog.LevelWarn}))
	h := trackTestHub(NewHub(nc, logger, &mockAuthClient{allowed: true}, cfg, nil))
	t.Cleanup(h.Stop)

	for index, id := range []string{"msg-1", "msg-2", "msg-3"} {
		message := &nats.Msg{
			Subject: "chat.replay-room",
			Header:  nats.Header{},
			Data: []byte(`{"type":"new_message","room":"replay-room","payload":{"index":` +
				strconv.Itoa(index) + `}}`),
		}
		message.Header.Set("Nats-Msg-Id", id)
		_, err := js.PublishMsg(message)
		require.NoError(t, err)
	}

	client := &Client{
		ID:     "replay-client",
		UserID: "replay-user",
		Hub:    h,
		ctx:    context.Background(),
		Send:   make(chan []byte, 10),
	}
	client.replayOfflineMessages("replay-room", 0, "msg-1")

	for _, wantIndex := range []float64{1, 2} {
		select {
		case raw := <-client.Send:
			var replayed map[string]any
			require.NoError(t, json.Unmarshal(raw, &replayed))
			require.Equal(t, true, replayed["replayed"])
			require.Equal(t, wantIndex, replayed["payload"].(map[string]any)["index"])
			require.NotZero(t, replayed["seq"])
		case <-time.After(2 * time.Second):
			t.Fatalf("timed out waiting for replayed message %v", wantIndex)
		}
	}

	// A numeric stream sequence uses the other resume cursor and must replay
	// messages after the requested sequence without relying on message IDs.
	client.replayOfflineMessages("replay-room", 1, "")
	select {
	case raw := <-client.Send:
		var replayed map[string]any
		require.NoError(t, json.Unmarshal(raw, &replayed))
		require.Equal(t, float64(1), replayed["payload"].(map[string]any)["index"])
	case <-time.After(2 * time.Second):
		t.Fatal("timed out waiting for sequence-based replay")
	}
}
