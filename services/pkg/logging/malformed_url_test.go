package logging

import (
	"bytes"
	"fmt"
	"log/slog"
	"net/url"
	"testing"
)

func TestMalformedURLCredentialsFailClosedAcrossLoggerPaths(t *testing.T) {
	const secret = "opaqueCredentialCanary"
	for _, endpoint := range []string{
		"redis://reader:" + secret + "@localhost:bad",
		"redis://reader:" + secret + "@localhost/%zz",
		"redis://reader:" + secret + "%zz@localhost",
		"redis://reader:" + secret + "@[::1",
	} {
		t.Run(endpoint, func(t *testing.T) {
			_, parseErr := url.Parse(endpoint)
			if parseErr == nil {
				t.Fatal("fixture must exercise actual URL parser failure")
			}
			assertContains(t, parseErr.Error(), secret)
			for _, path := range []string{
				"message", "attribute", "error", "stringer", "with",
				"group", "map", "bytes", "struct", "replacement",
			} {
				t.Run(path, func(t *testing.T) {
					var output bytes.Buffer
					options := &slog.HandlerOptions{}
					if path == "replacement" {
						options.ReplaceAttr = func(_ []string, attr slog.Attr) slog.Attr {
							if attr.Key == "diagnostic" {
								return slog.String(attr.Key, endpoint)
							}
							return attr
						}
					}
					logger := NewJSONLogger(&output, options)
					switch path {
					case "message":
						logger.Error("connection failed: " + endpoint + ". retry later")
					case "attribute":
						logger.Error("connection failed", "diagnostic", endpoint)
					case "error":
						logger.Error("connection failed", "err", fmt.Errorf("parse Redis configuration: %w", parseErr))
					case "stringer":
						logger.Error("connection failed", "diagnostic", testStringer(endpoint))
					case "with":
						logger.With("diagnostic", endpoint).Error("connection failed")
					case "group":
						logger.WithGroup("upstream").Error("connection failed", slog.Group("config", "diagnostic", endpoint))
					case "map":
						logger.Error("connection failed", "diagnostic", map[string]any{endpoint: []any{endpoint}})
					case "bytes":
						logger.Error("connection failed", "diagnostic", []byte(endpoint))
					case "struct":
						logger.Error("connection failed", "diagnostic", struct{ Endpoint string }{endpoint})
					case "replacement":
						logger.Error("connection failed", "diagnostic", "safe")
					}
					assertNotContains(t, output.String(), secret, "reader")
					assertContains(t, output.String(), "connection failed", "REDACTED")
				})
			}
		})
	}
}

func TestURLRedactionPreservesSafeTextAndValidHostlessPaths(t *testing.T) {
	for _, input := range []string{
		"ordinary diagnostic: invalid port; retry later",
		"https://example.test/health?status=ready",
		"file:///tmp/health.log",
	} {
		if got := redactString(input); got != input {
			t.Fatalf("safe diagnostic changed: got %q, want %q", got, input)
		}
	}
	if got := redactString("before redis://reader:opaqueCredentialCanary@localhost:bad. after"); got != "before "+redactedValue+". after" {
		t.Fatalf("surrounding diagnostic or punctuation changed: %q", got)
	}
	// Hostless URLs can still carry userinfo; successful parsing must not
	// bypass the ordinary credential sanitizer merely because Host is empty.
	assertNotContains(t, redactString("redis://reader:opaqueCredentialCanary@"), "reader", "opaqueCredentialCanary")
}
