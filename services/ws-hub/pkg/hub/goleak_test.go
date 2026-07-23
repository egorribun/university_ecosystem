package hub

import (
	"fmt"
	"os"
	"sync"
	"testing"

	"go.uber.org/goleak"
)

var testHubs sync.Map

// trackTestHub centralises cleanup for tests that construct a Hub without a
// *testing.T parameter. Production callers use Hub.Stop directly; this registry
// exists only in the test binary so every limiter and Run loop is drained before
// goleak inspects the process.
func trackTestHub(h *Hub) *Hub {
	testHubs.Store(h, struct{}{})
	return h
}

func stopTrackedTestHubs() {
	testHubs.Range(func(key, _ any) bool {
		key.(*Hub).Stop()
		return true
	})
}

func TestMain(m *testing.M) {
	code := m.Run()
	stopTrackedTestHubs()
	if err := goleak.Find(); err != nil {
		_, _ = fmt.Fprintln(os.Stderr, err)
		code = 1
	}
	os.Exit(code)
}
