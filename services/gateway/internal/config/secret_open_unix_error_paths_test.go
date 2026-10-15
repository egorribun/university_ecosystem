//go:build unix

package config

import (
	"path/filepath"
	"testing"
)

func TestOpenSecretFileReturnsErrorWhenPathCannotBeOpened(t *testing.T) {
	file, err := openSecretFile(filepath.Join(t.TempDir(), "missing-secret"))
	if err == nil || file != nil {
		t.Fatalf("missing path unexpectedly opened: file=%v err=%v", file, err)
	}
}
