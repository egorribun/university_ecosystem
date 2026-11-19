package spicedb

import (
	"context"
	"testing"
)

func TestMemoryClientTenantInheritanceIsCampusScoped(t *testing.T) {
	client := NewMemoryClient()
	client.SetCampusTenant("shared-id", "parent-tenant")
	client.SetPermission("tenant", "parent-tenant", "admin", "admin", true)
	ctx := context.Background()

	for _, resourceType := range []string{"campus", "tenant", "document", "course", ""} {
		t.Run(resourceType, func(t *testing.T) {
			allowed, err := client.CheckPermission(ctx, resourceType, "shared-id", "view", "admin")
			want := resourceType == "campus"
			if err != nil || allowed != want {
				t.Fatalf("CheckPermission(%q): allowed=%v err=%v, want %v", resourceType, allowed, err, want)
			}
		})
	}

	allowed, err := client.CheckTenantPermission(ctx, "shared-id", "manage", "admin")
	if err != nil || allowed {
		t.Fatalf("unrelated tenant must not inherit campus permissions: allowed=%v err=%v", allowed, err)
	}
	allowed, err = client.CheckCampusPermission(ctx, "shared-id", "manage", "admin")
	if err != nil || !allowed {
		t.Fatalf("mapped campus must retain tenant inheritance: allowed=%v err=%v", allowed, err)
	}
}

func TestMemoryClientDirectPermissionsPrecedeCampusInheritance(t *testing.T) {
	for _, resourceType := range []string{"campus", "tenant", "document"} {
		for _, direct := range []bool{false, true} {
			client := NewMemoryClient()
			client.SetCampusTenant("shared-id", "parent-tenant")
			client.SetPermission("tenant", "parent-tenant", "admin", "admin", true)
			client.SetPermission(resourceType, "shared-id", "view", "admin", direct)

			allowed, err := client.CheckPermission(context.Background(), resourceType, "shared-id", "view", "admin")
			if err != nil || allowed != direct {
				t.Fatalf("direct %q permission %v: allowed=%v err=%v", resourceType, direct, allowed, err)
			}
		}
	}
}

func TestMemoryClientCampusInheritanceRequiresMatchingMappingAndAdmin(t *testing.T) {
	client := NewMemoryClient()
	client.SetCampusTenant("mapped-campus", "parent-tenant")
	client.SetPermission("tenant", "parent-tenant", "admin", "admin", true)
	client.SetPermission("tenant", "parent-tenant", "admin", "denied-admin", false)

	for _, tc := range []struct {
		campusID string
		userID   string
	}{
		{"unmapped-campus", "admin"},
		{"mapped-campus", "other-user"},
		{"mapped-campus", "denied-admin"},
	} {
		allowed, err := client.CheckCampusPermission(context.Background(), tc.campusID, "view", tc.userID)
		if err != nil || allowed {
			t.Fatalf("campus=%q user=%q: allowed=%v err=%v, want denial", tc.campusID, tc.userID, allowed, err)
		}
	}
}
