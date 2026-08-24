package spicedb

import (
	"context"
	"fmt"
	"sync"
	"time"
)

// Client defines the interface for SpiceDB ReBAC permission evaluation in Go services.
type Client interface {
	CheckPermission(ctx context.Context, resourceType, resourceID, permission, userID string) (bool, error)
	CheckTenantPermission(ctx context.Context, tenantID, permission, userID string) (bool, error)
	CheckCampusPermission(ctx context.Context, campusID, permission, userID string) (bool, error)
}

// MemoryClient implements Client for local evaluation and caching in Go services.
type MemoryClient struct {
	mu          sync.RWMutex
	permissions map[string]bool
	tenantMap   map[string]string // campusID -> tenantID mapping
}

// NewMemoryClient initializes an in-memory SpiceDB client for Go services.
func NewMemoryClient() *MemoryClient {
	return &MemoryClient{
		permissions: make(map[string]bool),
		tenantMap:   make(map[string]string),
	}
}

// Key formats permission tuples.
func permKey(resourceType, resourceID, permission, userID string) string {
	return fmt.Sprintf("%s:%s#%s@user:%s", resourceType, resourceID, permission, userID)
}

// SetPermission sets a permission state for testing or cache seeding.
func (c *MemoryClient) SetPermission(resourceType, resourceID, permission, userID string, allowed bool) {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.permissions[permKey(resourceType, resourceID, permission, userID)] = allowed
}

// SetCampusTenant sets campus-tenant relationship mapping.
func (c *MemoryClient) SetCampusTenant(campusID, tenantID string) {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.tenantMap[campusID] = tenantID
}

// CheckPermission evaluates a permission tuple.
func (c *MemoryClient) CheckPermission(ctx context.Context, resourceType, resourceID, permission, userID string) (bool, error) {
	if err := ctx.Err(); err != nil {
		return false, err
	}
	c.mu.RLock()
	defer c.mu.RUnlock()

	// Check direct permission
	key := permKey(resourceType, resourceID, permission, userID)
	if allowed, ok := c.permissions[key]; ok {
		return allowed, nil
	}

	// Check global tenant admin permission override if tenant is set
	if tenantID, ok := c.tenantMap[resourceID]; ok {
		tenantAdminKey := permKey("tenant", tenantID, "admin", userID)
		if allowed, ok := c.permissions[tenantAdminKey]; ok && allowed {
			return true, nil
		}
	}

	return false, nil
}

// CheckTenantPermission checks tenant-level permissions.
func (c *MemoryClient) CheckTenantPermission(ctx context.Context, tenantID, permission, userID string) (bool, error) {
	return c.CheckPermission(ctx, "tenant", tenantID, permission, userID)
}

// CheckCampusPermission checks campus-level permissions.
func (c *MemoryClient) CheckCampusPermission(ctx context.Context, campusID, permission, userID string) (bool, error) {
	return c.CheckPermission(ctx, "campus", campusID, permission, userID)
}

// EvaluateWithTimeout evaluates a permission check function with a context timeout.
// The callback receives the derived context and must propagate cancellation to
// its backend call; this prevents a timed-out evaluation from leaking a
// permanently blocked goroutine.
func EvaluateWithTimeout(ctx context.Context, fn func(context.Context) (bool, error), timeout time.Duration) (bool, error) {
	evalCtx, cancel := context.WithTimeout(ctx, timeout)
	defer cancel()

	type res struct {
		allowed bool
		err     error
	}

	ch := make(chan res, 1)
	go func() {
		allowed, err := fn(evalCtx)
		ch <- res{allowed: allowed, err: err}
	}()

	select {
	case <-evalCtx.Done():
		return false, evalCtx.Err()
	case r := <-ch:
		return r.allowed, r.err
	}
}
