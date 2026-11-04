//go:build contract

// Package contract_test contains Pact V4 schema checks for the remaining
// university-backend NATS message interactions.
//
// MOD-07 (audit 2026-03-16 Wave 10): Consumer-Driven Contract Tests.
//
// The cache-invalidation contract is tested separately against the production
// Python publisher and the real hub handler, using a generated wire artifact.
// The remaining Pact handlers below check only their declared message shapes.
//
// Requires pact-go/v2 and the Pact Rust FFI library.
package contract_test

import (
	"os"
	"path/filepath"
	"testing"

	pactLog "github.com/pact-foundation/pact-go/v2/log"
	pactMessage "github.com/pact-foundation/pact-go/v2/message"
	"github.com/pact-foundation/pact-go/v2/models"
	"github.com/pact-foundation/pact-go/v2/provider"
)

type directChatMessage struct {
	ChatID    string `json:"chat_id"`
	Content   string `json:"content"`
	MessageID string `json:"message_id"`
	SenderID  string `json:"sender_id"`
}

type chatMessageSent struct {
	ChatID         string `json:"chat_id"`
	ContentPreview string `json:"content_preview"`
	MessageID      string `json:"message_id"`
	SenderID       string `json:"sender_id"`
}

type chatDeleted struct {
	ChatID        string `json:"chat_id"`
	ParticipantID string `json:"participant_id"`
}

type userCreated struct {
	Email  string `json:"email"`
	UserID string `json:"user_id"`
}

type notificationSent struct {
	NotificationID   string `json:"notification_id"`
	NotificationType string `json:"notification_type"`
	UserID           string `json:"user_id"`
}

type taskEnvelope struct {
	Args         []string       `json:"args"`
	ID           string         `json:"id"`
	Kwargs       map[string]any `json:"kwargs"`
	Name         string         `json:"name"`
	TraceContext map[string]any `json:"trace_context"`
}

// ---------------------------------------------------------------------------
// Provider verification test
// ---------------------------------------------------------------------------

// TestRemainingNatsPactMessageShapes verifies the remaining Pact message shapes.
// It does not exercise a production publisher or the hub's cache handler.
//
// The verifier reads the pact file written by the Python consumer test and
// runs the registered message handler for each interaction, checking that:
//   - The handler produces a body matching the pact interaction body matchers.
//   - The handler produces metadata with the expected nats_subject.
func TestRemainingNatsPactMessageShapes(t *testing.T) {
	if err := pactLog.SetLogLevel("INFO"); err != nil {
		t.Logf("Failed to set pact log level: %v", err)
	}

	// Locate the pact file produced by the Python consumer test.
	pactDir := os.Getenv("PACT_DIR")
	if pactDir == "" {
		// Default: from services/ws-hub/internal/contract/ to repo-root pacts/.
		pactDir = filepath.Join("..", "..", "..", "..", "tests", "contracts", "pacts")
	}

	// Map Pact interaction descriptions to handler functions.
	// The key must exactly match the string passed to .upon_receiving() in the
	// Python consumer test.
	handlers := pactMessage.Handlers{
		"a direct chat message event": func(_ []models.ProviderState) (pactMessage.Body, pactMessage.Metadata, error) {
			return directChatMessage{
				ChatID:    "chat-uuid-123",
				MessageID: "msg-uuid-456",
				Content:   "Hello there!",
				SenderID:  "user-uuid-789",
			}, pactMessage.Metadata{
				"contentType":  "application/json",
				"nats_subject": "chat.direct",
			}, nil
		},
		"a chat message_sent domain event": func(_ []models.ProviderState) (pactMessage.Body, pactMessage.Metadata, error) {
			return chatMessageSent{
				ChatID:         "chat-uuid-001",
				MessageID:      "msg-uuid-001",
				SenderID:       "user-uuid-001",
				ContentPreview: "Hello world",
			}, pactMessage.Metadata{
				"contentType":  "application/json",
				"nats_subject": "chat.message_sent",
			}, nil
		},
		"a chat deleted event": func(_ []models.ProviderState) (pactMessage.Body, pactMessage.Metadata, error) {
			return chatDeleted{
				ChatID:        "chat-uuid-del",
				ParticipantID: "user-uuid-del",
			}, pactMessage.Metadata{
				"contentType":  "application/json",
				"nats_subject": "chat.deleted",
			}, nil
		},
		"a user.created domain event": func(_ []models.ProviderState) (pactMessage.Body, pactMessage.Metadata, error) {
			return userCreated{
				UserID: "user-uuid-new",
				Email:  "newuser@university.test",
			}, pactMessage.Metadata{
				"contentType":  "application/json",
				"nats_subject": "user.created",
			}, nil
		},
		"a notification.sent event": func(_ []models.ProviderState) (pactMessage.Body, pactMessage.Metadata, error) {
			return notificationSent{
				NotificationID:   "notif-uuid-001",
				UserID:           "user-uuid-001",
				NotificationType: "push",
			}, pactMessage.Metadata{
				"contentType":  "application/json",
				"nats_subject": "notification.sent",
			}, nil
		},
		"a generic NATS task envelope": func(_ []models.ProviderState) (pactMessage.Body, pactMessage.Metadata, error) {
			return taskEnvelope{
				ID:           "task-uuid-999",
				Name:         "email.send_welcome",
				Args:         []string{"user@university.test"},
				Kwargs:       map[string]any{},
				TraceContext: map[string]any{},
			}, pactMessage.Metadata{
				"contentType":  "application/json",
				"nats_subject": "tasks.email.send_welcome",
			}, nil
		},
	}

	verifier := provider.NewVerifier()
	if err := verifier.VerifyProvider(t, provider.VerifyRequest{
		Provider: "university-backend",
		PactFiles: []string{
			filepath.ToSlash(filepath.Join(pactDir, "ws-hub-university-backend.json")),
		},
		MessageHandlers: handlers,
	}); err != nil {
		t.Errorf("Pact verification failed: %v", err)
	}
}
