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
// CI budget (20s per target, see .github/workflows/ci.yml go-fuzz job):
//
//	bash ../../scripts/ci/run-go-fuzz.sh ./pkg/hub FuzzParseMessage -fuzztime=20s -parallel=1 -timeout=3m
//	bash ../../scripts/ci/run-go-fuzz.sh ./pkg/hub FuzzParseResumeToken -fuzztime=20s -parallel=1 -timeout=3m
//
// Crash corpora are stored in testdata/fuzz/FuzzParseMessage/ and replayed
// automatically by `go test ./pkg/hub/...` without the -fuzz flag.
package hub

import (
	"crypto/rand"
	"encoding/base64"
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

// FuzzParseResumeToken exercises the current replay-token parser, including
// authenticated payload decoding. Random tokens alone almost always stop at the
// signature check and would leave the JSON claims parser unexplored.
func FuzzParseResumeToken(f *testing.F) {
	// Each run uses a fresh test-only signing key; all assertions are key-independent.
	var key [32]byte
	if _, err := rand.Read(key[:]); err != nil {
		f.Fatal(err)
	}
	secret := string(key[:])
	for _, seed := range []string{
		`{"v":1,"uid":"user","room":"room","stream":"CHAT_EVENTS","inc":"generation","seq":7,"exp":2000000000}`,
		`{"seq":18446744073709551615,"exp":-1}`,
		`{"seq":-1}`, `{"seq":1.5}`, `{"seq":"7"}`, `{"exp":9223372036854775808}`,
		`{}`, `null`, `[]`, ``, `not-json`, `.`, `payload.%%%`, `payload.signature.extra`,
		strings.Repeat("x", 4097),
		"%%%",
		base64.RawURLEncoding.EncodeToString([]byte(`{"seq":7}`)),
	} {
		f.Add([]byte(seed))
	}

	f.Fuzz(func(t *testing.T, data []byte) {
		claims, err := parseResumeToken(string(data), secret)
		if err != nil && claims != (resumeTokenClaims{}) {
			t.Fatal("invalid token returned partial claims")
		}
		if len(data) > 4096 {
			if err == nil {
				t.Fatal("oversized token was accepted")
			}
			return
		}

		// Sign both arbitrary encoded payloads and encoded JSON input with the
		// worker's own key, so signature checks cannot hide decoder paths.
		for _, payloadPart := range []string{string(data), base64.RawURLEncoding.EncodeToString(data)} {
			token := signedTokenPart(secret, payloadPart)
			payload, decodeErr := base64.RawURLEncoding.DecodeString(payloadPart)
			var want resumeTokenClaims
			if decodeErr == nil {
				decodeErr = json.Unmarshal(payload, &want)
			}
			got, parseErr := parseResumeToken(token, secret)
			if len(token) > 4096 || decodeErr != nil {
				if parseErr == nil || got != (resumeTokenClaims{}) {
					t.Fatal("invalid authenticated payload was accepted")
				}
			} else if parseErr != nil || got != want {
				t.Fatalf("valid authenticated payload changed: got %+v, want %+v, error %v", got, want, parseErr)
			}

			if _, err := parseResumeToken(token, secret+"."); err == nil {
				t.Fatal("token authenticated with the wrong key")
			}
			if _, err := parseResumeToken(token+".extra", secret); err == nil {
				t.Fatal("token with an extra segment was accepted")
			}
		}
	})
}
