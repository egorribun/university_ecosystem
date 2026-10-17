package config

import (
	"bytes"
	"errors"
	"io"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestReadSecretFileWithIOFailsClosedAndClosesOpenedFiles(t *testing.T) {
	path := filepath.Join(t.TempDir(), "credential")
	if err := os.WriteFile(path, []byte("safe-value"), 0o600); err != nil {
		t.Fatalf("write source file: %v", err)
	}
	directory := t.TempDir()

	tests := []struct {
		name      string
		open      func() (*os.File, error)
		read      secretFileReadFunc
		wantError string
	}{
		{
			name:      "open failure",
			open:      func() (*os.File, error) { return nil, errors.New("private open detail") },
			read:      readBoundedSecretFile,
			wantError: "cannot open configured secret file",
		},
		{
			name: "stat failure after open",
			open: func() (*os.File, error) {
				file, err := os.Open(path)
				if err != nil {
					return nil, err
				}
				if err := file.Close(); err != nil {
					return nil, err
				}
				return file, nil
			},
			read:      readBoundedSecretFile,
			wantError: "cannot inspect configured secret file",
		},
		{
			name:      "opened path becomes nonregular",
			open:      func() (*os.File, error) { return os.Open(directory) },
			read:      readBoundedSecretFile,
			wantError: "configured secret path must resolve to a regular file",
		},
		{
			name:      "read failure",
			open:      func() (*os.File, error) { return os.OpenFile(path, os.O_WRONLY, 0) },
			read:      readBoundedSecretFile,
			wantError: "cannot read configured secret file",
		},
		{
			name: "file grows after stat",
			open: func() (*os.File, error) { return os.OpenFile(path, os.O_RDWR, 0) },
			read: func(file *os.File) ([]byte, error) {
				if err := file.Truncate(0); err != nil {
					return nil, err
				}
				if _, err := file.Seek(0, io.SeekStart); err != nil {
					return nil, err
				}
				if _, err := file.Write(bytes.Repeat([]byte("x"), maxSecretFileSize+1)); err != nil {
					return nil, err
				}
				if _, err := file.Seek(0, io.SeekStart); err != nil {
					return nil, err
				}
				return readBoundedSecretFile(file)
			},
			wantError: "configured secret file exceeds the size limit",
		},
	}

	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			var opened *os.File
			contents, err := readSecretFileWithIO(
				path,
				func(string) (*os.File, error) {
					file, openErr := test.open()
					opened = file
					return file, openErr
				},
				test.read,
			)
			if err == nil || !strings.Contains(err.Error(), test.wantError) {
				t.Fatalf("unexpected read result: contents=%q err=%v", contents, err)
			}
			if len(contents) != 0 {
				t.Fatalf("failed read returned secret bytes: %q", contents)
			}
			if strings.Contains(err.Error(), "private open detail") || strings.Contains(err.Error(), "safe-value") {
				t.Fatal("secret-file error disclosed file or OS detail")
			}
			if opened != nil {
				if _, statErr := opened.Stat(); statErr == nil {
					t.Fatal("opened secret descriptor was not closed on error")
				}
			}
		})
	}
}

func TestReadSecretFileWithIOReportsCloseFailureAndPreservesReadFailure(t *testing.T) {
	path := filepath.Join(t.TempDir(), "credential")
	if err := os.WriteFile(path, []byte("secret-value"), 0o600); err != nil {
		t.Fatalf("write source file: %v", err)
	}

	t.Run("successful read with close failure clears contents", func(t *testing.T) {
		var opened *os.File
		contents, err := readSecretFileWithIO(
			path,
			func(name string) (*os.File, error) {
				file, openErr := os.Open(name)
				opened = file
				return file, openErr
			},
			func(file *os.File) ([]byte, error) {
				value, readErr := readBoundedSecretFile(file)
				if readErr != nil {
					return nil, readErr
				}
				if closeErr := file.Close(); closeErr != nil {
					return nil, closeErr
				}
				return value, nil
			},
		)
		if err == nil || err.Error() != "cannot close configured secret file" {
			t.Fatalf("close failure was not reported safely: contents=%q err=%v", contents, err)
		}
		if len(contents) != 0 || strings.Contains(err.Error(), "secret-value") {
			t.Fatalf("close failure retained secret data: contents=%q err=%v", contents, err)
		}
		if opened == nil {
			t.Fatal("open callback did not return a file")
		}
		if _, statErr := opened.Stat(); statErr == nil {
			t.Fatal("descriptor remained open after close failure")
		}
	})

	t.Run("read failure remains primary when deferred close fails", func(t *testing.T) {
		contents, err := readSecretFileWithIO(
			path,
			os.Open,
			func(file *os.File) ([]byte, error) {
				if _, readErr := readBoundedSecretFile(file); readErr != nil {
					return nil, readErr
				}
				if closeErr := file.Close(); closeErr != nil {
					return nil, closeErr
				}
				return []byte("must-not-return"), errors.New("private read detail")
			},
		)
		if err == nil || err.Error() != "cannot read configured secret file" {
			t.Fatalf("read error was not preserved and sanitized: contents=%q err=%v", contents, err)
		}
		if len(contents) != 0 || strings.Contains(err.Error(), "private read detail") || strings.Contains(err.Error(), "must-not-return") {
			t.Fatalf("read failure leaked data or detail: contents=%q err=%v", contents, err)
		}
	})
}
func TestReadBoundedSecretFileStopsAtMaximumPlusOne(t *testing.T) {
	path := filepath.Join(t.TempDir(), "oversized")
	if err := os.WriteFile(path, bytes.Repeat([]byte("x"), maxSecretFileSize+100), 0o600); err != nil {
		t.Fatalf("write oversized fixture: %v", err)
	}
	file, err := os.Open(path)
	if err != nil {
		t.Fatalf("open oversized fixture: %v", err)
	}
	contents, readErr := readBoundedSecretFile(file)
	closeErr := file.Close()
	if readErr != nil {
		t.Fatalf("bounded read: %v", readErr)
	}
	if closeErr != nil {
		t.Fatalf("close oversized fixture: %v", closeErr)
	}
	if len(contents) != maxSecretFileSize+1 {
		t.Fatalf("bounded read returned %d bytes, want %d", len(contents), maxSecretFileSize+1)
	}
}

func TestReadSecretEnvRejectsBlankFilePathWithoutFallback(t *testing.T) {
	t.Setenv("TEST_SECRET_SOURCE", "environment-fallback-marker")
	t.Setenv("TEST_SECRET_SOURCE_FILE", " \t")

	value, configured, err := readSecretEnv("TEST_SECRET_SOURCE")
	if err == nil || !configured || value != "" {
		t.Fatalf("blank configured file path did not fail closed: value=%q configured=%v err=%v", value, configured, err)
	}
	if !strings.Contains(err.Error(), "TEST_SECRET_SOURCE_FILE") || strings.Contains(err.Error(), "environment-fallback-marker") {
		t.Fatalf("blank path error is inaccurate or discloses fallback: %v", err)
	}
}
