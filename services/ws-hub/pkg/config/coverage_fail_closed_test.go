package config

import (
	"errors"
	"io"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestLoadConfigFailsClosedAtEachConfiguredSecretFile(t *testing.T) {
	testCases := []struct {
		name         string
		target       string
		unsetJWTList bool
	}{
		{name: "NATS URL", target: "NATS_URL_FILE"},
		{name: "NATS user", target: "NATS_USER_FILE"},
		{name: "NATS password", target: "NATS_PASSWORD_FILE"},
		{name: "NATS token", target: "NATS_AUTH_TOKEN_FILE"},
		{name: "JWT rotation list", target: "JWT_SECRETS_FILE"},
		{name: "legacy JWT", target: "JWT_SECRET_FILE", unsetJWTList: true},
		{name: "internal shared secret", target: "WS_HUB_INTERNAL_SECRET_FILE"},
		{name: "internal callback token", target: "INTERNAL_AUTH_TOKEN_FILE"},
		{name: "cache Redis URL", target: "REDIS_URL_FILE"},
		{name: "cache Redis password", target: "REDIS_PASSWORD_FILE"},
		{name: "revocation Redis URL", target: "REVOCATION_REDIS_URL_FILE"},
	}

	for _, testCase := range testCases {
		t.Run(testCase.name, func(t *testing.T) {
			fileValues := map[string]string{
				"NATS_URL_FILE":               "nats://synthetic.invalid:4222",
				"NATS_USER_FILE":              "sample-user",
				"NATS_PASSWORD_FILE":          "sample-password",
				"NATS_AUTH_TOKEN_FILE":        "sample-token",
				"JWT_SECRETS_FILE":            "sample-one,sample-two",
				"JWT_SECRET_FILE":             "sample-legacy",
				"WS_HUB_INTERNAL_SECRET_FILE": "sample-internal",
				"INTERNAL_AUTH_TOKEN_FILE":    "sample-callback",
				"REDIS_URL_FILE":              "redis://synthetic.invalid:6379/0",
				"REDIS_PASSWORD_FILE":         "sample-redis-password",
				"REVOCATION_REDIS_URL_FILE":   "redis://synthetic-revocation.invalid:6379/0",
			}
			for name := range fileValues {
				clearEnvForSecretFileTest(t, name)
				clearEnvForSecretFileTest(t, strings.TrimSuffix(name, "_FILE"))
			}

			validDirectory := t.TempDir()
			validFilePaths := make(map[string]string, len(fileValues))
			for name, contents := range fileValues {
				path := filepath.Join(validDirectory, strings.ToLower(name))
				if err := os.WriteFile(path, []byte(contents), 0o600); err != nil {
					t.Fatal(err)
				}
				validFilePaths[name] = path
			}
			for name := range fileValues {
				if name == testCase.target || testCase.unsetJWTList && name == "JWT_SECRETS_FILE" {
					continue
				}
				t.Setenv(name, validFilePaths[name])
			}
			if testCase.unsetJWTList {
				t.Setenv("JWT_SECRETS", "")
			}

			missingPath := filepath.Join(t.TempDir(), "missing-secret")
			t.Setenv(testCase.target, missingPath)

			cfg, err := LoadConfig()
			if err == nil {
				t.Fatal("configured secret file failure unexpectedly loaded config")
			}
			if cfg != nil {
				t.Fatal("failed configuration returned a partial config")
			}
			if !strings.Contains(err.Error(), strings.TrimSuffix(testCase.target, "_FILE")) {
				t.Fatalf("error did not identify the configured key: %v", err)
			}
			if strings.Contains(err.Error(), "sample-config-value") || strings.Contains(err.Error(), missingPath) {
				t.Fatalf("error disclosed file contents or path: %v", err)
			}
		})
	}
}

func TestGetEnvSliceUsesDefaultWhenConfiguredValueHasNoEntries(t *testing.T) {
	t.Setenv("TEST_EMPTY_ENV_SLICE", ", 	, ,")
	defaultValue := []string{"first-default", "second-default"}

	got := getEnvSlice("TEST_EMPTY_ENV_SLICE", defaultValue)

	if len(got) != len(defaultValue) || got[0] != "first-default" || got[1] != "second-default" {
		t.Fatalf("getEnvSlice() = %#v, want %#v", got, defaultValue)
	}
}

func TestReadSecretEnvRejectsEmptyConfiguredFilePathWithoutFallback(t *testing.T) {
	t.Setenv("TEST_SECRET_VALUE", "sample-compose-value")
	t.Setenv("TEST_SECRET_VALUE_FILE", "")

	value, configured, err := readSecretEnv("TEST_SECRET_VALUE")

	if err == nil || !configured || value != "" {
		t.Fatalf("empty file path did not fail closed: configured=%v value=%q err=%v", configured, value, err)
	}
	if !strings.Contains(err.Error(), "TEST_SECRET_VALUE_FILE must not be empty") {
		t.Fatalf("unexpected empty-path error: %v", err)
	}
	if strings.Contains(err.Error(), "sample-compose-value") {
		t.Fatal("empty-path error disclosed fallback environment contents")
	}
}

func TestSecretEnvOrDefaultUsesDefaultForConfiguredEmptyEnvironmentValue(t *testing.T) {
	t.Setenv("TEST_OPTIONAL_URL", "")

	got, err := secretEnvOrDefault("TEST_OPTIONAL_URL", "protocol://default.invalid")

	if err != nil || got != "protocol://default.invalid" {
		t.Fatalf("secretEnvOrDefault() = %q, %v; want default, nil", got, err)
	}
}

func TestReadSecretFileFailsClosedAndClosesOpenedFile(t *testing.T) {
	directory := t.TempDir()
	smallPath := filepath.Join(directory, "small")
	if err := os.WriteFile(smallPath, []byte("small"), 0o600); err != nil {
		t.Fatal(err)
	}
	emptyPath := filepath.Join(directory, "empty")
	if err := os.WriteFile(emptyPath, nil, 0o600); err != nil {
		t.Fatal(err)
	}
	oversizedPath := filepath.Join(directory, "oversized")
	if err := os.WriteFile(oversizedPath, []byte(strings.Repeat("x", maxSecretFileSize+1)), 0o600); err != nil {
		t.Fatal(err)
	}
	directoryPath := filepath.Join(directory, "nested")
	if err := os.Mkdir(directoryPath, 0o700); err != nil {
		t.Fatal(err)
	}

	testCases := []struct {
		name      string
		path      string
		openErr   bool
		statErr   error
		statPath  string
		readErr   error
		readData  string
		wantError string
		wantRead  bool
	}{
		{name: "open error", path: smallPath, openErr: true, wantError: "cannot open configured secret file"},
		{name: "opened-file stat error", path: smallPath, statErr: errors.New("sample underlying stat error"), wantError: "cannot inspect configured secret file"},
		{name: "opened path no longer regular", path: smallPath, statPath: directoryPath, wantError: "configured secret path must resolve to a regular file"},
		{name: "opened file exceeds limit", path: oversizedPath, wantError: "configured secret file exceeds the size limit"},
		{name: "read error", path: smallPath, readErr: errors.New("sample underlying read error"), wantError: "cannot read configured secret file", wantRead: true},
		{name: "file grew while reading", path: smallPath, readData: strings.Repeat("x", maxSecretFileSize+1), wantError: "configured secret file exceeds the size limit", wantRead: true},
		{name: "empty file", path: emptyPath, readData: "", wantError: "configured secret file must not be empty", wantRead: true},
	}

	for _, testCase := range testCases {
		t.Run(testCase.name, func(t *testing.T) {
			var opened *trackedSecretFile
			oldOpen := openSecretFileForRead
			t.Cleanup(func() { openSecretFileForRead = oldOpen })
			openSecretFileForRead = func(string) (secretFile, error) {
				if testCase.openErr {
					return nil, errors.New("sample underlying open error")
				}
				realFile, err := openSecretFile(testCase.path)
				if err != nil {
					return nil, err
				}
				var info os.FileInfo
				if testCase.statPath != "" {
					info, err = os.Stat(testCase.statPath)
				} else if testCase.statErr == nil {
					info, err = realFile.Stat()
				}
				opened = &trackedSecretFile{
					file:     realFile,
					info:     info,
					statErr:  testCase.statErr,
					readErr:  testCase.readErr,
					readData: testCase.readData,
				}
				return opened, err
			}

			_, err := readSecretFile(testCase.path)

			if err == nil || !strings.Contains(err.Error(), testCase.wantError) {
				t.Fatalf("readSecretFile() error = %v, want containing %q", err, testCase.wantError)
			}
			if strings.Contains(err.Error(), "sample underlying") || strings.Contains(err.Error(), "small") {
				t.Fatalf("error disclosed lower-level details: %v", err)
			}
			if opened != nil {
				if opened.closeCalls != 1 {
					t.Fatalf("opened secret file close calls = %d, want 1", opened.closeCalls)
				}
				if opened.file != nil {
					if _, statErr := opened.file.Stat(); statErr == nil {
						t.Fatal("opened file descriptor remained usable after return")
					}
				}
				if opened.readCalls == 0 && testCase.wantRead {
					t.Fatal("expected the reader to be exercised")
				}
				if opened.readCalls != 0 && !testCase.wantRead {
					t.Fatal("read was attempted before the opened-file validation failed")
				}
			} else if testCase.name != "open error" {
				t.Fatal("file was not opened for a post-open failure case")
			}
		})
	}
}

type trackedSecretFile struct {
	file       *os.File
	info       os.FileInfo
	statErr    error
	readErr    error
	closeErr   error
	readData   string
	readCalls  int
	closeCalls int
	reader     io.Reader
}

func (f *trackedSecretFile) Stat() (os.FileInfo, error) {
	if f.statErr != nil {
		return nil, f.statErr
	}
	if f.info != nil {
		return f.info, nil
	}
	return f.file.Stat()
}

func (f *trackedSecretFile) Read(buffer []byte) (int, error) {
	f.readCalls++
	if f.readErr != nil {
		return 0, f.readErr
	}
	if f.reader == nil {
		f.reader = strings.NewReader(f.readData)
	}
	return f.reader.Read(buffer)
}

func (f *trackedSecretFile) Close() error {
	f.closeCalls++
	if err := f.file.Close(); err != nil {
		return err
	}
	return f.closeErr
}

func TestOpenSecretFileRejectsMissingPath(t *testing.T) {
	path := filepath.Join(t.TempDir(), "missing-secret")
	file, err := openSecretFile(path)
	if err == nil || file != nil {
		t.Fatalf("openSecretFile() = (%v, %v), want (nil, error)", file, err)
	}
}
