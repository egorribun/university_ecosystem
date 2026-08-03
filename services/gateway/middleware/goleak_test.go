package middleware

import (
	"fmt"
	"os"
	"testing"

	"go.uber.org/goleak"
)

func TestMain(m *testing.M) {
	code := m.Run()
	// Tests cancel every refresher context; wait for the cancellation branch to
	// return before goleak samples the process. This turns a timing race into a
	// deterministic lifecycle assertion without ignoring any goroutine.
	jwksRefreshWG.Wait()
	opts := []goleak.Option{
		// testcontainers-go talks to Docker Desktop through a Windows named pipe.
		// The go-winio completion worker belongs to that external transport and
		// can outlive container cleanup; it is not an application goroutine.
		goleak.IgnoreAnyFunction("github.com/Microsoft/go-winio.ioCompletionProcessor"),
	}
	if err := goleak.Find(opts...); err != nil {
		_, _ = fmt.Fprintln(os.Stderr, err)
		code = 1
	}
	os.Exit(code)
}
