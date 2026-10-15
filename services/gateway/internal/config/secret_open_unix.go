//go:build unix

package config

import (
	"os"

	"golang.org/x/sys/unix"
)

// openSecretFile opens regular files without blocking if the path changes to a
// FIFO after readSecretFile's initial regular-file check.
func openSecretFile(path string) (*os.File, error) {
	fd, err := unix.Open(path, unix.O_RDONLY|unix.O_NONBLOCK|unix.O_CLOEXEC, 0)
	if err != nil {
		return nil, err
	}
	return os.NewFile(uintptr(fd), path), nil
}
