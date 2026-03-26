//go:build go1.18

// MOD-W15-06 (audit 2026-03-23 Wave 15): Fuzz testing for ws-hub message parsing.
//
// Fuzz testing feeds random byte sequences into the message parsing path to find
// panics, OOM, and unexpected error states without explicit test case enumeration.
//
// Run locally (30s budget):
//
//	go test ./pkg/hub/ -fuzz=FuzzParseMessage -fuzztime=30s
//
// CI budget (30s, see .github/workflows/ci.yml go-fuzz job):
//
//	go test ./pkg/hub/ -fuzz=FuzzParseMessage -fuzztime=30s
//
// Crash corpora are stored in testdata/fuzz/FuzzParseMessage/ and replayed
// automatically by `go test ./pkg/hub/...` without the -fuzz flag.
package hub

import (
	"encoding/json"
	"strings"
	"testing"
)

// FuzzParseMessage verifies that json.Unmarshal into Message never panics,
// regardless of the input byte sequence.  This mirrors the production parse path
// in client.go:ReadPump — if it can panic there, it will panic here first.
func FuzzParseMessage(f *testing.F) {
	// Seed corpus: valid messages the hub actually processes.
	f.Add([]byte(`{"type":"chat_message","room":"room-uuid","payload":{"content":"hello"}}`))
	f.Add([]byte(`{"type":"join","room":"another-room"}`))
	f.Add([]byte(`{"type":"leave","room":"some-room"}`))
	f.Add([]byte(`{"type":"ping"}`))
	f.Add([]byte(`{}`))
	f.Add([]byte(`[]`))
	f.Add([]byte(``))
	f.Add([]byte(`null`))
	// Edge cases: extremely long strings, binary data, nested structures.
	f.Add([]byte(`{"type":"` + strings.Repeat("x", 10_000) + `"}`))
	f.Add([]byte(`{"type":true}`))
	f.Add([]byte(`{"payload":{"nested":{"deeply":{"keys":` + strings.Repeat(`{"a":`, 50) + `{}` + strings.Repeat("}", 50) + `}}}}`))

	f.Fuzz(func(t *testing.T, data []byte) {
		// Must not panic on any input — exactly the guarantee the production code needs.
		var msg Message
		_ = json.Unmarshal(data, &msg) //nolint:errcheck // fuzz: intentionally ignore parse errors

		// If unmarshal succeeded, accessing fields must not panic.
		_ = msg.Type
		_ = msg.Room
		_ = msg.From
		_ = msg.To
		_ = len(msg.Payload)
	})
}

// FuzzExtractAlgFromHeader verifies that extractAlgFromHeader never panics.
// Inputs include malformed base64, truncated headers, and adversarial JWTs.
func FuzzExtractAlgFromHeader(f *testing.F) {
	// Valid JWT header: {"alg":"RS256","typ":"JWT"} base64url-encoded.
	f.Add("eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.payload.signature")
	// HS256 variant.
	f.Add("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.payload.signature")
	// Malformed: only 2 parts.
	f.Add("eyJhbGciOiJSUzI1NiJ9.payload")
	// Malformed: invalid base64.
	f.Add("!!!.payload.signature")
	// Empty string.
	f.Add("")
	// Header with missing alg.
	f.Add("e30K.payload.signature") // base64url of '{}'
	// Algorithm injection attempt.
	f.Add(`eyJhbGciOiJub25lIn0.payload.signature`) // {"alg":"none"}

	f.Fuzz(func(t *testing.T, token string) {
		// Must not panic on any input.
		_, _ = extractAlgFromHeader(token) //nolint:errcheck // fuzz: intentionally ignore errors
	})
}
