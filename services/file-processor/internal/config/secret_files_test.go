package config

import (
	"errors"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/spf13/viper"
)

func TestSecretFileReaderAcceptsProjectedSecretSymlinks(t *testing.T) {
	directory := t.TempDir()
	versionDirectory := filepath.Join(directory, "..2026_10_15_000000")
	if err := os.Mkdir(versionDirectory, 0o700); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(versionDirectory, "credential"), []byte("projected-value"), 0o600); err != nil {
		t.Fatal(err)
	}
	if err := os.Symlink(filepath.Base(versionDirectory), filepath.Join(directory, "..data")); err != nil {
		t.Fatalf("directory symlinks are unavailable: %v", err)
	}
	projectedPath := filepath.Join(directory, "credential")
	if err := os.Symlink(filepath.Join("..data", "credential"), projectedPath); err != nil {
		t.Fatalf("projected Secret symlinks are unavailable: %v", err)
	}

	contents, err := readSecretFile(projectedPath)
	if err != nil {
		t.Fatalf("read projected secret: %v", err)
	}
	if string(contents) != "projected-value" {
		t.Fatal("projected file contents did not match")
	}
}

func TestApplySecretFileOverridesUseFilesAndRejectInvalidInput(t *testing.T) {
	secretEnvs := []string{
		"FP_NATS_URL_FILE", "FP_MINIO_ACCESS_KEY_FILE", "FP_MINIO_SECRET_KEY_FILE",
		"FP_PROCESSING_CAPABILITY_SECRET_FILE", "FP_JWT_SECRET_FILE", "FP_REVOCATION_REDIS_URL_FILE",
	}
	for _, name := range secretEnvs {
		clearFPSecretFileEnv(t, name)
	}
	values := map[string]string{
		"FP_NATS_URL_FILE":                     " \tnats://file-nats:4222 \n",
		"FP_MINIO_ACCESS_KEY_FILE":             "access-value",
		"FP_MINIO_SECRET_KEY_FILE":             "storage-value",
		"FP_PROCESSING_CAPABILITY_SECRET_FILE": strings.Repeat("c", 40),
		"FP_JWT_SECRET_FILE":                   "jwt-value",
		"FP_REVOCATION_REDIS_URL_FILE":         "redis://file-revocation:6379/0",
	}
	for envName, value := range values {
		path := filepath.Join(t.TempDir(), strings.ToLower(envName))
		if err := os.WriteFile(path, []byte(value), 0o600); err != nil {
			t.Fatal(err)
		}
		t.Setenv(envName, path)
	}
	for envName, value := range map[string]string{
		"FP_NATS_URL":                     "nats://compose:4222",
		"FP_MINIO_ACCESS_KEY":             "compose-value",
		"FP_MINIO_SECRET_KEY":             "compose-fallback",
		"FP_PROCESSING_CAPABILITY_SECRET": "compose-test-value",
		"FP_JWT_SECRET":                   "compose-jwt-value",
		"FP_REVOCATION_REDIS_URL":         "redis://compose:6379/0",
	} {
		t.Setenv(envName, value)
	}

	configureViper()
	if err := bindConfigEnvironment(); err != nil {
		t.Fatalf("bind env: %v", err)
	}
	if err := applySecretFileOverrides(); err != nil {
		t.Fatalf("apply secret files: %v", err)
	}
	for key, expected := range map[string]string{
		"nats_url": "nats://file-nats:4222", "minio_access_key": "access-value",
		"minio_secret_key": "storage-value", "processing_capability_secret": strings.Repeat("c", 40),
		"jwt_secret": "jwt-value", "revocation_redis_url": "redis://file-revocation:6379/0",
	} {
		if actual := viper.GetString(key); actual != expected {
			t.Errorf("%s file value was not applied", key)
		}
	}

	missingPath := filepath.Join(t.TempDir(), "missing")
	t.Setenv("FP_MINIO_SECRET_KEY_FILE", missingPath)
	if err := applySecretFileOverrides(); err == nil {
		t.Fatal("configured missing file unexpectedly fell back to env")
	} else if strings.Contains(err.Error(), "compose-fallback") {
		t.Fatal("file error disclosed secret bytes")
	}
}

func TestReadSecretFileRejectsNonRegularOversizedEmptyAndInvalidText(t *testing.T) {
	directory := t.TempDir()
	directoryPath := filepath.Join(directory, "directory")
	if err := os.Mkdir(directoryPath, 0o700); err != nil {
		t.Fatal(err)
	}
	oversizedPath := filepath.Join(directory, "oversized")
	if err := os.WriteFile(oversizedPath, []byte(strings.Repeat("x", maxSecretFileSize+1)), 0o600); err != nil {
		t.Fatal(err)
	}
	emptyPath := filepath.Join(directory, "empty")
	if err := os.WriteFile(emptyPath, nil, 0o600); err != nil {
		t.Fatal(err)
	}
	invalidTextPath := filepath.Join(directory, "invalid-text")
	if err := os.WriteFile(invalidTextPath, []byte{0xff}, 0o600); err != nil {
		t.Fatal(err)
	}
	missingPath := filepath.Join(directory, "missing")
	for name, path := range map[string]string{
		"directory": directoryPath, "oversized": oversizedPath, "empty": emptyPath,
		"invalid text": invalidTextPath, "missing": missingPath,
	} {
		t.Run(name, func(t *testing.T) {
			if contents, err := readSecretFile(path); err == nil || len(contents) != 0 {
				t.Fatal("invalid secret file unexpectedly succeeded")
			}
		})
	}
}

func TestApplySecretFileOverridesRejectsMultilineAndPreservesComposeEnvironment(t *testing.T) {
	for _, name := range []string{
		"FP_NATS_URL_FILE", "FP_MINIO_ACCESS_KEY_FILE", "FP_MINIO_SECRET_KEY_FILE",
		"FP_PROCESSING_CAPABILITY_SECRET_FILE", "FP_JWT_SECRET_FILE", "FP_REVOCATION_REDIS_URL_FILE",
	} {
		clearFPSecretFileEnv(t, name)
	}
	t.Setenv("FP_NATS_URL", "  nats://compose:4222  ")
	configureViper()
	if err := bindConfigEnvironment(); err != nil {
		t.Fatalf("bind env: %v", err)
	}
	if err := applySecretFileOverrides(); err != nil {
		t.Fatalf("apply without file values: %v", err)
	}
	if actual := viper.GetString("nats_url"); actual != "  nats://compose:4222  " {
		t.Fatalf("plain Compose environment value changed: %q", actual)
	}

	path := filepath.Join(t.TempDir(), "multiline")
	if err := os.WriteFile(path, []byte("synthetic-first-line\nsynthetic-second-line"), 0o600); err != nil {
		t.Fatal(err)
	}
	t.Setenv("FP_NATS_URL_FILE", path)
	if err := applySecretFileOverrides(); err == nil {
		t.Fatal("multiline secret file unexpectedly succeeded")
	} else if strings.Contains(err.Error(), "synthetic-first-line") || strings.Contains(err.Error(), "synthetic-second-line") {
		t.Fatal("file error disclosed secret bytes")
	}
}

func clearFPSecretFileEnv(t *testing.T, name string) {
	t.Helper()
	previous, existed := os.LookupEnv(name)
	if err := os.Unsetenv(name); err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() {
		if existed {
			_ = os.Setenv(name, previous)
		} else {
			_ = os.Unsetenv(name)
		}
	})
}

func TestReadSecretFileRejectsEmptyPath(t *testing.T) {
	if contents, err := readSecretFile(""); err == nil || len(contents) != 0 {
		t.Fatal("empty configured secret path unexpectedly succeeded")
	}
}

func TestOpenSecretFileRejectsMissingPath(t *testing.T) {
	path := filepath.Join(t.TempDir(), "missing")
	if file, err := openSecretFile(path); err == nil {
		if file != nil {
			_ = file.Close()
		}
		t.Fatal("opening a missing secret file unexpectedly succeeded")
	}
}

func TestLoadReturnsConfiguredSecretFileErrorWithoutEnvironmentFallback(t *testing.T) {
	for _, name := range []string{
		"FP_NATS_URL_FILE", "FP_MINIO_ACCESS_KEY_FILE", "FP_MINIO_SECRET_KEY_FILE",
		"FP_PROCESSING_CAPABILITY_SECRET_FILE", "FP_JWT_SECRET_FILE", "FP_REVOCATION_REDIS_URL_FILE",
	} {
		clearFPSecretFileEnv(t, name)
	}
	missingPath := filepath.Join(t.TempDir(), "missing")
	t.Setenv("FP_NATS_URL", "nats://environment-fallback:4222")
	t.Setenv("FP_NATS_URL_FILE", missingPath)

	cfg, err := Load()

	if cfg != nil || err == nil {
		t.Fatal("configured missing secret file unexpectedly fell back to the environment")
	}
	if !strings.Contains(err.Error(), "FP_NATS_URL_FILE") {
		t.Fatal("secret-file load error did not identify the configured input")
	}
	if strings.Contains(err.Error(), missingPath) || strings.Contains(err.Error(), "environment-fallback") {
		t.Fatal("secret-file load error disclosed a path or secret-like value")
	}
}
func TestReadSecretFileRejectsIOFailuresAndClosesOpenedFile(t *testing.T) {
	path := filepath.Join(t.TempDir(), "credential")
	if err := os.WriteFile(path, []byte("synthetic-content"), 0o600); err != nil {
		t.Fatal(err)
	}
	directory := t.TempDir()

	tests := []struct {
		name         string
		configure    func(*secretFileOperations)
		wantClose    bool
		wantNoDetail string
	}{
		{
			name: "open failure after initial stat",
			configure: func(ops *secretFileOperations) {
				ops.open = func(string) (*os.File, error) { return nil, errors.New("synthetic open failure") }
			},
			wantNoDetail: "synthetic open failure",
		},
		{
			name: "opened stat failure",
			configure: func(ops *secretFileOperations) {
				ops.statFile = func(*os.File) (os.FileInfo, error) { return nil, errors.New("synthetic stat failure") }
			},
			wantClose:    true,
			wantNoDetail: "synthetic stat failure",
		},
		{
			name: "opened path changed to nonregular",
			configure: func(ops *secretFileOperations) {
				ops.statFile = func(*os.File) (os.FileInfo, error) { return os.Stat(directory) }
			},
			wantClose: true,
		},
		{
			name: "read failure",
			configure: func(ops *secretFileOperations) {
				ops.read = func(*os.File, int64) ([]byte, error) { return nil, errors.New("synthetic read failure") }
			},
			wantClose:    true,
			wantNoDetail: "synthetic read failure",
		},
		{
			name: "bounded read detects growth after stat",
			configure: func(ops *secretFileOperations) {
				ops.read = func(*os.File, int64) ([]byte, error) { return make([]byte, maxSecretFileSize+1), nil }
			},
			wantClose: true,
		},
	}

	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			closed := false
			setSecretFileOperations(t, func(ops *secretFileOperations) {
				ops.close = func(file *os.File) error {
					closed = true
					return file.Close()
				}
				test.configure(ops)
			})

			contents, err := readSecretFile(path)
			if err == nil || len(contents) != 0 {
				t.Fatal("configured I/O failure unexpectedly succeeded")
			}
			if test.wantNoDetail != "" && strings.Contains(err.Error(), test.wantNoDetail) {
				t.Fatal("I/O error disclosed an underlying detail")
			}
			if closed != test.wantClose {
				t.Fatalf("opened descriptor close state = %t, want %t", closed, test.wantClose)
			}
		})
	}
}

func setSecretFileOperations(t *testing.T, update func(*secretFileOperations)) {
	t.Helper()
	previous := secretFileIO
	update(&secretFileIO)
	t.Cleanup(func() { secretFileIO = previous })
}

func TestReadSecretFileClosesOpenedFileAfterSuccess(t *testing.T) {
	path := filepath.Join(t.TempDir(), "credential")
	if err := os.WriteFile(path, []byte("synthetic-content"), 0o600); err != nil {
		t.Fatal(err)
	}
	closed := false
	setSecretFileOperations(t, func(ops *secretFileOperations) {
		ops.close = func(file *os.File) error {
			closed = true
			return file.Close()
		}
	})

	contents, err := readSecretFile(path)
	if err != nil || string(contents) != "synthetic-content" {
		t.Fatal("regular secret file read failed")
	}
	if !closed {
		t.Fatal("opened file descriptor was not closed after a successful read")
	}
}

func TestReadSecretFileFailsClosedWhenCloseReportsError(t *testing.T) {
	path := filepath.Join(t.TempDir(), "credential")
	if err := os.WriteFile(path, []byte("synthetic-content"), 0o600); err != nil {
		t.Fatal(err)
	}
	closeCalls := 0
	descriptorClosed := false
	setSecretFileOperations(t, func(ops *secretFileOperations) {
		ops.close = func(file *os.File) error {
			closeCalls++
			if err := file.Close(); err != nil {
				return err
			}
			descriptorClosed = true
			return errors.New("synthetic close failure")
		}
	})

	contents, err := readSecretFile(path)
	if err == nil || len(contents) != 0 {
		t.Fatal("secret contents were returned after close reported an error")
	}
	if err.Error() != "cannot close configured secret file" {
		t.Fatal("close error was not sanitized")
	}
	if strings.Contains(err.Error(), "synthetic close failure") {
		t.Fatal("close error disclosed its underlying detail")
	}
	if closeCalls != 1 || !descriptorClosed {
		t.Fatalf("close state = %d calls, descriptor closed %t; want one successful descriptor close", closeCalls, descriptorClosed)
	}
}

func TestReadSecretFileRetainsReadErrorWhenCloseAlsoReportsError(t *testing.T) {
	path := filepath.Join(t.TempDir(), "credential")
	if err := os.WriteFile(path, []byte("synthetic-content"), 0o600); err != nil {
		t.Fatal(err)
	}
	closeCalls := 0
	descriptorClosed := false
	setSecretFileOperations(t, func(ops *secretFileOperations) {
		ops.read = func(*os.File, int64) ([]byte, error) {
			return nil, errors.New("synthetic read failure")
		}
		ops.close = func(file *os.File) error {
			closeCalls++
			if err := file.Close(); err != nil {
				return err
			}
			descriptorClosed = true
			return errors.New("synthetic close failure")
		}
	})

	contents, err := readSecretFile(path)
	if err == nil || len(contents) != 0 {
		t.Fatal("read failure unexpectedly returned contents")
	}
	if err.Error() != "cannot read configured secret file" {
		t.Fatal("close error replaced the sanitized read error")
	}
	if strings.Contains(err.Error(), "synthetic read failure") || strings.Contains(err.Error(), "synthetic close failure") {
		t.Fatal("I/O error disclosed an underlying detail")
	}
	if closeCalls != 1 || !descriptorClosed {
		t.Fatalf("close state = %d calls, descriptor closed %t; want one successful descriptor close", closeCalls, descriptorClosed)
	}
}
