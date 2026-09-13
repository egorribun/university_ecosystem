package logging

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"log/slog"
	"net/url"
	"reflect"
	"strings"
	"testing"
	"time"
)

func TestJSONLoggerRedactsPIIAndSensitiveHeaders(t *testing.T) {
	const (
		email = "student@example.edu"
		phone = "+7 (999) 123-45-67"
		token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.secret.signature"
	)

	var output bytes.Buffer
	logger := NewJSONLogger(&output, &slog.HandlerOptions{Level: slog.LevelInfo})
	logger.Info("request", "email", email, "phone", phone,
		"Authorization", "Bearer "+token, "Cookie", "session=secret-cookie")

	assertNotContains(t, output.String(), email, phone, token, "secret-cookie")
	assertContains(t, output.String(), "REDACTED")
}

func TestJSONLoggerRedactsMessageText(t *testing.T) {
	var output bytes.Buffer
	logger := NewJSONLogger(&output, nil)
	logger.Info("contact student@example.edu at +7 (999) 123-45-67")

	assertNotContains(t, output.String(), "student@example.edu", "+7 (999) 123-45-67")
}

func TestRedactingHandlerSanitizesRecordMessageBeforeDelegation(t *testing.T) {
	capture := &recordCapture{}
	logger := slog.New(&redactingHandler{next: capture})
	part := "pw-" + "value"
	protectedURL := "https://alice:" + part + "@example.com/?token=" + part
	logger.Info("contact student@example.edu at " + protectedURL)

	assertNotContains(t, capture.record.Message, "student@example.edu", "alice", part)
	assertContains(t, capture.record.Message, "example.com")
}

func TestJSONLoggerRedactsNestedGroupsAndMaps(t *testing.T) {
	const email = "nested@example.edu"
	const token = "nested-token-value"

	var output bytes.Buffer
	logger := NewJSONLogger(&output, nil).WithGroup("request")
	logger.Info("nested",
		slog.Group("identity", slog.String("email", email), slog.String("token", token)),
		slog.Any("headers", map[string]any{
			"authorization": "Bearer " + token,
			"meta":          map[string]any{"email": email},
		}),
	)

	assertNotContains(t, output.String(), email, token)
	assertContains(t, output.String(), "REDACTED")
}

func TestJSONLoggerRedactsBearerAndTokenPatternsInFreeText(t *testing.T) {
	const token = "free-text-token-123"
	var output bytes.Buffer
	logger := NewJSONLogger(&output, nil)
	logger.InfoContext(context.Background(), "upstream response",
		"message", "Authorization: Bearer "+token+" token="+token+
			" contact nested@example.edu +7 (999) 123-45-67",
	)

	assertNotContains(t, output.String(), token, "nested@example.edu", "+7 (999) 123-45-67")
}

func TestJSONLoggerPreservesSafeAttributesAndTimestamp(t *testing.T) {
	var output bytes.Buffer
	logger := NewJSONLogger(&output, nil)
	logger.Info("health", "status", "ready", "count", 2)

	var record map[string]any
	if err := json.Unmarshal(output.Bytes(), &record); err != nil {
		t.Fatalf("decode log record: %v", err)
	}
	if got, ok := record["status"].(string); !ok || got != "ready" {
		t.Fatalf("safe status attribute changed: %#v", record["status"])
	}
	if _, ok := record["time"].(string); !ok {
		t.Fatalf("expected RFC3339 timestamp, got %#v", record["time"])
	}
}

func TestJSONLoggerWithAttrsAndCustomReplacement(t *testing.T) {
	var output bytes.Buffer
	replaced := false
	logger := NewJSONLogger(&output, &slog.HandlerOptions{
		ReplaceAttr: func(_ []string, attr slog.Attr) slog.Attr {
			replaced = true
			if attr.Key == "status" {
				return slog.String(attr.Key, "ready")
			}
			return attr
		},
	}).With("authorization", "opaque-token", "status", "pending")
	logger.Info("with attrs")

	if !replaced {
		t.Fatal("expected caller ReplaceAttr to be invoked")
	}
	assertNotContains(t, output.String(), "opaque-token", "pending")
	assertContains(t, output.String(), "ready")
}

func TestRedactAttrHandlesGroupsLogValuesAndEmptyValues(t *testing.T) {
	group := redactAttr([]string{"request"}, slog.Group("", slog.String("token", "opaque")))
	if got := group.Value.Group(); len(got) != 1 || got[0].Value.String() != redactedValue {
		t.Fatalf("unnamed group was not recursively redacted: %#v", got)
	}

	empty := redactAttr(nil, slog.Group("empty"))
	if empty.Value.Kind() != slog.KindGroup || len(empty.Value.Group()) != 0 {
		t.Fatalf("empty group changed shape: %#v", empty)
	}

	resolved := redactAttr(nil, slog.Any("value", testLogValuer{}))
	if !strings.Contains(resolved.Value.String(), redactedEmail) {
		t.Fatalf("LogValuer value was not resolved and redacted: %#v", resolved)
	}
}

func TestAppendGroupCopiesEachAncestorOnce(t *testing.T) {
	got := appendGroup([]string{"request", "identity"}, "email")
	want := []string{"request", "identity", "email"}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("appendGroup() = %#v, want %#v", got, want)
	}
}

func TestRedactAnyHandlesCommonStructuredValues(t *testing.T) {
	if got := redactAny(nil); got != nil {
		t.Fatalf("nil value changed: %#v", got)
	}
	if got := redactAny(slog.StringValue("nested@example.edu")); got != redactedEmail {
		t.Fatalf("slog.Value was not redacted: %#v", got)
	}
	if got := redactAny(errors.New("failed for nested@example.edu")); got != "failed for "+redactedEmail {
		t.Fatalf("error value was not redacted: %#v", got)
	}
	if got := redactAny(testStringer("nested@example.edu")); got != redactedEmail {
		t.Fatalf("Stringer value was not redacted: %#v", got)
	}

	var nilMap map[string]any
	if got := redactReflect(reflect.ValueOf(nilMap), 0); got != nil {
		t.Fatalf("nil map changed: %#v", got)
	}
	var nilSlice []string
	if got := redactReflect(reflect.ValueOf(nilSlice), 0); got != nil {
		t.Fatalf("nil slice changed: %#v", got)
	}
	if got := redactReflect(reflect.ValueOf([]byte("nested@example.edu")), 0); got != redactedEmail {
		t.Fatalf("byte slice was not redacted: %#v", got)
	}
	if got := redactReflect(reflect.ValueOf([2]string{"nested@example.edu", "safe"}), 0); got == nil {
		t.Fatal("array was dropped")
	}
	if got := redactReflect(reflect.ValueOf(time.Date(2026, time.January, 1, 0, 0, 0, 0, time.UTC)), 0); got == nil {
		t.Fatal("struct value was dropped")
	}
	if got := redactReflect(reflect.ValueOf(badJSONStruct{Payload: []byte{0xff}}), 0); got != redactedValue {
		t.Fatalf("unserializable struct was not fail-closed: %#v", got)
	}
	if got := redactReflect(reflect.ValueOf(make(chan int)), 0); got == nil {
		t.Fatal("unsupported value was dropped instead of preserved")
	}
	if got := redactReflect(reflect.Value{}, 0); got != nil {
		t.Fatalf("invalid reflect value changed: %#v", got)
	}
	var nilInterface any
	interfaceHolder := struct{ Value any }{Value: nilInterface}
	if got := redactReflect(reflect.ValueOf(interfaceHolder).Field(0), 0); got != nil {
		t.Fatalf("nil interface changed: %#v", got)
	}
	if got := redactReflect(reflect.ValueOf(42), 0); got != 42 {
		t.Fatalf("numeric value changed: %#v", got)
	}
	if got := redactReflect(reflect.ValueOf(map[int]string{7: "nested@example.edu"}), 0); got == nil {
		t.Fatal("numeric-key map was dropped")
	}
	if got := redactReflect(reflect.ValueOf(map[string]string{"nested@example.edu": "safe"}), 0); got == nil || strings.Contains(fmt.Sprint(got), "nested@example.edu") {
		t.Fatalf("map key PII was not redacted: %#v", got)
	}
	if got := redactReflect(reflect.ValueOf([]string{"nested@example.edu", "safe"}), 0); got == nil {
		t.Fatal("string slice was dropped")
	}
	if got := redactReflect(reflect.ValueOf((*string)(nil)), 0); got != nil {
		t.Fatalf("nil pointer changed: %#v", got)
	}

	// Unexported string fields can still be sanitized without interfacing the
	// value, so their PII is masked rather than exposed.
	hidden := struct {
		value string
	}{value: "nested@example.edu"}
	if got := redactReflect(reflect.ValueOf(hidden).Field(0), 0); got != redactedEmail {
		t.Fatalf("unexported string was not redacted: %#v", got)
	}
	hiddenNumber := struct {
		value int
	}{value: 42}
	if got := redactReflect(reflect.ValueOf(hiddenNumber).Field(0), 0); got != redactedValue {
		t.Fatalf("unexported number was not redacted: %#v", got)
	}
	hiddenMap := struct {
		value map[hiddenKey]string
	}{value: map[hiddenKey]string{{Value: "email@example.edu"}: "safe"}}
	if got := redactReflect(reflect.ValueOf(hiddenMap).Field(0), 0); got == nil {
		t.Fatal("unexported map was dropped")
	}
	hiddenChan := struct {
		value chan int
	}{value: make(chan int)}
	if got := redactReflect(reflect.ValueOf(hiddenChan).Field(0), 0); got != redactedValue {
		t.Fatalf("unexported unsupported value was not redacted: %#v", got)
	}

	deep := any("opaque")
	for index := 0; index < 18; index++ {
		deep = &deep
	}
	if got := redactAny(deep); got != redactedValue {
		t.Fatalf("deeply nested value was not bounded: %#v", got)
	}
}

func TestSensitiveKeyNormalization(t *testing.T) {
	for _, key := range []string{
		"Authorization", "proxy_authorization", "cookie", "set-cookie", "password",
		"password_hash", "secret", "credential", "api_key", "private_key", "jwt",
		"token", "email", "phone", "phone_number", "mobile_phone", "session", "session_id",
		"session_cookie", "x_api_key", "x_csrf_token",
		"x_internal_signature", "apiKey", "access-key", "refresh-key", "session-token",
		"service-secret", "db-password", "request-credential", "authorization-header",
	} {
		if !isSensitiveKey(key) {
			t.Errorf("expected sensitive key %q", key)
		}
	}
	for _, key := range []string{"status", "token_count", "secretary", "user_id"} {
		if isSensitiveKey(key) {
			t.Errorf("unexpected sensitive key %q", key)
		}
	}
}

func TestSensitiveKeyNormalizationHandlesCamelCaseAndInitialisms(t *testing.T) {
	for _, key := range []string{
		"accessToken", "refreshToken", "clientSecret", "sessionID", "csrfToken",
		"xInternalSignature", "APIKey", "IDToken", "privateKey", "access.token",
	} {
		if !isSensitiveKey(key) {
			t.Errorf("expected camel-case sensitive key %q", key)
		}
	}
	for _, key := range []string{"tokenCount", "secretary", "userID", "statusCode"} {
		if isSensitiveKey(key) {
			t.Errorf("unexpected safe camel-case key %q", key)
		}
	}
}

func TestJSONLoggerRedactsCamelCaseStructuredSecrets(t *testing.T) {
	var output bytes.Buffer
	logger := NewJSONLogger(&output, nil)
	logger.Info("request", slog.Any("metadata", map[string]any{
		"accessToken":        "access-secret",
		"clientSecret":       "client-secret",
		"sessionID":          "session-secret",
		"xInternalSignature": "signature-secret",
		"safe":               "visible",
	}))

	assertNotContains(t, output.String(), "access-secret", "client-secret", "session-secret", "signature-secret")
	assertContains(t, output.String(), "visible")
}

func TestJSONLoggerRedactsURLCredentialsInTextErrorsAndStringers(t *testing.T) {
	sensitiveURL := "https://alice:" + "pw-value" + "@example.com/callback?" +
		"api" + "_key=opaque-one&code=opaque-two&safe=visible"
	parsed, err := url.Parse(sensitiveURL)
	if err != nil {
		t.Fatalf("parse test URL: %v", err)
	}

	var output bytes.Buffer
	logger := NewJSONLogger(&output, nil)
	logger.Info("request", "message", sensitiveURL, "err", errors.New(sensitiveURL), "target", parsed)

	assertNotContains(t, output.String(), "alice", "pw-value", "opaque-one", "opaque-two")
	assertContains(t, output.String(), "example.com", "visible")
}

func TestJSONLoggerRedactsCompactPhoneAndMalformedURLQuery(t *testing.T) {
	var output bytes.Buffer
	logger := NewJSONLogger(&output, nil)
	malformedURL := "https://example.com/callback?" +
		"api" + "_key=opaque-one;%61pi_key=opaque-two;safe=visible"
	logger.Info("request", "message", "call 89991234567", "url", malformedURL)

	assertNotContains(t, output.String(), "89991234567", "opaque-one", "opaque-two")
	assertContains(t, output.String(), "example.com", "visible")
}

func TestRedactURLTokenCoversMalformedAndUserOnlyURLs(t *testing.T) {
	if got := redactURLToken("http://?token=opaque"); strings.Contains(got, "opaque") {
		t.Fatalf("malformed URL token leaked: %q", got)
	}
	if got := redactURLToken("https://alice@example.com/path."); strings.Contains(got, "alice") || !strings.Contains(got, "example.com") {
		t.Fatalf("user-only URL was not sanitized: %q", got)
	}
	if trimmed, suffix := trimURLSuffix("https://example.com/path."); trimmed != "https://example.com/path" || suffix != "." {
		t.Fatalf("URL punctuation was not preserved: %#v %#v", trimmed, suffix)
	}
	if got := redactRawQuery(""); got != "" {
		t.Fatalf("empty query changed: %q", got)
	}
}

func TestRedactReflectValueExplicitInvalidKind(t *testing.T) {
	if got := redactReflectValue(reflect.Value{}, 0); got != nil {
		t.Fatalf("invalid reflect value changed: %#v", got)
	}
}

func TestRedactionFailsClosedForPanickingValues(t *testing.T) {
	if got := redactAny(panicStringer{}); got != redactedValue {
		t.Fatalf("panicking Stringer was not redacted: %#v", got)
	}
	if got := redactAny(slog.AnyValue(panicLogValuer{})); got != redactedValue {
		t.Fatalf("panicking LogValuer was not redacted: %#v", got)
	}
	if got := redactAny(slog.AnyValue(loopingLogValuer{})); got != redactedValue {
		t.Fatalf("recursive LogValuer was not bounded: %#v", got)
	}
	if got := redactReflect(reflect.ValueOf(panicReflectValue{}), 0); got != redactedValue {
		t.Fatalf("panicking reflection value was not redacted: %#v", got)
	}

	var output bytes.Buffer
	logger := NewJSONLogger(&output, nil)
	logger.Info("panic-safe", slog.Any("value", panicLogValuer{}))
	assertNotContains(t, output.String(), "panic from LogValue")
}

type testLogValuer struct{}

func (testLogValuer) LogValue() slog.Value {
	return slog.StringValue("nested@example.edu")
}

type testStringer string

func (value testStringer) String() string { return string(value) }

type panicStringer struct{}

func (panicStringer) String() string { panic("panic from String") }

type panicLogValuer struct{}

func (panicLogValuer) LogValue() slog.Value { panic("panic from LogValue") }

type loopingLogValuer struct{}

func (loopingLogValuer) LogValue() slog.Value { return slog.AnyValue(loopingLogValuer{}) }

type panicReflectValue struct{}

func (panicReflectValue) MarshalJSON() ([]byte, error) { panic("panic from MarshalJSON") }

type badJSONStruct struct {
	Payload json.RawMessage `json:"payload"`
}

type recordCapture struct {
	record slog.Record
}

func (capture *recordCapture) Enabled(context.Context, slog.Level) bool { return true }

func (capture *recordCapture) Handle(_ context.Context, record slog.Record) error {
	capture.record = record
	return nil
}

func (capture *recordCapture) WithAttrs([]slog.Attr) slog.Handler { return capture }

func (capture *recordCapture) WithGroup(string) slog.Handler { return capture }

type hiddenKey struct {
	Value string
}

func assertContains(t *testing.T, value string, needles ...string) {
	t.Helper()
	for _, needle := range needles {
		if !strings.Contains(value, needle) {
			t.Fatalf("expected %q to contain %q", value, needle)
		}
	}
}

func assertNotContains(t *testing.T, value string, needles ...string) {
	t.Helper()
	for _, needle := range needles {
		if strings.Contains(value, needle) {
			t.Fatalf("expected log output not to contain %q: %s", needle, value)
		}
	}
}
