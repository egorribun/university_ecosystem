// Package logging provides the JSON slog handler shared by the Go services.
//
// The handler is deliberately placed at the service boundary: every record is
// sanitized before it reaches a concrete output handler, including attributes
// attached with Logger.With and values nested in groups or maps. This keeps
// redaction independent from individual call sites and prevents a new service
// from accidentally emitting credentials or personal data to Loki.
package logging

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log/slog"
	"net/url"
	"reflect"
	"regexp"
	"strings"
)

const (
	redactedValue = "[REDACTED]"

	// Keep the marker stable so dashboards and security scanners can identify
	// intentional redaction without depending on a particular field name.
	redactedEmail = "[REDACTED_EMAIL]"
	redactedPhone = "[REDACTED_PHONE]"
	textMask      = "[REDACTED_BEARER]"
	valueMask     = "[REDACTED_TOKEN]"
)

var (
	// These expressions intentionally match only values, never log keys. The
	// key-aware pass below handles credentials that do not have a recognizable
	// textual format (for example opaque session tokens).
	emailPattern = regexp.MustCompile(`(?i)\b[[:alnum:]][[:alnum:]._%+\-']*@[[:alnum:]][[:alnum:]\-]*(?:\.[[:alnum:]][[:alnum:]\-]*)+\b`)
	// Require an explicit country/area marker or three conventional groups so
	// timestamps and ordinary numeric identifiers are not mistaken for phones.
	phonePattern              = regexp.MustCompile(`(?:\+\d{1,3}[\s.-]?(?:\(\d{2,4}\)|\d{2,4})[\s.-]?(?:\d{2,4}[\s.-]?){1,3}\d{2,4}|\(\d{2,4}\)[\s.-]?(?:\d{2,4}[\s.-]?){2,3}\d{2,4}|\b\d{3}[-.\s]\d{3}[-.\s]\d{4}\b|\b(?:\d[\s.-]?){9,14}\d\b)`)
	bearerPattern             = regexp.MustCompile(`(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+`)
	tokenPattern              = regexp.MustCompile(`(?i)\b(?:access[_-]?|refresh[_-]?|id[_-]?|mfa[_-]?|csrf[_-]?)?token\s*[:=]\s*[^\s,;]+`)
	camelBoundaryPattern      = regexp.MustCompile(`([a-z0-9])([A-Z])`)
	initialismBoundaryPattern = regexp.MustCompile(`([A-Z]+)([A-Z][a-z])`)
	embeddedURLPattern        = regexp.MustCompile(`(?i)\b[a-z][a-z0-9+.-]*://[^\s<>"']+`)
)

// NewJSONHandler returns a JSON slog handler with timestamp normalization and
// recursive PII/credential redaction. The supplied options are copied, so the
// caller's options are never mutated. A caller-provided ReplaceAttr is still
// honored before the final redaction pass.
func NewJSONHandler(writer io.Writer, options *slog.HandlerOptions) slog.Handler {
	var opts slog.HandlerOptions
	if options != nil {
		opts = *options
	} else {
		opts.Level = slog.LevelInfo
	}

	callerReplace := opts.ReplaceAttr
	opts.ReplaceAttr = func(groups []string, attr slog.Attr) slog.Attr {
		if callerReplace != nil {
			attr = callerReplace(groups, attr)
		}
		if attr.Key == slog.TimeKey && attr.Value.Kind() == slog.KindTime {
			// Keep the value typed as time.Time so the downstream JSON handler
			// formats it safely; converting to a string first would make the
			// phone scrubber mistake RFC3339 date fragments for phone numbers.
			attr.Value = slog.TimeValue(attr.Value.Time().UTC())
		}
		return redactAttr(groups, attr)
	}

	return &redactingHandler{next: slog.NewJSONHandler(writer, &opts)}
}

// NewJSONLogger constructs a slog logger backed by NewJSONHandler.
func NewJSONLogger(writer io.Writer, options *slog.HandlerOptions) *slog.Logger {
	return slog.New(NewJSONHandler(writer, options))
}

// redactingHandler sanitizes records before delegating to the standard JSON
// handler. ReplaceAttr alone cannot inspect nested values held in slog.Any,
// hence the record-level pass in Handle.
type redactingHandler struct {
	next slog.Handler
}

func (h *redactingHandler) Enabled(ctx context.Context, level slog.Level) bool {
	return h.next.Enabled(ctx, level)
}

func (h *redactingHandler) Handle(ctx context.Context, record slog.Record) error {
	sanitized := slog.NewRecord(record.Time, record.Level, redactString(record.Message), record.PC)
	record.Attrs(func(attr slog.Attr) bool {
		sanitized.AddAttrs(redactAttr(nil, attr))
		return true
	})
	return h.next.Handle(ctx, sanitized)
}

func (h *redactingHandler) WithAttrs(attrs []slog.Attr) slog.Handler {
	sanitized := make([]slog.Attr, 0, len(attrs))
	for _, attr := range attrs {
		sanitized = append(sanitized, redactAttr(nil, attr))
	}
	return &redactingHandler{next: h.next.WithAttrs(sanitized)}
}

func (h *redactingHandler) WithGroup(name string) slog.Handler {
	return &redactingHandler{next: h.next.WithGroup(name)}
}

func redactAttr(groups []string, attr slog.Attr) slog.Attr {
	if isSensitiveKey(attr.Key) {
		return slog.String(attr.Key, redactedValue)
	}

	value := resolveSlogValue(attr.Value)
	switch value.Kind() {
	case slog.KindString:
		return slog.String(attr.Key, redactString(value.String()))
	case slog.KindGroup:
		children := value.Group()
		if len(children) == 0 {
			return slog.Attr{Key: attr.Key, Value: slog.GroupValue()}
		}
		redacted := make([]slog.Attr, 0, len(children))
		for _, child := range children {
			redacted = append(redacted, redactAttr(appendGroup(groups, attr.Key), child))
		}
		return slog.Attr{Key: attr.Key, Value: slog.GroupValue(redacted...)}
	case slog.KindAny:
		return slog.Any(attr.Key, redactAny(value.Any()))
	case slog.KindBool, slog.KindDuration, slog.KindFloat64, slog.KindInt64,
		slog.KindTime, slog.KindUint64, slog.KindLogValuer:
		// Primitive values require no transformation and use the common return
		// below. Keeping this case explicit satisfies exhaustive enum checking.
	}
	return slog.Attr{Key: attr.Key, Value: value}
}

func appendGroup(groups []string, group string) []string {
	if group == "" {
		return groups
	}
	result := make([]string, 0, len(groups)+1)
	result = append(result, groups...)
	return append(result, group)
}

func isSensitiveKey(key string) bool {
	normalized := normalizeKey(key)
	compact := strings.ReplaceAll(normalized, "-", "")

	switch normalized {
	case "authorization", "proxy-authorization", "cookie", "set-cookie",
		"password", "password-hash", "secret", "credential", "api-key",
		"private-key", "jwt", "token", "email", "phone", "phone-number",
		"mobile-phone", "session", "session-id", "session-cookie", "x-api-key",
		"x-csrf-token", "x-internal-signature":
		return true
	}
	if compact == "apikey" || compact == "accesskey" || compact == "refreshkey" {
		return true
	}
	for _, suffix := range []string{"-token", "-secret", "-password", "-credential", "-api-key"} {
		if strings.HasSuffix(normalized, suffix) {
			return true
		}
	}
	return strings.Contains(normalized, "authorization")
}

func normalizeKey(key string) string {
	normalized := strings.TrimSpace(key)
	// Split initialisms before ordinary camel-case boundaries: APIKey becomes
	// API-Key, while sessionID becomes session-ID in the second pass.
	normalized = initialismBoundaryPattern.ReplaceAllString(normalized, `${1}-${2}`)
	normalized = camelBoundaryPattern.ReplaceAllString(normalized, `${1}-${2}`)
	normalized = strings.Map(func(r rune) rune {
		switch r {
		case '_', '.', '/', '\\', ':':
			return '-'
		default:
			return r
		}
	}, normalized)
	normalized = strings.ToLower(normalized)
	normalized = strings.ReplaceAll(normalized, "_", "-")
	normalized = strings.Join(strings.Fields(normalized), "-")
	return normalized
}

func redactString(value string) string {
	matches := embeddedURLPattern.FindAllStringIndex(value, -1)
	if len(matches) == 0 {
		return redactPlainText(value)
	}

	var redacted strings.Builder
	redacted.Grow(len(value))
	previous := 0
	for _, match := range matches {
		redacted.WriteString(redactPlainText(value[previous:match[0]]))
		redacted.WriteString(redactURLToken(value[match[0]:match[1]]))
		previous = match[1]
	}
	redacted.WriteString(redactPlainText(value[previous:]))
	return redacted.String()
}

func redactPlainText(value string) string {
	value = emailPattern.ReplaceAllString(value, redactedEmail)
	value = phonePattern.ReplaceAllString(value, redactedPhone)
	value = bearerPattern.ReplaceAllString(value, textMask)
	return tokenPattern.ReplaceAllString(value, valueMask)
}

func redactURLToken(token string) string {
	trimmed, suffix := trimURLSuffix(token)
	parsed, err := url.Parse(trimmed)
	if err != nil || parsed.Host == "" {
		return redactPlainText(token)
	}

	if parsed.User != nil {
		_, hasPassword := parsed.User.Password()
		if hasPassword {
			parsed.User = url.UserPassword(redactedValue, redactedValue)
		} else {
			parsed.User = url.User(redactedValue)
		}
	}

	if query, queryErr := url.ParseQuery(parsed.RawQuery); queryErr == nil {
		for key, values := range query {
			if isSensitiveQueryKey(key) {
				query[key] = []string{redactedValue}
				continue
			}
			for index, value := range values {
				values[index] = redactPlainText(value)
			}
		}
		parsed.RawQuery = query.Encode()
	} else {
		parsed.RawQuery = redactRawQuery(parsed.RawQuery)
	}

	// Sanitize user-controlled path and fragment components independently.
	// Running the email scrubber over the complete serialized URL would treat
	// the `user@host` delimiter as an email and erase the host from otherwise
	// useful diagnostics.
	parsed.Path = redactPlainText(parsed.Path)
	parsed.RawPath = ""
	parsed.Fragment = redactPlainText(parsed.Fragment)
	parsed.RawFragment = ""
	return parsed.String() + suffix
}

func trimURLSuffix(value string) (string, string) {
	end := len(value)
	for end > 0 && strings.ContainsRune(".,;:!?)]}", rune(value[end-1])) {
		end--
	}
	return value[:end], value[end:]
}

func redactRawQuery(raw string) string {
	if raw == "" {
		return raw
	}
	var redacted strings.Builder
	redacted.Grow(len(raw))
	for index := 0; index < len(raw); {
		end := index
		for end < len(raw) && raw[end] != '&' && raw[end] != ';' {
			end++
		}
		part := raw[index:end]
		key, value, hasValue := strings.Cut(part, "=")
		redacted.WriteString(key)
		if hasValue {
			redacted.WriteByte('=')
			if isSensitiveQueryKey(key) {
				redacted.WriteString(redactedValue)
			} else {
				redacted.WriteString(redactPlainText(value))
			}
		}
		if end < len(raw) {
			redacted.WriteByte(raw[end])
		}
		index = end + 1
	}
	return redacted.String()
}

func isSensitiveQueryKey(key string) bool {
	if decoded, err := url.QueryUnescape(key); err == nil {
		key = decoded
	}
	if isSensitiveKey(key) {
		return true
	}
	switch normalizeKey(key) {
	case "code", "ticket", "ott", "signature", "sig", "nonce", "otp":
		return true
	default:
		return false
	}
}

func resolveSlogValue(value slog.Value) (resolved slog.Value) {
	defer func() {
		if recover() != nil {
			resolved = slog.StringValue(redactedValue)
		}
	}()
	for index := 0; index < 100; index++ {
		if value.Kind() != slog.KindLogValuer {
			return value
		}
		value = value.LogValuer().LogValue()
	}
	return slog.StringValue(redactedValue)
}

func redactAny(value any) (result any) {
	defer func() {
		if recover() != nil {
			result = redactedValue
		}
	}()
	if value == nil {
		return nil
	}
	if slogValue, ok := value.(slog.Value); ok {
		return redactAny(resolveSlogValue(slogValue).Any())
	}
	if err, ok := value.(error); ok {
		return redactString(err.Error())
	}
	if stringer, ok := value.(fmt.Stringer); ok {
		return redactString(stringer.String())
	}
	return redactReflect(reflect.ValueOf(value), 0)
}

func redactReflect(value reflect.Value, depth int) (result any) {
	defer func() {
		if recover() != nil {
			result = redactedValue
		}
	}()
	if !value.IsValid() {
		return nil
	}
	if depth > 16 {
		return redactedValue
	}
	return redactReflectValue(value, depth)
}

func redactReflectValue(value reflect.Value, depth int) any {
	switch value.Kind() {
	case reflect.Invalid:
		return nil
	case reflect.Interface:
		if value.IsNil() {
			return nil
		}
		return redactReflect(value.Elem(), depth+1)
	case reflect.String:
		return redactString(value.String())
	case reflect.Bool, reflect.Int, reflect.Int8, reflect.Int16, reflect.Int32,
		reflect.Int64, reflect.Uint, reflect.Uint8, reflect.Uint16, reflect.Uint32,
		reflect.Uint64, reflect.Uintptr, reflect.Float32, reflect.Float64,
		reflect.Complex64, reflect.Complex128:
		return redactNumeric(value)
	case reflect.Pointer:
		return redactPointer(value, depth)
	case reflect.Slice:
		return redactSlice(value, depth)
	case reflect.Array:
		return redactArray(value, depth)
	case reflect.Map:
		return redactMap(value, depth)
	case reflect.Struct:
		return redactStruct(value)
	case reflect.Chan, reflect.Func, reflect.UnsafePointer:
		// Unsupported values fail closed through the common return below.
	}
	return redactedValue
}

func redactNumeric(value reflect.Value) any {
	if value.CanInterface() {
		return value.Interface()
	}
	return redactedValue
}

func redactPointer(value reflect.Value, depth int) any {
	if value.IsNil() {
		return nil
	}
	return redactReflect(value.Elem(), depth+1)
}

func redactSlice(value reflect.Value, depth int) any {
	if value.IsNil() {
		return nil
	}
	if value.Type().Elem().Kind() == reflect.Uint8 {
		return redactString(string(value.Bytes()))
	}
	result := make([]any, value.Len())
	for index := 0; index < value.Len(); index++ {
		result[index] = redactReflect(value.Index(index), depth+1)
	}
	return result
}

func redactArray(value reflect.Value, depth int) any {
	result := make([]any, value.Len())
	for index := 0; index < value.Len(); index++ {
		result[index] = redactReflect(value.Index(index), depth+1)
	}
	return result
}

func redactMap(value reflect.Value, depth int) any {
	if value.IsNil() {
		return nil
	}
	result := make(map[string]any, value.Len())
	iter := value.MapRange()
	for iter.Next() {
		key := redactMapKey(iter.Key())
		if isSensitiveKey(key) {
			result[key] = redactedValue
			continue
		}
		// JSON object keys are still user-controlled strings. Sanitize
		// recognizable email/phone material before preserving the key so a
		// map such as {"person@example.edu": "..."} cannot bypass the
		// value-oriented redaction pass.
		result[redactString(key)] = redactReflect(iter.Value(), depth+1)
	}
	return result
}

func redactMapKey(value reflect.Value) string {
	if value.Kind() == reflect.String {
		return value.String()
	}
	if value.CanInterface() {
		return fmt.Sprint(value.Interface())
	}
	return "[REDACTED_KEY]"
}

func redactStruct(value reflect.Value) any {
	if value.CanInterface() {
		if encoded, err := json.Marshal(value.Interface()); err == nil {
			var decoded any
			if json.Unmarshal(encoded, &decoded) == nil {
				return redactAny(decoded)
			}
		}
	}
	// Never fall back to the raw value: fmt.Stringer/error values were
	// handled above, while an arbitrary String() may contain credentials.
	return redactedValue
}
