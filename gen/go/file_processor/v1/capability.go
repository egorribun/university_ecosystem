package file_processorv1

// This file intentionally lives beside the generated transport types so the
// gateway and file-processor use one byte-for-byte capability contract without
// duplicating security-sensitive signing code in two Go modules.

import (
	"context"
	"crypto/hmac"
	"crypto/rand"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"errors"
	"fmt"
	"strings"
	"time"
)

const (
	ProcessingCapabilityHeader      = "X-File-Processing-Capability"
	processingCapabilityVersion     = "v1"
	processingCapabilityDomain      = "university-ecosystem/file-processing-capability/v1"
	processingCapabilityMaxTTL      = 15 * time.Minute
	processingCapabilityNonceLen    = 24
	processingCapabilityMaxTokenLen = 4096
)

// ProcessingCapabilityClaims is the signed authorization proof issued by the
// trusted backend after it has checked object ownership and permissions.
// Storage keys are deliberately bound exactly, not by a caller-controlled
// prefix, so a valid proof cannot be replayed for a different object.
type ProcessingCapabilityClaims struct {
	ID        string
	Type      string
	SourceKey string
	DestKey   string
	UserID    string
	SessionID string
	TenantID  string
	ExpiresAt int64
	Nonce     string
}

// ProcessingCapabilityExpectation describes the request fields that a proof
// must match at a transport boundary.
type ProcessingCapabilityExpectation struct {
	ID        string
	Type      string
	SourceKey string
	DestKey   string
	UserID    string
	SessionID string
	TenantID  string
}

// ProcessingIdentity is the authenticated JWT identity attached to a request.
// It is kept in a shared package so HTTP/gRPC middleware and the service cannot
// accidentally use different context-key types.
type ProcessingIdentity struct {
	UserID    string
	SessionID string
	TenantID  string
}

type processingIdentityContextKey struct{}

// WithProcessingIdentity attaches verified JWT identity to a request context.
func WithProcessingIdentity(ctx context.Context, identity ProcessingIdentity) context.Context {
	return context.WithValue(ctx, processingIdentityContextKey{}, identity)
}

// ProcessingIdentityFromContext returns the identity established by the
// transport authentication middleware. A missing identity is never treated as
// anonymous for capability-bound operations.
func ProcessingIdentityFromContext(ctx context.Context) (ProcessingIdentity, bool) {
	identity, ok := ctx.Value(processingIdentityContextKey{}).(ProcessingIdentity)
	if !ok || identity.UserID == "" || identity.SessionID == "" {
		return ProcessingIdentity{}, false
	}
	return identity, true
}

// MintProcessingCapability mints a short-lived proof using the current UTC
// clock. Callers that need deterministic tests can use the At variant.
func MintProcessingCapability(secret []byte, claims ProcessingCapabilityClaims) (string, error) {
	return MintProcessingCapabilityAt(secret, claims, time.Now().UTC())
}

// MintProcessingCapabilityAt is the deterministic/testable capability issuer.
func MintProcessingCapabilityAt(secret []byte, claims ProcessingCapabilityClaims, now time.Time) (string, error) {
	if len(secret) < 32 {
		return "", errors.New("processing capability secret must contain at least 32 bytes")
	}
	if claims.Nonce == "" {
		raw := make([]byte, processingCapabilityNonceLen)
		if _, err := rand.Read(raw); err != nil {
			return "", fmt.Errorf("generate processing capability nonce: %w", err)
		}
		claims.Nonce = base64.RawURLEncoding.EncodeToString(raw)
	}
	if err := validateClaims(claims, now); err != nil {
		return "", err
	}
	parts, err := encodeClaims(claims)
	if err != nil {
		return "", err
	}
	payload := strings.Join(parts, ".")
	return payload + "." + hex.EncodeToString(capabilityMAC(secret, payload)), nil
}

// VerifyProcessingCapability verifies the MAC, lifetime and shape of a proof.
// It does not authorize a request by itself; callers must compare the returned
// claims to the authenticated identity and exact request fields.
func VerifyProcessingCapability(token string, secret []byte, now time.Time) (ProcessingCapabilityClaims, error) {
	if len(secret) < 32 {
		return ProcessingCapabilityClaims{}, errors.New("processing capability secret is not configured")
	}
	if len(token) == 0 || len(token) > processingCapabilityMaxTokenLen {
		return ProcessingCapabilityClaims{}, errors.New("processing capability has invalid length")
	}
	parts := strings.Split(token, ".")
	if len(parts) != 11 || parts[0] != processingCapabilityVersion {
		return ProcessingCapabilityClaims{}, errors.New("processing capability has invalid format")
	}
	payload := strings.Join(parts[:10], ".")
	providedMAC, err := hex.DecodeString(parts[10])
	if err != nil || len(providedMAC) != sha256.Size {
		return ProcessingCapabilityClaims{}, errors.New("processing capability has invalid signature")
	}
	if !hmac.Equal(providedMAC, capabilityMAC(secret, payload)) {
		return ProcessingCapabilityClaims{}, errors.New("processing capability signature mismatch")
	}
	claims, err := decodeClaims(parts[1:10])
	if err != nil {
		return ProcessingCapabilityClaims{}, err
	}
	if err := validateClaims(claims, now); err != nil {
		return ProcessingCapabilityClaims{}, err
	}
	return claims, nil
}

// Matches compares every security-relevant field in constant time where a
// string comparison could otherwise become an oracle. The final result is
// intentionally all-or-nothing; callers must not accept partial matches.
func (claims ProcessingCapabilityClaims) Matches(expected ProcessingCapabilityExpectation) bool {
	values := [7][2]string{
		{claims.ID, expected.ID},
		{claims.Type, expected.Type},
		{claims.SourceKey, expected.SourceKey},
		{claims.DestKey, expected.DestKey},
		{claims.UserID, expected.UserID},
		{claims.SessionID, expected.SessionID},
		{claims.TenantID, expected.TenantID},
	}
	matched := true
	for _, pair := range values {
		// Do not short-circuit the comparisons: every field participates in the
		// same amount of work even when an earlier claim is wrong.
		if !hmac.Equal([]byte(pair[0]), []byte(pair[1])) {
			matched = false
		}
	}
	return matched
}

func capabilityMAC(secret []byte, payload string) []byte {
	mac := hmac.New(sha256.New, secret)
	mac.Write([]byte(processingCapabilityDomain))
	mac.Write([]byte{0})
	mac.Write([]byte(payload))
	return mac.Sum(nil)
}

func validateClaims(claims ProcessingCapabilityClaims, now time.Time) error {
	for name, value := range map[string]string{
		"id": claims.ID, "type": claims.Type, "source_key": claims.SourceKey,
		"dest_key": claims.DestKey, "user_id": claims.UserID,
		"session_id": claims.SessionID, "nonce": claims.Nonce,
	} {
		if value == "" || strings.ContainsRune(value, '\x00') {
			return fmt.Errorf("processing capability %s is invalid", name)
		}
	}
	if strings.ContainsRune(claims.TenantID, '\x00') {
		return errors.New("processing capability tenant_id is invalid")
	}
	if len(claims.ID) > 256 || len(claims.Type) > 64 || len(claims.SourceKey) > 1024 || len(claims.DestKey) > 1024 || len(claims.UserID) > 256 || len(claims.SessionID) > 256 || len(claims.TenantID) > 256 || len(claims.Nonce) > 128 {
		return errors.New("processing capability claim is too long")
	}
	if claims.ExpiresAt <= now.Unix() {
		return errors.New("processing capability has expired")
	}
	if time.Unix(claims.ExpiresAt, 0).After(now.Add(processingCapabilityMaxTTL)) {
		return errors.New("processing capability lifetime exceeds limit")
	}
	return nil
}

func encodeClaims(claims ProcessingCapabilityClaims) ([]string, error) {
	encode := func(value string) string { return base64.RawURLEncoding.EncodeToString([]byte(value)) }
	return []string{
		processingCapabilityVersion,
		encode(claims.ID), encode(claims.Type), encode(claims.SourceKey),
		encode(claims.DestKey), encode(claims.UserID), encode(claims.SessionID),
		encode(claims.TenantID), fmt.Sprintf("%d", claims.ExpiresAt), encode(claims.Nonce),
	}, nil
}

func decodeClaims(parts []string) (ProcessingCapabilityClaims, error) {
	if len(parts) != 9 {
		return ProcessingCapabilityClaims{}, errors.New("processing capability has invalid claims")
	}
	decode := func(value string) (string, error) {
		decoded, err := base64.RawURLEncoding.DecodeString(value)
		if err != nil {
			return "", errors.New("processing capability has invalid encoding")
		}
		return string(decoded), nil
	}
	values := make([]string, 7)
	for i := range values {
		value, err := decode(parts[i])
		if err != nil {
			return ProcessingCapabilityClaims{}, err
		}
		values[i] = value
	}
	var expiresAt int64
	if _, err := fmt.Sscan(parts[7], &expiresAt); err != nil {
		return ProcessingCapabilityClaims{}, errors.New("processing capability has invalid expiry")
	}
	nonce, err := decode(parts[8])
	if err != nil {
		return ProcessingCapabilityClaims{}, err
	}
	return ProcessingCapabilityClaims{
		ID: values[0], Type: values[1], SourceKey: values[2], DestKey: values[3],
		UserID: values[4], SessionID: values[5], TenantID: values[6],
		ExpiresAt: expiresAt, Nonce: nonce,
	}, nil
}
