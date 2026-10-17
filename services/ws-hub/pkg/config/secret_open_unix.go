//go:build unix

package config

import (
	"os"

	"golang.org/x/sys/unix"
)

// init selects the strict Unix opener while keeping openSecretFile itself a
// stable wrapper for callbacks captured during package variable initialization.
func init() {
	openSecretFilePlatform = openSecretFileUnix
}

// openSecretFileUnix opens regular files without blocking if the path changes to a
// FIFO after readSecretFile's initial regular-file check.
func openSecretFileUnix(path string) (*os.File, error) {
	fd, err := unix.Open(path, unix.O_RDONLY|unix.O_NONBLOCK|unix.O_CLOEXEC, 0)
	if err != nil {
		return nil, err
	}
	// A successful unix.Open returns a valid descriptor; os.NewFile returns nil
	// only when the descriptor is invalid, so this conversion cannot fail here.
	return os.NewFile(uintptr(fd), path), nil
}
