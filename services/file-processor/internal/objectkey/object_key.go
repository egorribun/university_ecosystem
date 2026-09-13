// Package objectkey provides host-independent validation for storage object keys.
package objectkey

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
