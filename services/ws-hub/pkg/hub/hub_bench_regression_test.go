package hub

import "testing"

func TestBenchmarkSafeSendBoundsAndReleasesChannels(t *testing.T) {
	originalHook := safeSendAfterLockHook
	channels := make(map[chan []byte]struct{})
	t.Cleanup(func() {
		safeSendAfterLockHook = originalHook
		for ch := range channels {
			safeClose(ch)
		}
	})

	result := testing.Benchmark(func(b *testing.B) {
		defer func() {
			if b.Failed() {
				t.Error("safeSend benchmark failed")
			}
		}()
		safeSendAfterLockHook = func(ch chan []byte, _ *chEntry) {
			channels[ch] = struct{}{}
			if cap(ch) != 256 {
				t.Errorf("benchmark channel capacity = %d; want fixed client buffer size 256", cap(ch))
				b.FailNow()
			}
		}
		BenchmarkSafeSend(b)
	})
	if result.N == 0 || len(channels) == 0 {
		t.Fatal("benchmark did not exercise safeSend")
	}

	for ch := range channels {
		chMu.RLock()
		_, retained := chMutexes[ch]
		chMu.RUnlock()
		if retained {
			t.Error("benchmark channel remains retained by the safeSend registry")
		}
		select {
		case _, open := <-ch:
			if open {
				t.Error("benchmark left an undrained or open channel")
			}
		default:
			t.Error("benchmark left its channel open")
		}
	}
}
