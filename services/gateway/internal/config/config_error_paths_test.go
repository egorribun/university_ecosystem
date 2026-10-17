package config

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestLoadFailsClosedForEveryConfiguredSecretFileError(t *testing.T) {
	keys := []string{
		"REVOCATION_REDIS_URL",
		"JWT_SECRET",
		"REDIS_URL",
		"INTERNAL_HMAC_SECRET",
		"FILE_PROCESSING_CAPABILITY_SECRET",
	}
	validFile := filepath.Join(t.TempDir(), "configured-secret")
	if err := os.WriteFile(validFile, []byte("runtime-value\n"), 0o600); err != nil {
		t.Fatalf("write valid earlier secret file: %v", err)
	}

	for index, target := range keys {
		t.Run(target, func(t *testing.T) {
			for _, key := range keys {
				t.Setenv(key, "environment-fallback-marker")
				t.Setenv(key+"_FILE", "")
			}
			for _, key := range keys[:index] {
				t.Setenv(key+"_FILE", validFile)
			}

			cfg, err := Load()
			if err == nil || cfg != nil {
				t.Fatalf("Load did not fail closed for %s_FILE: cfg=%#v err=%v", target, cfg, err)
			}
			if !strings.Contains(err.Error(), target+"_FILE") {
				t.Fatalf("Load error does not identify %s_FILE: %v", target, err)
			}
			if strings.Contains(err.Error(), "environment-fallback-marker") || strings.Contains(err.Error(), "runtime-value") {
				t.Fatal("configuration error disclosed a secret value")
			}
		})
	}
}
