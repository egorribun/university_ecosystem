package spicedb

import (
	"context"
	"os"
	"os/exec"
	"strings"
	"testing"
	"time"
)

const panicNilChildEnv = "AUD507_PANICNIL_CHILD"

func TestEvaluateWithTimeoutRecoversCallbackPanic(t *testing.T) {
	const panicValue = "AUD507_SYNTHETIC_PANIC_MARKER"

	allowed, err := EvaluateWithTimeout(
		context.Background(),
		func(context.Context) (bool, error) {
			panic(panicValue)
		},
		time.Second,
	)

	if allowed {
		t.Fatal("panicked permission evaluation must fail closed")
	}
	if err == nil {
		t.Fatal("panicked permission evaluation must return an error")
	}
	if err.Error() != "permission evaluation panicked" {
		t.Fatalf("unexpected sanitized panic error: %q", err)
	}
	if strings.Contains(err.Error(), panicValue) {
		t.Fatal("callback panic value must not be included in the returned error")
	}
}

func TestEvaluateWithTimeoutRecoversNilPanicByDefault(t *testing.T) {
	assertNilPanicFailsClosed(t)
}

func TestEvaluateWithTimeoutRecoversNilPanicWithPanicNilDebug(t *testing.T) {
	if os.Getenv(panicNilChildEnv) == "1" {
		assertNilPanicFailsClosed(t)
		return
	}

	executable, err := os.Executable()
	if err != nil {
		t.Fatalf("locate test executable: %v", err)
	}
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	cmd := exec.CommandContext(ctx, executable, "-test.run=^TestEvaluateWithTimeoutRecoversNilPanicWithPanicNilDebug$")
	for _, entry := range os.Environ() {
		key, _, _ := strings.Cut(entry, "=")
		if key == "GODEBUG" || key == panicNilChildEnv {
			continue
		}
		cmd.Env = append(cmd.Env, entry)
	}
	cmd.Env = append(cmd.Env, "GODEBUG=panicnil=1", panicNilChildEnv+"=1")

	output, err := cmd.CombinedOutput()
	if err != nil {
		t.Fatalf("panicnil=1 subprocess failed: %v; output:\n%s", err, output)
	}
}

func assertNilPanicFailsClosed(t *testing.T) {
	t.Helper()

	allowed, err := EvaluateWithTimeout(
		context.Background(),
		func(context.Context) (bool, error) {
			panic(nil)
		},
		time.Second,
	)
	if allowed {
		t.Fatal("panicked permission evaluation must fail closed")
	}
	if err == nil || err.Error() != "permission evaluation panicked" {
		t.Fatalf("nil panic must return the sanitized error; got %v", err)
	}
}
