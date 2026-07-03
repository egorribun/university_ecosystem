package middleware

// Coverage tests (testing session 9) for RequireRole, including the TD-10
// ok-guard branch (a non-string user_role in the gin context must yield 403,
// not a goroutine panic / 500).

import (
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/gin-gonic/gin"
	"github.com/stretchr/testify/assert"
)

// roleRouter wires a preceding middleware that seeds user_role (skipped when
// seed is nil) followed by RequireRole + a 200 terminal handler.
func roleRouter(seed interface{}, roles ...string) *gin.Engine {
	r := gin.New()
	r.GET("/admin",
		func(c *gin.Context) {
			if seed != nil {
				c.Set("user_role", seed)
			}
			c.Next()
		},
		RequireRole(roles...),
		func(c *gin.Context) { c.Status(http.StatusOK) },
	)
	return r
}

func TestRequireRole_NoRoleInContext(t *testing.T) {
	rec := httptest.NewRecorder()
	roleRouter(nil, "admin").ServeHTTP(rec, httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/admin", nil))
	assert.Equal(t, http.StatusForbidden, rec.Code)
	assert.Contains(t, rec.Body.String(), "role not found in token")
}

func TestRequireRole_NonStringRoleRejected(t *testing.T) {
	// TD-10: an int in the context must NOT panic the goroutine.
	rec := httptest.NewRecorder()
	roleRouter(12345, "admin").ServeHTTP(rec, httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/admin", nil))
	assert.Equal(t, http.StatusForbidden, rec.Code)
	assert.Contains(t, rec.Body.String(), "insufficient permissions")
}

func TestRequireRole_RoleNotInSet(t *testing.T) {
	rec := httptest.NewRecorder()
	roleRouter("student", "admin", "staff").ServeHTTP(rec, httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/admin", nil))
	assert.Equal(t, http.StatusForbidden, rec.Code)
	assert.Contains(t, rec.Body.String(), "insufficient permissions")
}

func TestRequireRole_MatchingRolePasses(t *testing.T) {
	rec := httptest.NewRecorder()
	roleRouter("admin", "admin", "staff").ServeHTTP(rec, httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/admin", nil))
	assert.Equal(t, http.StatusOK, rec.Code)
}
