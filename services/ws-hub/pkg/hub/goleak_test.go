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
	opts := []goleak.Option{
		goleak.IgnoreTopFunction("net/http.(*Transport).startDialConnForLocked"),
		goleak.IgnoreTopFunction("net/http.(*Transport).dialConn"),
		goleak.IgnoreTopFunction("net.(*Resolver).lookupIP"),
		goleak.IgnoreTopFunction("net.(*Resolver).lookupIPAddr"),
		goleak.IgnoreTopFunction("net.(*Resolver).lookupIP.func1"),
		goleak.IgnoreTopFunction("net.(*Resolver).lookupIP.func2"),
		goleak.IgnoreTopFunction("syscall.SyscallN"),
		goleak.IgnoreTopFunction("syscall.syscalln"),
		goleak.IgnoreTopFunction("syscall.GetAddrInfoW"),
		goleak.IgnoreTopFunction("internal/singleflight.(*Group).doCall"),
		goleak.IgnoreTopFunction("github.com/lestrrat-go/httprc.runFetchWorker"),
		goleak.IgnoreTopFunction("github.com/lestrrat-go/httprc.(*queue).refreshLoop"),
		goleak.IgnoreTopFunction("github.com/lestrrat-go/httprc.(*queue).fetchLoop"),
		goleak.IgnoreTopFunction("sync.runtime_notifyListWait"),
		goleak.IgnoreTopFunction("sync.(*Cond).Wait"),
	}
	if err := goleak.Find(opts...); err != nil {
		_, _ = fmt.Fprintln(os.Stderr, err)
		code = 1
	}
	os.Exit(code)
}
