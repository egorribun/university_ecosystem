package config

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestReadSecretEnvSupportsProjectedSecretSymlinkAndPrefersFile(t *testing.T) {
	directory := t.TempDir()
	versionDirectory := filepath.Join(directory, "..2026_10_15_000000")
	if err := os.Mkdir(versionDirectory, 0o700); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(versionDirectory, "password"), []byte("from-file"), 0o600); err != nil {
		t.Fatal(err)
	}
	if err := os.Symlink(filepath.Base(versionDirectory), filepath.Join(directory, "..data")); err != nil {
		t.Fatalf("directory symlinks are unavailable: %v", err)
	}
	projectedPath := filepath.Join(directory, "password")
	if err := os.Symlink(filepath.Join("..data", "password"), projectedPath); err != nil {
		t.Fatalf("projected Secret symlinks are unavailable: %v", err)
	}
	t.Setenv("TEST_SECRET_VALUE", "compose-test-value")
	t.Setenv("TEST_SECRET_VALUE_FILE", projectedPath)

	value, configured, err := readSecretEnv("TEST_SECRET_VALUE")
	if err != nil {
		t.Fatalf("read projected secret: %v", err)
	}
	if !configured || value != "from-file" {
		t.Fatalf("file did not take precedence: configured=%v value=%q", configured, value)
	}
}

func TestReadSecretEnvNormalizesFileLineAndPreservesPlainEnvironmentBytes(t *testing.T) {
	path := filepath.Join(t.TempDir(), "credential")
	if err := os.WriteFile(path, []byte(" \tfile-value \n"), 0o600); err != nil {
		t.Fatal(err)
	}
	t.Setenv("TEST_SECRET_VALUE", "  compose-value  ")
	t.Setenv("TEST_SECRET_VALUE_FILE", path)
	value, configured, err := readSecretEnv("TEST_SECRET_VALUE")
	if err != nil || !configured || value != "file-value" {
		t.Fatalf("file value normalization failed: configured=%v value=%q err=%v", configured, value, err)
	}
	if err := os.Unsetenv("TEST_SECRET_VALUE_FILE"); err != nil {
		t.Fatal(err)
	}
	value, configured, err = readSecretEnv("TEST_SECRET_VALUE")
	if err != nil || !configured || value != "  compose-value  " {
		t.Fatalf("plain Compose value changed: configured=%v value=%q err=%v", configured, value, err)
	}
}

func TestReadSecretEnvRejectsMultilineFileWithoutFallbackOrDisclosure(t *testing.T) {
	path := filepath.Join(t.TempDir(), "credential")
	if err := os.WriteFile(path, []byte("synthetic-first-line\nsynthetic-second-line"), 0o600); err != nil {
		t.Fatal(err)
	}
	t.Setenv("TEST_SECRET_VALUE", "compose-fallback-value")
	t.Setenv("TEST_SECRET_VALUE_FILE", path)
	value, configured, err := readSecretEnv("TEST_SECRET_VALUE")
	if err == nil || !configured || value != "" {
		t.Fatalf("multiline file did not fail closed: configured=%v value=%q err=%v", configured, value, err)
	}
	if strings.Contains(err.Error(), "synthetic-first-line") || strings.Contains(err.Error(), "synthetic-second-line") || strings.Contains(err.Error(), "compose-fallback-value") {
		t.Fatal("file error disclosed secret bytes")
	}
}

func TestReadSecretEnvFailsClosedForInvalidFiles(t *testing.T) {
	directory := t.TempDir()
	directoryPath := filepath.Join(directory, "directory")
	if err := os.Mkdir(directoryPath, 0o700); err != nil {
		t.Fatal(err)
	}
	oversizedPath := filepath.Join(directory, "oversized")
	if err := os.WriteFile(oversizedPath, []byte(strings.Repeat("x", maxSecretFileSize+1)), 0o600); err != nil {
		t.Fatal(err)
	}
	invalidTextPath := filepath.Join(directory, "invalid-text")
	if err := os.WriteFile(invalidTextPath, []byte{0xff}, 0o600); err != nil {
		t.Fatal(err)
	}
	missingPath := filepath.Join(directory, "missing")

	for name, path := range map[string]string{
		"missing":      missingPath,
		"directory":    directoryPath,
		"oversized":    oversizedPath,
		"invalid text": invalidTextPath,
	} {
		t.Run(name, func(t *testing.T) {
			t.Setenv("TEST_SECRET_VALUE", "nonsecret-test-value")
			t.Setenv("TEST_SECRET_VALUE_FILE", path)
			value, configured, err := readSecretEnv("TEST_SECRET_VALUE")
			if err == nil {
				t.Fatal("invalid file unexpectedly succeeded")
			}
			if !configured || value != "" {
				t.Fatalf("file error fell back to env: configured=%v value=%q", configured, value)
			}
			if strings.Contains(err.Error(), "nonsecret-test-value") {
				t.Fatal("error disclosed secret bytes")
			}
		})
	}
}

func TestLoadConfigUsesSecretFilesAndKeepsComposeEnvFallback(t *testing.T) {
	for _, name := range []string{
		"NATS_URL_FILE", "NATS_USER_FILE", "NATS_PASSWORD_FILE", "NATS_AUTH_TOKEN_FILE",
		"JWT_SECRETS_FILE", "JWT_SECRET_FILE", "WS_HUB_INTERNAL_SECRET_FILE",
		"INTERNAL_AUTH_TOKEN_FILE", "REDIS_URL_FILE", "REDIS_PASSWORD_FILE",
		"REVOCATION_REDIS_URL_FILE",
	} {
		clearEnvForSecretFileTest(t, name)
	}
	files := map[string]string{
		"NATS_URL_FILE":               "nats://file-nats:4222",
		"JWT_SECRET_FILE":             "file-value",
		"NATS_AUTH_TOKEN_FILE":        "nats-token-value",
		"WS_HUB_INTERNAL_SECRET_FILE": "internal-value",
		"INTERNAL_AUTH_TOKEN_FILE":    "callback-value",
		"REDIS_URL_FILE":              "redis://file-redis:6379",
		"REDIS_PASSWORD_FILE":         "redis-password-value",
		"REVOCATION_REDIS_URL_FILE":   "redis://file-revocation:6379/0",
	}
	for envName, contents := range files {
		path := filepath.Join(t.TempDir(), strings.ToLower(envName))
		if err := os.WriteFile(path, []byte(contents), 0o600); err != nil {
			t.Fatal(err)
		}
		t.Setenv(envName, path)
	}
	t.Setenv("NATS_URL", "nats://compose:4222")
	t.Setenv("JWT_SECRET", "compose-value")
	t.Setenv("VITE_ENVIRONMENT", "test")

	cfg, err := LoadConfig()
	if err != nil {
		t.Fatalf("load config: %v", err)
	}
	if cfg.NatsURL != "nats://file-nats:4222" || len(cfg.JWTSecrets) != 1 || cfg.JWTSecrets[0] != "file-value" {
		t.Fatal("file values did not override Compose environment")
	}
	if cfg.NatsAuthToken != "nats-token-value" || cfg.InternalSecret != "internal-value" || cfg.InternalAuthToken != "callback-value" {
		t.Fatal("internal file values were not loaded")
	}
	if cfg.RedisURL != "redis://file-redis:6379" || cfg.RedisPassword != "redis-password-value" || cfg.RevocationRedisURL != "redis://file-revocation:6379/0" {
		t.Fatal("Redis file values were not loaded")
	}
}

func clearEnvForSecretFileTest(t *testing.T, name string) {
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
