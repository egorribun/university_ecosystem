package middleware

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/gin-gonic/gin"
)

func FuzzJWTValidation(f *testing.F) {
	// Provide seeds
	f.Add("Bearer invalid.token.here")
	f.Add("Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.e30.signature")
	f.Add("invalid_header")
	f.Add("")

	gin.SetMode(gin.TestMode)
	// Create middleware without redis to isolate JWT parsing logic
	m := NewJWTMiddleware("test-secret-at-least-32-bytes-long!", nil)
	handler := m.Validate(context.Background())

	f.Fuzz(func(t *testing.T, authHeader string) {
		w := httptest.NewRecorder()
		c, _ := gin.CreateTestContext(w)

		req, err := http.NewRequestWithContext(context.Background(), http.MethodGet, "/", nil)
		if err != nil {
			return
		}
		
		if authHeader != "" {
			req.Header.Set("Authorization", authHeader)
		}
		
		c.Request = req

		// The handler should safely reject invalid tokens without panicking
		handler(c)
	})
}
