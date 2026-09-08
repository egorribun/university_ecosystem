// Package jobcontract contains transport-neutral validation for file-processing
// jobs.  Both gRPC and asynchronous consumers can use the same boundary before
// handing a job to Temporal.
package jobcontract

import (
	"encoding/json"
	"errors"
	"path"
	"strings"

	"github.com/university-ecosystem/file-processor/internal/objectkey"
)

// MaxIDLen is the maximum length accepted for a process-job identifier.  The
// remaining constants in this block define the corresponding validation
// limits for keys, options, and option values.
const (
	MaxIDLen          = 256
	MaxKeyLen         = 1024
	MaxOptions        = 10
	MaxOptionKeyLen   = 64
	MaxOptionValueLen = 1024
)

// AllowedTypes is the versioned file-processing type allow-list.  Keep this
// list in the transport-neutral package so every ingress path accepts the same
// contract.
var AllowedTypes = map[string]struct{}{
	"image_resize":    {},
	"image_compress":  {},
	"pdf_preview":     {},
	"video_transcode": {},
}

// ValidationError is safe to include in structured logs: it contains a stable
// reason code and never embeds user-controlled identifiers, keys, or payloads.
type ValidationError struct{ Code string }

func (e *ValidationError) Error() string { return "invalid process job: " + e.Code }

// Validate validates a decoded job before any Temporal side effect.  Options
// are intentionally limited to JSON scalar values; accepting arbitrary nested
// objects or arrays would allow unbounded workflow history growth.
func Validate(id, typ, sourceKey, destKey string, options map[string]interface{}) error {
	if id == "" {
		return &ValidationError{Code: "missing_id"}
	}
	if len(id) > MaxIDLen {
		return &ValidationError{Code: "id_too_long"}
	}
	if _, ok := AllowedTypes[typ]; !ok {
		return &ValidationError{Code: "unsupported_type"}
	}
	if sourceKey == "" || destKey == "" {
		return &ValidationError{Code: "missing_object_key"}
	}
	if err := validateKey(sourceKey); err != nil {
		return &ValidationError{Code: err.Error()}
	}
	if err := validateKey(destKey); err != nil {
		return &ValidationError{Code: err.Error()}
	}
	if len(options) > MaxOptions {
		return &ValidationError{Code: "options_too_many"}
	}
	for key, value := range options {
		if key == "" {
			return &ValidationError{Code: "empty_option_key"}
		}
		if len(key) > MaxOptionKeyLen {
			return &ValidationError{Code: "option_key_too_long"}
		}
		if err := validateOptionValue(value); err != nil {
			return &ValidationError{Code: "invalid_option_value"}
		}
	}
	return nil
}

func validateKey(key string) error {
	if len(key) > MaxKeyLen {
		return errors.New("object_key_too_long")
	}
	if strings.IndexByte(key, 0) >= 0 {
		return errors.New("object_key_nul")
	}
	if objectkey.IsAbsolute(key) {
		return errors.New("object_key_absolute")
	}
	// Object keys are platform-neutral.  Treat backslashes as separators before
	// cleaning so Windows-style traversal cannot bypass the POSIX path check.
	normalized := strings.ReplaceAll(key, "\\", "/")
	for _, segment := range strings.Split(normalized, "/") {
		if segment == ".." {
			return errors.New("object_key_traversal")
		}
	}
	cleaned := path.Clean(normalized)
	if strings.HasPrefix(cleaned, "..") || strings.Contains(cleaned, "/../") {
		return errors.New("object_key_traversal")
	}
	return nil
}

func validateOptionValue(value interface{}) error {
	switch v := value.(type) {
	case nil:
		return errors.New("null_option_value")
	case string:
		if len(v) > MaxOptionValueLen {
			return errors.New("option_value_too_long")
		}
	case bool, float64:
		return nil
	case json.Number:
		// json.Decoder may produce json.Number when UseNumber is enabled.  It is
		// still a scalar and its bounded textual form is safe to persist.
		if len(v) <= MaxOptionValueLen {
			return nil
		}
		return errors.New("option_value_too_long")
	default:
		return errors.New("nested_option_value")
	}
	return nil
}
