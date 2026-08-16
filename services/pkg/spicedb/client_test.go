package spicedb

import (
	"context"
	"errors"
	"testing"
	"time"
)

func TestSpiceDBMemoryClient(t *testing.T) {
	ctx := context.Background()
	client := NewMemoryClient()

	client.SetPermission("campus", "campus-north", "view", "user-100", true)
	client.SetCampusTenant("campus-north", "tenant-guu")
	client.SetPermission("tenant", "tenant-guu", "admin", "admin-1", true)

	// 1. Allowed campus user
	allowed, err := client.CheckCampusPermission(ctx, "campus-north", "view", "user-100")
	if err != nil || !allowed {
		t.Fatalf("expected user-100 to have campus view permission, got allowed=%v err=%v", allowed, err)
	}

	// 2. Unpermitted campus user
	allowed, err = client.CheckCampusPermission(ctx, "campus-north", "view", "user-200")
	if err != nil || allowed {
		t.Fatalf("expected user-200 to be denied campus view permission, got allowed=%v err=%v", allowed, err)
	}

	// 3. Tenant admin override
	allowed, err = client.CheckCampusPermission(ctx, "campus-north", "view", "admin-1")
	if err != nil || !allowed {
		t.Fatalf("expected tenant admin-1 to inherit campus view permission, got allowed=%v err=%v", allowed, err)
	}

	// 4. Timeout evaluation helper
	allowed, err = EvaluateWithTimeout(ctx, func() (bool, error) {
		return client.CheckTenantPermission(ctx, "tenant-guu", "admin", "admin-1")
	}, 1*time.Second)
	if err != nil || !allowed {
		t.Fatalf("expected EvaluateWithTimeout to return allowed=true, got %v err=%v", allowed, err)
	}
}

func TestMemoryClientRejectsCancelledEvaluation(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	client := NewMemoryClient()

	allowed, err := client.CheckPermission(ctx, "campus", "north", "view", "user")

	if allowed {
		t.Fatal("cancelled permission evaluation must fail closed")
	}
	if !errors.Is(err, context.Canceled) {
		t.Fatalf("expected context cancellation, got %v", err)
	}
}

func TestEvaluateWithTimeoutStopsWaitingAtDeadline(t *testing.T) {
	started := make(chan struct{})
	release := make(chan struct{})
	defer close(release)

	allowed, err := EvaluateWithTimeout(
		context.Background(),
		func() (bool, error) {
			close(started)
			<-release
			return true, nil
		},
		10*time.Millisecond,
	)

	<-started
	if allowed {
		t.Fatal("timed-out evaluation must fail closed")
	}
	if !errors.Is(err, context.DeadlineExceeded) {
		t.Fatalf("expected deadline exceeded, got %v", err)
	}
}
