package config

import (
	"errors"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestReadSecretFileFailsClosedOnCloseError(t *testing.T) {
	secretPath := filepath.Join(t.TempDir(), "credential")
	if err := os.WriteFile(secretPath, []byte("synthetic credential bytes"), 0o600); err != nil {
		t.Fatal(err)
	}

	testCases := []struct {
		name      string
		readErr   error
		wantError string
	}{
		{
			name:      "successful read then close failure",
			wantError: "cannot close configured secret file",
		},
		{
			name:      "read failure remains primary when close also fails",
			readErr:   errors.New("synthetic reader detail"),
			wantError: "cannot read configured secret file",
		},
	}

	for _, testCase := range testCases {
		t.Run(testCase.name, func(t *testing.T) {
			var opened *trackedSecretFile
			oldOpen := openSecretFileForRead
			t.Cleanup(func() { openSecretFileForRead = oldOpen })
			openSecretFileForRead = func(string) (secretFile, error) {
				file, err := openSecretFile(secretPath)
				if err != nil {
					return nil, err
				}
				opened = &trackedSecretFile{
					file:     file,
					readErr:  testCase.readErr,
					closeErr: errors.New("synthetic close diagnostic"),
					readData: "synthetic credential bytes",
				}
				return opened, nil
			}

			contents, err := readSecretFile(secretPath)
			if err == nil || err.Error() != testCase.wantError {
				t.Fatalf("readSecretFile() error = %v, want %q", err, testCase.wantError)
			}
			if contents != nil {
				t.Fatal("failed secret read returned data")
			}
			if strings.Contains(err.Error(), "synthetic") {
				t.Fatalf("error disclosed a lower-level detail: %v", err)
			}
			if opened == nil {
				t.Fatal("secret file was not opened")
			}
			if opened.closeCalls != 1 {
				t.Fatalf("close calls = %d, want 1", opened.closeCalls)
			}
			if opened.readCalls == 0 {
				t.Fatal("reader was not exercised before close")
			}
			if _, statErr := opened.file.Stat(); statErr == nil {
				t.Fatal("secret file descriptor remained open after return")
			}
		})
	}
}
