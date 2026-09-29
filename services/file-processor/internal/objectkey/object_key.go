// Package objectkey provides host-independent validation for storage object keys.
package objectkey

import (
	"errors"
	"path"
	"strings"
)

// MaxLength is the object-key boundary shared by every file-processor
// transport. Keeping the limit here prevents one ingress from accepting a key
// that is rejected only after it has already entered a workflow.
const MaxLength = 1024

var (
	// ErrEmpty reports an empty object key.
	ErrEmpty = errors.New("object key must not be empty")
	// ErrTooLong reports an object key exceeding MaxLength bytes.
	ErrTooLong = errors.New("object key exceeds maximum length")
	// ErrNUL reports an object key containing a NUL byte.
	ErrNUL = errors.New("object key contains NUL")
	// ErrAbsolute reports an absolute or rooted object key.
	ErrAbsolute = errors.New("absolute path is not allowed in object key")
	// ErrTraversal reports an object key containing a parent traversal segment.
	ErrTraversal = errors.New("path traversal detected in object key")
)

// IsAbsolute reports whether key starts with a Unix root, a Windows root, or a
// Windows drive designator. Drive-relative forms such as C:tenant/object are
// rejected because they can become absolute when interpreted on Windows.
func IsAbsolute(key string) bool {
	if key == "" {
		return false
	}
	if key[0] == '/' || key[0] == '\\' {
		return true
	}
	return len(key) >= 2 && isASCIILetter(key[0]) && key[1] == ':'
}

func isASCIILetter(value byte) bool {
	return value >= 'A' && value <= 'Z' || value >= 'a' && value <= 'z'
}

// Normalize validates and canonicalises a storage object key for use by all
// file-processor boundaries. Object names are platform-neutral: both slash
// styles are treated as separators before path cleaning, so a Windows-style
// traversal cannot pass through a POSIX path.Clean call on Linux. Absolute
// paths, parent segments, NUL bytes, and oversized keys are rejected.
//
// The returned key always uses forward slashes and has dot segments cleaned.
// Callers must use the returned value rather than the raw input when handing a
// key to a storage client or workflow.
func Normalize(key string) (string, error) {
	if key == "" {
		return "", ErrEmpty
	}
	if len(key) > MaxLength {
		return "", ErrTooLong
	}
	if strings.IndexByte(key, 0) >= 0 {
		return "", ErrNUL
	}
	if IsAbsolute(key) {
		return "", ErrAbsolute
	}

	normalized := strings.ReplaceAll(key, "\\", "/")
	// A rooted component can be hidden behind a leading dot segment when the
	// input mixes slash styles (for example, ./\\server\\share). Treat that
	// form as absolute before path.Clean discards the dot segment.
	if strings.HasPrefix(normalized, "./") && IsAbsolute(strings.TrimPrefix(normalized, "./")) {
		return "", ErrAbsolute
	}
	hasParentSegment := false
	for _, segment := range strings.Split(normalized, "/") {
		if segment == ".." {
			hasParentSegment = true
		}
	}

	cleaned := path.Clean(normalized)
	if IsAbsolute(cleaned) {
		return "", ErrAbsolute
	}
	// Retain the conservative guard used by the existing transports: names
	// beginning with two dots are rejected even when they are not a literal
	// parent segment, because downstream adapters may interpret them as one.
	if hasParentSegment || strings.HasPrefix(cleaned, "..") || strings.Contains(cleaned, "/../") {
		return "", ErrTraversal
	}
	return cleaned, nil
}
