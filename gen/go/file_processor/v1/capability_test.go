package file_processorv1

import (
	"context"
	"encoding/base64"
	"fmt"
	"strings"
	"testing"
	"time"
)

var testCapabilityKey = strings.Repeat("k", 32)

func testCapabilityClaims(now time.Time) ProcessingCapabilityClaims {
	return ProcessingCapabilityClaims{
		ID:        "job-123",
		Type:      "image_resize",
		SourceKey: "users/u-1/source.png",
		DestKey:   "users/u-1/dest.png",
		UserID:    "u-1",
		SessionID: "session-1",
		TenantID:  "tenant-1",
		ExpiresAt: now.Add(5 * time.Minute).Unix(),
		Nonce:     "nonce-1234567890",
	}
}

func TestProcessingCapabilityRoundTrip(t *testing.T) {
	now := time.Unix(1_700_000_000, 0)
	claims := testCapabilityClaims(now)
	token, err := MintProcessingCapabilityAt([]byte(testCapabilityKey), claims, now)
	if err != nil {
		t.Fatalf("MintProcessingCapability() error = %v", err)
	}
	got, err := VerifyProcessingCapability(token, []byte(testCapabilityKey), now)
	if err != nil {
		t.Fatalf("VerifyProcessingCapability() error = %v", err)
	}
	if got != claims {
		t.Fatalf("claims mismatch: got %#v want %#v", got, claims)
	}
	if !got.Matches(ProcessingCapabilityExpectation{
		ID:        claims.ID,
		Type:      claims.Type,
		SourceKey: claims.SourceKey,
		DestKey:   claims.DestKey,
		UserID:    claims.UserID,
		SessionID: claims.SessionID,
		TenantID:  claims.TenantID,
	}) {
		t.Fatal("valid capability did not match its expected request")
	}
}

func TestProcessingCapabilityRejectsTamperingAndExpiry(t *testing.T) {
	now := time.Unix(1_700_000_000, 0)
	claims := testCapabilityClaims(now)
	token, err := MintProcessingCapabilityAt([]byte(testCapabilityKey), claims, now)
	if err != nil {
		t.Fatal(err)
	}
	parts := strings.Split(token, ".")
	parts[2] = "dGFtcGVyZWQ"
	if _, err := VerifyProcessingCapability(strings.Join(parts, "."), []byte(testCapabilityKey), now); err == nil {
		t.Fatal("tampered capability was accepted")
	}
	if _, err := VerifyProcessingCapability(token, []byte(testCapabilityKey), time.Unix(claims.ExpiresAt, 0)); err == nil {
		t.Fatal("expired capability was accepted")
	}
	for _, signature := range []string{"!", "00"} {
		parts := strings.Split(token, ".")
		parts[10] = signature
		if _, err := VerifyProcessingCapability(strings.Join(parts, "."), []byte(testCapabilityKey), now); err == nil {
			t.Fatalf("invalid signature %q was accepted", signature)
		}
	}
}

func TestProcessingCapabilityRejectsMalformedAndWeakInputs(t *testing.T) {
	now := time.Unix(1_700_000_000, 0)
	claims := testCapabilityClaims(now)
	if _, err := MintProcessingCapabilityAt([]byte("short"), claims, now); err == nil {
		t.Fatal("weak secret was accepted")
	}
	if _, err := VerifyProcessingCapability("v1", []byte("short"), now); err == nil {
		t.Fatal("weak verification secret was accepted")
	}
	if _, err := VerifyProcessingCapability("v1", []byte(testCapabilityKey), now); err == nil {
		t.Fatal("malformed capability was accepted")
	}
	if _, err := VerifyProcessingCapability(strings.Repeat("x", processingCapabilityMaxTokenLen+1), []byte(testCapabilityKey), now); err == nil {
		t.Fatal("oversized capability was accepted")
	}
	claims.ExpiresAt = now.Add(48 * time.Hour).Unix()
	if _, err := MintProcessingCapabilityAt([]byte(testCapabilityKey), claims, now); err == nil {
		t.Fatal("long-lived capability was accepted")
	}
}

func TestMintProcessingCapability_GeneratesNonce(t *testing.T) {
	now := time.Now().UTC()
	claims := testCapabilityClaims(now)
	claims.Nonce = ""
	token, err := MintProcessingCapability([]byte(testCapabilityKey), claims)
	if err != nil {
		t.Fatalf("MintProcessingCapability() error = %v", err)
	}
	got, err := VerifyProcessingCapability(token, []byte(testCapabilityKey), time.Now().UTC())
	if err != nil {
		t.Fatalf("VerifyProcessingCapability() error = %v", err)
	}
	if got.Nonce == "" {
		t.Fatal("generated nonce is empty")
	}
}

func TestProcessingCapabilityRejectsMalformedSignedClaims(t *testing.T) {
	now := time.Unix(1_700_000_000, 0)
	claims := testCapabilityClaims(now)
	parts, err := encodeClaims(claims)
	if err != nil {
		t.Fatal(err)
	}

	tests := []struct {
		name   string
		mutate func([]string)
	}{
		{name: "invalid claim encoding", mutate: func(parts []string) { parts[1] = "!" }},
		{name: "invalid expiry", mutate: func(parts []string) { parts[8] = "not-an-integer" }},
		{name: "invalid nonce encoding", mutate: func(parts []string) { parts[9] = "!" }},
		{name: "empty required claim", mutate: func(parts []string) { parts[5] = "" }},
		{name: "tenant NUL", mutate: func(parts []string) {
			parts[7] = base64.RawURLEncoding.EncodeToString([]byte("tenant\x00id"))
		}},
		{name: "too-long claim", mutate: func(parts []string) {
			parts[1] = base64.RawURLEncoding.EncodeToString([]byte(strings.Repeat("x", 257)))
		}},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			mutated := append([]string(nil), parts...)
			tc.mutate(mutated)
			payload := strings.Join(mutated, ".")
			token := payload + "." + hexCapabilityMAC([]byte(testCapabilityKey), payload)
			if _, err := VerifyProcessingCapability(token, []byte(testCapabilityKey), now); err == nil {
				t.Fatal("malformed signed capability was accepted")
			}
		})
	}
}

func TestDecodeClaimsRejectsMalformedInputs(t *testing.T) {
	now := time.Unix(1_700_000_000, 0)
	parts, err := encodeClaims(testCapabilityClaims(now))
	if err != nil {
		t.Fatal(err)
	}

	if _, err := decodeClaims(parts[:8]); err == nil {
		t.Fatal("short claims were accepted")
	}
	invalidEncoding := append([]string(nil), parts...)
	invalidEncoding[1] = "!"
	if _, err := decodeClaims(invalidEncoding[1:]); err == nil {
		t.Fatal("invalid claim encoding was accepted")
	}
	invalidExpiry := append([]string(nil), parts...)
	invalidExpiry[8] = "not-an-integer"
	if _, err := decodeClaims(invalidExpiry[1:]); err == nil {
		t.Fatal("invalid expiry was accepted")
	}
	invalidNonce := append([]string(nil), parts...)
	invalidNonce[9] = "!"
	if _, err := decodeClaims(invalidNonce[1:]); err == nil {
		t.Fatal("invalid nonce encoding was accepted")
	}
}

func TestProcessingCapabilityRejectsInvalidClaimShapes(t *testing.T) {
	now := time.Unix(1_700_000_000, 0)
	base := testCapabilityClaims(now)
	tests := []struct {
		name   string
		mutate func(*ProcessingCapabilityClaims)
	}{
		{name: "empty id", mutate: func(c *ProcessingCapabilityClaims) { c.ID = "" }},
		{name: "NUL in type", mutate: func(c *ProcessingCapabilityClaims) { c.Type = "image\x00resize" }},
		{name: "NUL in source", mutate: func(c *ProcessingCapabilityClaims) { c.SourceKey = "source\x00key" }},
		{name: "NUL in destination", mutate: func(c *ProcessingCapabilityClaims) { c.DestKey = "dest\x00key" }},
		{name: "NUL in user", mutate: func(c *ProcessingCapabilityClaims) { c.UserID = "user\x00id" }},
		{name: "NUL in session", mutate: func(c *ProcessingCapabilityClaims) { c.SessionID = "session\x00id" }},
		{name: "NUL in nonce", mutate: func(c *ProcessingCapabilityClaims) { c.Nonce = "nonce\x00id" }},
		{name: "NUL in tenant", mutate: func(c *ProcessingCapabilityClaims) { c.TenantID = "tenant\x00id" }},
		{name: "long type", mutate: func(c *ProcessingCapabilityClaims) { c.Type = strings.Repeat("x", 65) }},
		{name: "long source", mutate: func(c *ProcessingCapabilityClaims) { c.SourceKey = strings.Repeat("x", 1025) }},
		{name: "long destination", mutate: func(c *ProcessingCapabilityClaims) { c.DestKey = strings.Repeat("x", 1025) }},
		{name: "long user", mutate: func(c *ProcessingCapabilityClaims) { c.UserID = strings.Repeat("x", 257) }},
		{name: "long session", mutate: func(c *ProcessingCapabilityClaims) { c.SessionID = strings.Repeat("x", 257) }},
		{name: "long tenant", mutate: func(c *ProcessingCapabilityClaims) { c.TenantID = strings.Repeat("x", 257) }},
		{name: "long nonce", mutate: func(c *ProcessingCapabilityClaims) { c.Nonce = strings.Repeat("x", 129) }},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			claims := base
			tc.mutate(&claims)
			if _, err := MintProcessingCapabilityAt([]byte(testCapabilityKey), claims, now); err == nil {
				t.Fatal("invalid claim shape was accepted")
			}
		})
	}
}

func TestProcessingCapabilityMatchesRejectsAnyFieldMismatch(t *testing.T) {
	now := time.Unix(1_700_000_000, 0)
	claims := testCapabilityClaims(now)
	expected := ProcessingCapabilityExpectation{
		ID: claims.ID, Type: claims.Type, SourceKey: claims.SourceKey,
		DestKey: claims.DestKey, UserID: claims.UserID, SessionID: claims.SessionID,
		TenantID: claims.TenantID,
	}
	fields := []struct {
		name   string
		mutate func(*ProcessingCapabilityExpectation)
	}{
		{name: "id", mutate: func(e *ProcessingCapabilityExpectation) { e.ID += "-other" }},
		{name: "type", mutate: func(e *ProcessingCapabilityExpectation) { e.Type += "-other" }},
		{name: "source", mutate: func(e *ProcessingCapabilityExpectation) { e.SourceKey += "-other" }},
		{name: "destination", mutate: func(e *ProcessingCapabilityExpectation) { e.DestKey += "-other" }},
		{name: "user", mutate: func(e *ProcessingCapabilityExpectation) { e.UserID += "-other" }},
		{name: "session", mutate: func(e *ProcessingCapabilityExpectation) { e.SessionID += "-other" }},
		{name: "tenant", mutate: func(e *ProcessingCapabilityExpectation) { e.TenantID += "-other" }},
	}
	for _, tc := range fields {
		t.Run(tc.name, func(t *testing.T) {
			mismatch := expected
			tc.mutate(&mismatch)
			if claims.Matches(mismatch) {
				t.Fatal("mismatched expectation was accepted")
			}
		})
	}
}

func TestProcessingIdentityContextRejectsIncompleteIdentity(t *testing.T) {
	for _, identity := range []ProcessingIdentity{{UserID: "", SessionID: "session"}, {UserID: "user", SessionID: ""}} {
		ctx := WithProcessingIdentity(t.Context(), identity)
		if _, ok := ProcessingIdentityFromContext(ctx); ok {
			t.Fatalf("incomplete identity unexpectedly resolved: %#v", identity)
		}
	}
	if _, ok := ProcessingIdentityFromContext(context.WithValue(t.Context(), processingIdentityContextKey{}, "not-an-identity")); ok {
		t.Fatal("wrong context value unexpectedly resolved")
	}
}

func hexCapabilityMAC(secret []byte, payload string) string {
	return fmt.Sprintf("%x", capabilityMAC(secret, payload))
}

func TestProcessingCapabilityIdentityContext(t *testing.T) {
	identity := ProcessingIdentity{UserID: "u-1", SessionID: "session-1", TenantID: "tenant-1"}
	ctx := WithProcessingIdentity(t.Context(), identity)
	got, ok := ProcessingIdentityFromContext(ctx)
	if !ok || got != identity {
		t.Fatalf("identity context mismatch: got %#v, ok=%v", got, ok)
	}
	if _, ok := ProcessingIdentityFromContext(t.Context()); ok {
		t.Fatal("missing identity unexpectedly resolved")
	}
}
