//go:build integration

package hub

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"net"
	"net/url"
	"os"
	"strconv"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	"github.com/nats-io/nats.go"
	"github.com/stretchr/testify/require"
	"github.com/testcontainers/testcontainers-go"
	tclog "github.com/testcontainers/testcontainers-go/log"
	tcnats "github.com/testcontainers/testcontainers-go/modules/nats"
	"github.com/university-ecosystem/ws-hub/pkg/config"
)

var integrationNamespaceCounter atomic.Uint64

func validateExternalNATSTestURL(rawURL string) error {
	parsed, err := url.Parse(rawURL)
	if err != nil || (parsed.Scheme != "nats" && parsed.Scheme != "tls") {
		return fmt.Errorf("NATS_TEST_URL must be a valid nats:// or tls:// URL")
	}
	host := parsed.Hostname()
	if host == "localhost" {
		return nil
	}
	ip := net.ParseIP(host)
	if ip == nil || !ip.IsLoopback() {
		return fmt.Errorf("NATS_TEST_URL must target a loopback address")
	}
	return nil
}

func integrationNamespace(t *testing.T) string {
	t.Helper()
	name := strings.Map(func(r rune) rune {
		if r >= 'a' && r <= 'z' || r >= 'A' && r <= 'Z' || r >= '0' && r <= '9' {
			return r
		}
		return '_'
	}, t.Name())
	return fmt.Sprintf("%s_%d_%d", name, os.Getpid(), integrationNamespaceCounter.Add(1))
}

func addOwnedMemoryStream(t *testing.T, js nats.JetStreamContext, name string, subjects ...string) {
	t.Helper()
	_, err := js.AddStream(&nats.StreamConfig{
		Name:      name,
		Subjects:  subjects,
		Storage:   nats.MemoryStorage,
		Retention: nats.LimitsPolicy,
	})
	require.NoError(t, err)
	t.Cleanup(func() {
		require.NoError(t, js.DeleteStream(name), "delete test-owned stream %s", name)
	})
}

func TestExternalNATSTestURLRequiresLoopback(t *testing.T) {
	for _, rawURL := range []string{
		"nats://127.0.0.1:4222",
		"nats://[::1]:4222",
		"nats://localhost:4222",
	} {
		require.NoError(t, validateExternalNATSTestURL(rawURL), rawURL)
	}
	for _, rawURL := range []string{
		"nats://10.0.0.5:4222",
		"nats://example.com:4222",
		"nats://:4222",
		"not-a-url",
	} {
		require.Error(t, validateExternalNATSTestURL(rawURL), rawURL)
	}
}

func startJetStreamNATSContainer(t *testing.T) (*nats.Conn, nats.JetStreamContext, func()) {
	t.Helper()
	ctx := context.Background()
	if connectionString := os.Getenv("NATS_TEST_URL"); connectionString != "" {
		require.NoError(t, validateExternalNATSTestURL(connectionString))
		nc, err := nats.Connect(connectionString)
		require.NoError(t, err)
		js, err := nc.JetStream()
		require.NoError(t, err)
		return nc, js, nc.Close
	}

	container, err := tcnats.Run(
		ctx,
		"nats:2.12.6-alpine@sha256:1cfc36e2e5e638243d8c722f72c954cd0ec4b15ee82fadbc718ce12e2b3c1652",
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
	namespace := integrationNamespace(t)
	chatStream := "CHAT_" + strings.ToUpper(namespace)
	notificationStream := "NOTIFICATIONS_" + strings.ToUpper(namespace)
	room := "multi-replica-" + strings.ToLower(namespace)
	addOwnedMemoryStream(t, js, chatStream, "chat."+room)
	addOwnedMemoryStream(t, js, notificationStream, "notifications."+strings.ToLower(namespace))

	cfg := &config.Config{
		MaxClients:               10,
		BroadcastBufferSize:      10,
		BroadcastWorkers:         1,
		ClientMsgRateLimit:       10,
		ClientMsgRateBurst:       10,
		EnableJetStream:          true,
		NatsStreamChat:           chatStream,
		NatsStreamNotifications:  notificationStream,
		NatsDurableChat:          "integration-chat-" + namespace,
		NatsDurableNotifications: "integration-notifications-" + namespace,
		InternalSecret:           "integration-replay-signing-secret",
	}
	logger := slog.New(slog.NewTextHandler(os.Stderr, &slog.HandlerOptions{Level: slog.LevelWarn}))
	ctx, cancel := context.WithCancel(context.Background())
	t.Cleanup(cancel)
	hubs := []*Hub{
		trackTestHub(NewHub(nc, logger, &mockAuthClient{allowed: true}, cfg, nil)),
		trackTestHub(NewHub(nc, logger, &mockAuthClient{allowed: true}, cfg, nil)),
	}
	for _, h := range hubs {
		t.Cleanup(h.Stop)
		require.NoError(t, h.SubscribeToNATS(ctx))
		require.Len(t, h.subs, 5, "chat, notifications, cache, control, and JWKS subscriptions")
		require.True(t, h.chatReplayAvailable.Load())
	}

	payload := []byte(fmt.Sprintf(
		`{"type":"new_message","room":%q,"payload":{"chat_id":%q}}`, room, room,
	))
	_, err := js.Publish("chat."+room, payload)
	require.NoError(t, err)
	for _, h := range hubs {
		delivered := recvBroadcast(t, h)
		require.Equal(t, room, delivered.Room,
			"each replica must own an independent live consumer")
	}
}

func TestIntegration_OwnedStreamCleanupPreservesForeignStreams(t *testing.T) {
	nc, js, cleanup := startJetStreamNATSContainer(t)
	t.Cleanup(cleanup)
	require.True(t, nc.IsConnected())
	namespace := integrationNamespace(t)
	foreignStream := "FOREIGN_" + strings.ToUpper(namespace)
	ownedStream := "OWNED_" + strings.ToUpper(namespace)
	_, err := js.AddStream(&nats.StreamConfig{
		Name: foreignStream, Subjects: []string{"foreign." + strings.ToLower(namespace)}, Storage: nats.MemoryStorage,
	})
	require.NoError(t, err)
	t.Cleanup(func() { require.NoError(t, js.DeleteStream(foreignStream)) })

	t.Run("owned stream lifecycle", func(t *testing.T) {
		addOwnedMemoryStream(t, js, ownedStream, "owned."+strings.ToLower(namespace))
		_, err := js.StreamInfo(ownedStream)
		require.NoError(t, err)
	})

	_, err = js.StreamInfo(ownedStream)
	require.ErrorIs(t, err, nats.ErrStreamNotFound)
	_, err = js.StreamInfo(foreignStream)
	require.NoError(t, err, "cleanup must not delete streams it did not register")
}

func TestIntegration_ClientReplayOfflineMessagesFromJetStream(t *testing.T) {
	nc, js, cleanup := startJetStreamNATSContainer(t)
	t.Cleanup(cleanup)
	namespace := integrationNamespace(t)
	chatStream := "CHAT_" + strings.ToUpper(namespace)
	room := "replay-" + strings.ToLower(namespace)
	addOwnedMemoryStream(t, js, chatStream, "chat."+room)

	cfg := &config.Config{
		MaxClients:          10,
		BroadcastBufferSize: 10,
		BroadcastWorkers:    1,
		ClientMsgRateLimit:  10,
		ClientMsgRateBurst:  10,
		EnableJetStream:     true,
		NatsStreamChat:      chatStream,
		InternalSecret:      "integration-replay-signing-secret",
	}
	logger := slog.New(slog.NewTextHandler(os.Stderr, &slog.HandlerOptions{Level: slog.LevelWarn}))
	h := trackTestHub(NewHub(nc, logger, &mockAuthClient{allowed: true}, cfg, nil))
	t.Cleanup(h.Stop)
	streamInfo, err := js.StreamInfo(chatStream)
	require.NoError(t, err)
	h.chatStreamIncarnation = streamInfo.Created.UTC().Format(time.RFC3339Nano)

	for index, id := range []string{"msg-1", "msg-2", "msg-3"} {
		message := &nats.Msg{
			Subject: "chat." + room,
			Header:  nats.Header{},
			Data: []byte(fmt.Sprintf(
				`{"type":"new_message","room":%q,"payload":{"index":%s}}`, room, strconv.Itoa(index),
			)),
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
	client.replayOfflineMessages(room, 0, "msg-1")

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
	client.replayOfflineMessages(room, 1, "")
	select {
	case raw := <-client.Send:
		var replayed map[string]any
		require.NoError(t, json.Unmarshal(raw, &replayed))
		require.Equal(t, float64(1), replayed["payload"].(map[string]any)["index"])
	case <-time.After(2 * time.Second):
		t.Fatal("timed out waiting for sequence-based replay")
	}
}
