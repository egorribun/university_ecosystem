//go:build !unix

package config

import "os"

// openSecretFile is the portable fallback. readSecretFile performs regular-file
// checks both before and after opening this path.
func openSecretFile(path string) (*os.File, error) {
	return os.Open(path)
}
