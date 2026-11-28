package hub

import (
	"context"
	"strings"
	"testing"

	"github.com/nats-io/nats.go"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"github.com/university-ecosystem/services/pkg/logging"
)

func registerNotificationRoutingClient(t *testing.T, h *Hub, connectionID, userID string) *Client {
	t.Helper()
	client := &Client{
		ID:     connectionID,
		UserID: userID,
		Rooms:  make(map[string]bool),
		Send:   make(chan []byte, 1),
		Hub:    h,
		ctx:    context.Background(),
	}
	h.handleRegister(context.Background(), client)
	t.Cleanup(func() {
		h.handleUnregister(context.Background(), client)
	})
	return client
}

func TestHandleNotificationsRoutesToEverySessionForSubjectUser(t *testing.T) {
	h := newNatsTestHub(&mockAuthClient{allowed: true}, "", 10)
	first := registerNotificationRoutingClient(t, h, "connection-a", "user-77")
	second := registerNotificationRoutingClient(t, h, "connection-b", "user-77")
	other := registerNotificationRoutingClient(t, h, "connection-c", "user-88")

	h.handleNotifications(context.Background())(&nats.Msg{
		Subject: "notifications.user-77",
		Data:    []byte(`{"to":"user-77","payload":{"title":"alert"}}`),
	})

	message := recvBroadcast(t, h)
	require.Equal(t, "notification", message.Type)
	require.Equal(t, "user-77", message.To)
	h.broadcastMessage(context.Background(), message)

	assert.Equal(t, "notification", recvSend(t, first).Type)
	assert.Equal(t, "notification", recvSend(t, second).Type)
	select {
	case data := <-other.Send:
		t.Fatalf("notification for user-77 reached user-88: %s", data)
	default:
	}
}

func TestHandleNotificationsRejectsMissingInvalidOrMismatchedDestination(t *testing.T) {
	h := newNatsTestHub(&mockAuthClient{allowed: true}, "", 10)
	handler := h.handleNotifications(context.Background())
	cases := []struct {
		name    string
		subject string
		data    string
	}{
		{
			name:    "missing subject user",
			subject: "notifications.",
			data:    `{"to":"user-77"}`,
		},
		{
			name:    "extra subject token",
			subject: "notifications.user-77.extra",
			data:    `{"to":"user-77"}`,
		},
		{
			name:    "invalid subject token",
			subject: "notifications.user 77",
			data:    `{"to":"user 77"}`,
		},
		{
			name:    "missing payload recipient",
			subject: "notifications.user-77",
			data:    `{"payload":{"title":"alert"}}`,
		},
		{
			name:    "recipient differs from subject user",
			subject: "notifications.user-77",
			data:    `{"to":"user-88"}`,
		},
		{
			name:    "room conflicts with personal route",
			subject: "notifications.user-77",
			data:    `{"to":"user-77","room":"room-1"}`,
		},
	}

	for _, testCase := range cases {
		t.Run(testCase.name, func(t *testing.T) {
			handler(&nats.Msg{Subject: testCase.subject, Data: []byte(testCase.data)})
			select {
			case message := <-h.Broadcast:
				t.Fatalf("invalid notification was queued: %+v", message)
			default:
			}
		})
	}
}

func TestNotificationRoutingDoesNotFallBackWhenUserHasNoSession(t *testing.T) {
	h := newNatsTestHub(&mockAuthClient{allowed: true}, "", 10)
	other := registerNotificationRoutingClient(t, h, "connection-c", "user-88")

	h.handleNotifications(context.Background())(&nats.Msg{
		Subject: "notifications.user-77",
		Data:    []byte(`{"to":"user-77","payload":{"title":"alert"}}`),
	})
	h.broadcastMessage(context.Background(), recvBroadcast(t, h))

	select {
	case data := <-other.Send:
		t.Fatalf("notification without a matching user session was broadcast: %s", data)
	default:
	}
	assert.Empty(t, h.collectRecipients(&Message{Type: "notification"}, nil),
		"a notification without a destination must never collect all clients")
}

func TestHandleNotifications_DiagnosticsOmitSubjectRecipient(t *testing.T) {
	const recipient = "sample-recipient-identifier"
	for _, tc := range []struct {
		name, data, warning string
		fill                bool
	}{
		{"malformed", "not json", "malformed NATS notification dropped", false},
		{"destination mismatch", `{"to":"another-recipient"}`, "NATS notification destination rejected", false},
		{"full queue", `{"to":"sample-recipient-identifier"}`, "Broadcast channel full, dropping NATS notification", true},
	} {
		t.Run(tc.name, func(t *testing.T) {
			var logs strings.Builder
			h := newNatsTestHub(&mockAuthClient{allowed: true}, "", 1)
			h.Logger = logging.NewJSONLogger(&logs, nil)
			if tc.fill {
				h.Broadcast <- &Message{Type: "existing"}
			}

			h.handleNotifications(t.Context())(&nats.Msg{
				Subject: "notifications." + recipient,
				Data:    []byte(tc.data),
			})

			assert.Contains(t, logs.String(), tc.warning)
			assert.NotContains(t, logs.String(), recipient)
			if tc.fill {
				assert.Equal(t, "existing", recvBroadcast(t, h).Type)
			}
			assert.Empty(t, h.Broadcast)
		})
	}
}
