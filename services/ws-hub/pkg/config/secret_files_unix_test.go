//go:build unix

package config

import (
	"os"
	"os/exec"
	"path/filepath"
	"testing"
	"time"

	"golang.org/x/sys/unix"
)

func TestOpenSecretFileDoesNotBlockOnFIFO(t *testing.T) {
	const helperEnv = "UNIVERSITY_ECOSYSTEM_SECRET_FIFO_HELPER"
	if os.Getenv(helperEnv) == "1" {
		file, err := openSecretFile(os.Getenv("UNIVERSITY_ECOSYSTEM_SECRET_FIFO_PATH"))
		if err != nil {
			t.Fatal("nonblocking FIFO open failed")
		}
		defer func() { _ = file.Close() }()
		info, err := file.Stat()
		if err != nil {
			t.Fatal("could not inspect opened FIFO")
		}
		if info.Mode()&os.ModeNamedPipe == 0 {
			t.Fatal("opened path was not a FIFO")
		}
		return
	}

	fifoPath := filepath.Join(t.TempDir(), "secret.fifo")
	if err := unix.Mkfifo(fifoPath, 0o600); err != nil {
		t.Fatalf("create FIFO: %v", err)
	}
	command := exec.Command(os.Args[0], "-test.run=^TestOpenSecretFileDoesNotBlockOnFIFO$")
	command.Env = append(os.Environ(),
		helperEnv+"=1",
		"UNIVERSITY_ECOSYSTEM_SECRET_FIFO_PATH="+fifoPath,
	)
	done := make(chan error, 1)
	go func() { done <- command.Run() }()
	select {
	case err := <-done:
		if err != nil {
			t.Fatalf("FIFO open helper failed: %v", err)
		}
	case <-time.After(2 * time.Second):
		if command.Process != nil {
			_ = command.Process.Kill()
		}
		select {
		case <-done:
		case <-time.After(time.Second):
			t.Fatal("timed out waiting for the isolated FIFO-open test process to stop")
		}
		t.Fatal("opening a FIFO blocked instead of returning promptly")
	}

	if _, err := readSecretFile(fifoPath); err == nil {
		t.Fatal("readSecretFile accepted a FIFO as a secret file")
	}
}
