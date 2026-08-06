package spicedb

import (
	"context"
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
