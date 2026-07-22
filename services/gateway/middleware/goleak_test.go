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
	if err := goleak.Find(); err != nil {
		_, _ = fmt.Fprintln(os.Stderr, err)
		code = 1
	}
	os.Exit(code)
}
