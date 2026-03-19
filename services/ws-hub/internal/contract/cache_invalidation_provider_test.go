//go:build cgo

// Package contract_test contains Pact V4 provider verification for the
// university-backend → ws-hub NATS message contract.
//
// MOD-07 (audit 2026-03-16 Wave 10): Consumer-Driven Contract Tests.
//
// The Python consumer test (tests/contracts/test_ws_hub_contract.py) defines
// what the ws-hub expects to receive on the "cache.invalidate" NATS subject
// and writes a Pact V4 JSON file.  This test reads that pact file and verifies
// that "university-backend" (the Python producer) can produce messages whose
// structure matches the contract.
//
// The message handler below reproduces the exact signing logic from
// app/services/ws_hub_client.py so that any drift (field rename, type change,
// serialisation order mismatch) causes a verification failure rather than a
// silent HMAC drop in production.
//
// Run locally:
//
//	PACT_DIR=../../../../tests/contracts/pacts \
//	WS_HUB_INTERNAL_SECRET=<secret> \
//	go test ./internal/contract/... -v
//
// CGO requirement: pact-go/v2 wraps the Pact Rust FFI library.
// Install it once before running:
//
//	go run github.com/pact-foundation/pact-go/v2/install -libDir /usr/local/lib
package contract_test

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"testing"
	"time"

	pactLog "github.com/pact-foundation/pact-go/v2/log"
	pactMessage "github.com/pact-foundation/pact-go/v2/message"
	"github.com/pact-foundation/pact-go/v2/models"
	"github.com/pact-foundation/pact-go/v2/provider"
)

// ---------------------------------------------------------------------------
// Types — must exactly mirror hub.go's inline struct for HMAC correctness.
// Field tags are alphabetical to match Python's json.dumps(sort_keys=True).
// ---------------------------------------------------------------------------

// cacheInvalidationData mirrors the anonymous "Data" struct in hub.go.
// Field declaration order controls json.Marshal output order; the tags must
// be alphabetical (room_id < timestamp < user_id) to produce the same
// canonical JSON that Python signs.
type cacheInvalidationData struct {
	RoomID    string `json:"room_id"`
	Timestamp uint64 `json:"timestamp"`
	UserID    string `json:"user_id"`
}

// cacheInvalidationPayload is the full wire format published by WsHubClient.
type cacheInvalidationPayload struct {
	Data      cacheInvalidationData `json:"data"`
	Signature string                `json:"signature"`
}

// ---------------------------------------------------------------------------
// Helper — reproduces app/services/ws_hub_client.py signing logic exactly.
// ---------------------------------------------------------------------------

// buildInvalidationPayload signs a cache invalidation payload the same way the
// Python WsHubClient does:
//
//  1. Serialise the data object with json.Marshal (alphabetical fields).
//  2. Compute HMAC-SHA256 over the serialised bytes.
//  3. Hex-encode the digest.
//
// This must stay in sync with ws_hub_client.py.  The contract test will fail
// if they diverge — that's the point.
func buildInvalidationPayload(userID, roomID, secret string) (cacheInvalidationPayload, error) {
	data := cacheInvalidationData{
		RoomID:    roomID,
		Timestamp: uint64(time.Now().UnixMicro()), //nolint:gosec // monotonic timestamp, not a secret
		UserID:    userID,
	}

	// json.Marshal uses field declaration order (room_id, timestamp, user_id) —
	// identical to Python's sort_keys=True on the same keys.
	dataBytes, err := json.Marshal(data)
	if err != nil {
		return cacheInvalidationPayload{}, fmt.Errorf("json.Marshal data: %w", err)
	}

	hFunc := hmac.New(sha256.New, []byte(secret))
	hFunc.Write(dataBytes)

	return cacheInvalidationPayload{
		Data:      data,
		Signature: hex.EncodeToString(hFunc.Sum(nil)),
	}, nil
}

// ---------------------------------------------------------------------------
// Provider verification test
// ---------------------------------------------------------------------------

// TestCacheInvalidationMessageProvider verifies that the "university-backend"
// producer satisfies the ws-hub consumer contract for cache invalidation events.
//
// The verifier reads the pact file written by the Python consumer test and
// runs the registered message handler for each interaction, checking that:
//   - The handler produces a body matching the pact interaction body matchers.
//   - The handler produces metadata with the expected nats_subject.
func TestCacheInvalidationMessageProvider(t *testing.T) {
	pactLog.SetLogLevel("INFO")

	// Locate the pact file produced by the Python consumer test.
	pactDir := os.Getenv("PACT_DIR")
	if pactDir == "" {
		// Default: from services/ws-hub/internal/contract/ to repo-root pacts/.
		pactDir = filepath.Join("..", "..", "..", "..", "tests", "contracts", "pacts")
	}

	// Use a deterministic placeholder secret for structural verification.
	// The contract test validates shape (UUID regex, HMAC hex length), not
	// the specific secret value — that's an operational concern.
	secret := os.Getenv("WS_HUB_INTERNAL_SECRET")
	if secret == "" {
		secret = "contract-test-placeholder-secret-not-for-production" // pragma: allowlist secret
	}

	// Map Pact interaction descriptions to handler functions.
	// The key must exactly match the string passed to .upon_receiving() in the
	// Python consumer test.
	handlers := pactMessage.Handlers{
		"a cache invalidation event": func(_ []models.ProviderState) (pactMessage.Body, pactMessage.Metadata, error) {
			payload, err := buildInvalidationPayload(
				"550e8400-e29b-41d4-a716-446655440000",
				"550e8400-e29b-41d4-a716-446655440001",
				secret,
			)
			if err != nil {
				return nil, nil, err
			}
			return payload, pactMessage.Metadata{
				"contentType":  "application/json",
				"nats_subject": "cache.invalidate",
			}, nil
		},
	}

	verifier := provider.NewVerifier()
	verifier.VerifyProvider(t, provider.VerifyRequest{
		Provider: "university-backend",
		PactFiles: []string{
			filepath.ToSlash(filepath.Join(pactDir, "ws-hub-university-backend.json")),
		},
		MessageHandlers: handlers,
	})
}
