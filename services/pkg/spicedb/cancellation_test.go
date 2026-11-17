package spicedb

import (
	"context"
	"errors"
	"sync/atomic"
	"testing"
	"testing/synctest"
	"time"
)

func TestEvaluateWithTimeoutDoesNotDispatchExpiredContext(t *testing.T) {
	for _, timeout := range []time.Duration{0, -time.Second} {
		t.Run(timeout.String(), func(t *testing.T) {
			synctest.Test(t, func(t *testing.T) {
				var calls atomic.Int32
				allowed, err := EvaluateWithTimeout(context.Background(), func(context.Context) (bool, error) {
					calls.Add(1)
					return true, nil
				}, timeout)
				synctest.Wait()
				if allowed || !errors.Is(err, context.DeadlineExceeded) || calls.Load() != 0 {
					t.Fatalf("expired evaluation dispatched or allowed: allowed=%v err=%v calls=%d", allowed, err, calls.Load())
				}
			})
		})
	}
}

func TestEvaluateWithTimeoutDoesNotDispatchCancelledParent(t *testing.T) {
	synctest.Test(t, func(t *testing.T) {
		ctx, cancel := context.WithCancel(context.Background())
		cancel()
		var calls atomic.Int32
		allowed, err := EvaluateWithTimeout(ctx, func(context.Context) (bool, error) {
			calls.Add(1)
			return true, nil
		}, time.Second)
		synctest.Wait()
		if allowed || !errors.Is(err, context.Canceled) || calls.Load() != 0 {
			t.Fatalf("cancelled evaluation dispatched or allowed: allowed=%v err=%v calls=%d", allowed, err, calls.Load())
		}
	})
}

func TestPermissionResultAcceptanceHonorsCancellation(t *testing.T) {
	callbackErr := errors.New("callback failure")
	for _, allowed := range []bool{false, true} {
		for _, resultErr := range []error{nil, callbackErr} {
			ctx, cancel := context.WithCancel(context.Background())
			cancel()
			got, err := acceptPermissionEvaluation(ctx, allowed, resultErr)
			if got || !errors.Is(err, context.Canceled) {
				t.Fatalf("cancelled completed result accepted: allowed=%v err=%v", got, err)
			}
		}
	}
	ctx, cancel := context.WithDeadline(context.Background(), time.Now().Add(-time.Second))
	defer cancel()
	if allowed, err := acceptPermissionEvaluation(ctx, true, nil); allowed || !errors.Is(err, context.DeadlineExceeded) {
		t.Fatalf("expired completed result accepted: allowed=%v err=%v", allowed, err)
	}
}

func TestPermissionResultAcceptancePreservesLiveResults(t *testing.T) {
	callbackErr := errors.New("callback failure")
	for _, allowed := range []bool{false, true} {
		for _, resultErr := range []error{nil, callbackErr} {
			got, err := acceptPermissionEvaluation(context.Background(), allowed, resultErr)
			if got != allowed || err != resultErr {
				t.Fatalf("live result changed: allowed=%v err=%v", got, err)
			}
		}
	}
}

func TestEvaluateWithTimeoutRejectsCallbackCancellingParent(t *testing.T) {
	synctest.Test(t, func(t *testing.T) {
		ctx, cancel := context.WithCancel(context.Background())
		defer cancel()
		var calls atomic.Int32
		allowed, err := EvaluateWithTimeout(ctx, func(context.Context) (bool, error) {
			calls.Add(1)
			cancel()
			return true, nil
		}, time.Second)
		synctest.Wait()
		if allowed || !errors.Is(err, context.Canceled) || calls.Load() != 1 {
			t.Fatalf("cancelled callback accepted: allowed=%v err=%v calls=%d", allowed, err, calls.Load())
		}
	})
}
