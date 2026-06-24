package hub

import (
	"context"
	"testing"
	"time"
)


func TestHub_StartLimiterCleanup(t *testing.T) {
	h := newNatsTestHub(&mockAuthClient{allowed: true}, "", 10)
	ctx, cancel := context.WithCancel(context.Background())
	cancel() // cancel immediately
	
	// StartLimiterCleanup runs in a goroutine and exits immediately because of canceled context
	h.StartLimiterCleanup(ctx)
	
	// Give a tiny bit of time for goroutine scheduler
	time.Sleep(10 * time.Millisecond)
}

func TestWSUpgradeRateLimiter_GC(t *testing.T) {
	// Create limiter
	limiter := NewWSUpgradeRateLimiter(2, 1)
	
	// Add an item to trigger Allow and populate buckets
	limiter.Allow("192.168.1.1")
	
	// Stop will trigger the stopGC channel and return from gcLoop
	limiter.Stop()
	
	// Give a tiny bit of time for goroutine scheduler
	time.Sleep(10 * time.Millisecond)
}
