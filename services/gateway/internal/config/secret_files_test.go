package config

import (
	"io"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestReadSecretEnvPrefersProjectedSecretFile(t *testing.T) {
	directory := t.TempDir()
	versionDirectory := filepath.Join(directory, "..2026_10_15_000000")
	if err := os.Mkdir(versionDirectory, 0o700); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(versionDirectory, "jwt-secret"), []byte("file-value"), 0o600); err != nil {
		t.Fatal(err)
	}
	if err := os.Symlink(filepath.Base(versionDirectory), filepath.Join(directory, "..data")); err != nil {
		t.Fatalf("directory symlinks are unavailable: %v", err)
	}
	projectedPath := filepath.Join(directory, "jwt-secret")
	if err := os.Symlink(filepath.Join("..data", "jwt-secret"), projectedPath); err != nil {
		t.Fatalf("projected Secret symlinks are unavailable: %v", err)
	}

	t.Setenv("TEST_SECRET_SOURCE", "compose-value")
	t.Setenv("TEST_SECRET_SOURCE_FILE", projectedPath)
	value, configured, err := readSecretEnv("TEST_SECRET_SOURCE")
	if err != nil {
		t.Fatalf("read projected secret: %v", err)
	}
	if !configured || value != "file-value" {
		t.Fatalf("file did not take precedence: configured=%v value=%q", configured, value)
	}
}

func TestReadSecretEnvNormalizesFileLineAndPreservesPlainEnvironmentBytes(t *testing.T) {
	path := filepath.Join(t.TempDir(), "credential")
	if err := os.WriteFile(path, []byte(" \tfile-value \n"), 0o600); err != nil {
		t.Fatal(err)
	}
	t.Setenv("TEST_SECRET_SOURCE", "  compose-value  ")
	t.Setenv("TEST_SECRET_SOURCE_FILE", path)
	value, configured, err := readSecretEnv("TEST_SECRET_SOURCE")
	if err != nil || !configured || value != "file-value" {
		t.Fatalf("file value normalization failed: configured=%v value=%q err=%v", configured, value, err)
	}
	if err := os.Unsetenv("TEST_SECRET_SOURCE_FILE"); err != nil {
		t.Fatal(err)
	}
	value, configured, err = readSecretEnv("TEST_SECRET_SOURCE")
	if err != nil || !configured || value != "  compose-value  " {
		t.Fatalf("plain Compose value changed: configured=%v value=%q err=%v", configured, value, err)
	}
}

func TestReadSecretEnvRejectsMultilineFileWithoutFallbackOrDisclosure(t *testing.T) {
	path := filepath.Join(t.TempDir(), "credential")
	if err := os.WriteFile(path, []byte("synthetic-first-line\nsynthetic-second-line"), 0o600); err != nil {
		t.Fatal(err)
	}
	t.Setenv("TEST_SECRET_SOURCE", "compose-fallback-value")
	t.Setenv("TEST_SECRET_SOURCE_FILE", path)
	value, configured, err := readSecretEnv("TEST_SECRET_SOURCE")
	if err == nil || !configured || value != "" {
		t.Fatalf("multiline file did not fail closed: configured=%v value=%q err=%v", configured, value, err)
	}
	if strings.Contains(err.Error(), "synthetic-first-line") || strings.Contains(err.Error(), "synthetic-second-line") || strings.Contains(err.Error(), "compose-fallback-value") {
		t.Fatal("file error disclosed secret bytes")
	}
}

func TestReadSecretEnvRejectsInvalidFilesWithoutFallbackOrSecretDisclosure(t *testing.T) {
	directory := t.TempDir()
	missingPath := filepath.Join(directory, "missing")
	directoryPath := filepath.Join(directory, "directory")
	if err := os.Mkdir(directoryPath, 0o700); err != nil {
		t.Fatal(err)
	}
	oversizedPath := filepath.Join(directory, "oversized")
	if err := os.WriteFile(oversizedPath, []byte(strings.Repeat("x", maxSecretFileSize+1)), 0o600); err != nil {
		t.Fatal(err)
	}
	invalidTextPath := filepath.Join(directory, "invalid-text")
	if err := os.WriteFile(invalidTextPath, []byte{0xff, 0xfe}, 0o600); err != nil {
		t.Fatal(err)
	}
	emptyPath := filepath.Join(directory, "empty")
	if err := os.WriteFile(emptyPath, nil, 0o600); err != nil {
		t.Fatal(err)
	}

	for name, path := range map[string]string{
		"missing":      missingPath,
		"directory":    directoryPath,
		"oversized":    oversizedPath,
		"invalid text": invalidTextPath,
		"empty":        emptyPath,
	} {
		t.Run(name, func(t *testing.T) {
			t.Setenv("TEST_SECRET_SOURCE", strings.Repeat("x", 40))
			t.Setenv("TEST_SECRET_SOURCE_FILE", path)
			value, configured, err := readSecretEnv("TEST_SECRET_SOURCE")
			if err == nil {
				t.Fatal("invalid file unexpectedly succeeded")
			}
			if !configured || value != "" {
				t.Fatalf("file error fell back to env: configured=%v value=%q", configured, value)
			}
			if strings.Contains(err.Error(), strings.Repeat("x", 40)) {
				t.Fatal("error disclosed secret bytes")
			}
		})
	}
}

func TestLoadUsesSecretFilesAndPreservesEnvironmentFallback(t *testing.T) {
	for _, name := range []string{
		"JWT_SECRET_FILE", "REDIS_URL_FILE", "REVOCATION_REDIS_URL_FILE",
		"INTERNAL_HMAC_SECRET_FILE", "FILE_PROCESSING_CAPABILITY_SECRET_FILE",
	} {
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
	secretPath := filepath.Join(t.TempDir(), "jwt-secret")
	if err := os.WriteFile(secretPath, []byte("file-value"), 0o600); err != nil {
		t.Fatal(err)
	}
	revocationURLPath := filepath.Join(t.TempDir(), "redis-url")
	if err := os.WriteFile(revocationURLPath, []byte("redis://localhost:6379/0"), 0o600); err != nil {
		t.Fatal(err)
	}
	t.Setenv("JWT_SECRET", "compose-value")
	t.Setenv("JWT_SECRET_FILE", secretPath)
	t.Setenv("REVOCATION_REDIS_URL", "redis://compose:6379/0")
	t.Setenv("REVOCATION_REDIS_URL_FILE", revocationURLPath)
	t.Setenv("VITE_ENVIRONMENT", "development")

	cfg, err := Load()
	if err != nil {
		t.Fatalf("load config: %v", err)
	}
	if cfg.JWTSecret != "file-value" {
		t.Fatal("JWT secret file was not applied")
	}
	if cfg.RevocationRedisURL != "redis://localhost:6379/0" {
		t.Fatalf("revocation Redis URL file was not applied: %q", cfg.RevocationRedisURL)
	}
}

func TestOpenSecretFilePortableReadsRegularFile(t *testing.T) {
	path := filepath.Join(t.TempDir(), "portable-credential")
	const expected = "portable-file-test-data"
	if err := os.WriteFile(path, []byte(expected), 0o600); err != nil {
		t.Fatal(err)
	}

	file, err := openSecretFilePortable(path)
	if err != nil {
		t.Fatalf("open portable file: %v", err)
	}
	defer func() {
		if closeErr := file.Close(); closeErr != nil {
			t.Errorf("close portable file: %v", closeErr)
		}
	}()

	contents, err := io.ReadAll(file)
	if err != nil {
		t.Fatalf("read portable file: %v", err)
	}
	if string(contents) != expected {
		t.Fatalf("portable file contents = %q, want %q", contents, expected)
	}
}

func TestOpenSecretFilePortablePreservesSymlinkAndParentTraversalSemantics(t *testing.T) {
	root := t.TempDir()
	targetDir := filepath.Join(root, "actual")
	childDir := filepath.Join(targetDir, "child")
	if err := os.MkdirAll(childDir, 0o700); err != nil {
		t.Fatal(err)
	}

	linkPath := filepath.Join(root, "link")
	if err := os.Symlink(filepath.Join("actual", "child"), linkPath); err != nil {
		t.Fatalf("create directory symlink: %v", err)
	}
	if err := os.WriteFile(filepath.Join(targetDir, "credential"), []byte("resolved-target"), 0o600); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(root, "credential"), []byte("lexically-cleaned-target"), 0o600); err != nil {
		t.Fatal(err)
	}

	path := linkPath + string(os.PathSeparator) + ".." + string(os.PathSeparator) + "credential"
	file, err := openSecretFilePortable(path)
	if err != nil {
		t.Fatalf("open symlink/parent path: %v", err)
	}
	defer func() {
		if closeErr := file.Close(); closeErr != nil {
			t.Errorf("close symlink/parent path: %v", closeErr)
		}
	}()

	contents, err := io.ReadAll(file)
	if err != nil {
		t.Fatalf("read symlink/parent path: %v", err)
	}
	if string(contents) != "resolved-target" {
		t.Fatalf("symlink/parent path contents = %q, want filesystem-resolved target", contents)
	}
}

func TestOpenSecretFilePortableRejectsMissingPath(t *testing.T) {
	path := filepath.Join(t.TempDir(), "missing-credential")
	file, err := openSecretFilePortable(path)
	if err == nil {
		if file != nil {
			if closeErr := file.Close(); closeErr != nil {
				t.Errorf("close unexpected portable file: %v", closeErr)
			}
		}
		t.Fatal("opening a missing portable file unexpectedly succeeded")
	}
	if file != nil {
		t.Fatalf("missing portable file returned a descriptor: %v", file)
	}
}

func TestCapturedOpenSecretFileUsesPlatformOpenerAtCallTime(t *testing.T) {
	capturedOpen := openSecretFile
	original := openSecretFilePlatform
	t.Cleanup(func() { openSecretFilePlatform = original })

	called := false
	openSecretFilePlatform = func(path string) (*os.File, error) {
		called = true
		if path != "synthetic-secret-path" {
			t.Errorf("platform opener path = %q, want synthetic path", path)
		}
		return nil, os.ErrPermission
	}

	file, err := capturedOpen("synthetic-secret-path")
	if file != nil {
		t.Fatalf("open callback returned unexpected file: %v", file)
	}
	if !called || err != os.ErrPermission {
		t.Fatalf("open callback result = called %v, error %v; want called and permission error", called, err)
	}
}
