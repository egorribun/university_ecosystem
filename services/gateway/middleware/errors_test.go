package middleware

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/gin-gonic/gin"
	"github.com/stretchr/testify/assert"
)

func TestAbortWithProblem(t *testing.T) {
	// Setup gin in test mode
	gin.SetMode(gin.TestMode)

	t.Run("returns correct RFC 7807 response", func(t *testing.T) {
		w := httptest.NewRecorder()
		c, _ := gin.CreateTestContext(w)

		// Setup mock request for Instance path
		req, err := http.NewRequestWithContext(context.Background(), "GET", "/test-endpoint", nil)
		assert.NoError(t, err)
		c.Request = req

		status := http.StatusBadRequest
		title := "Bad Request"
		detail := "The request was missing required fields"
		problemType := "https://example.com/probs/bad-request"

		AbortWithProblem(c, status, title, detail, problemType)

		assert.Equal(t, status, w.Code)
		assert.Equal(t, "application/problem+json", w.Header().Get("Content-Type"))

		var body ProblemDetail
		err = json.Unmarshal(w.Body.Bytes(), &body)
		assert.NoError(t, err)

		assert.Equal(t, problemType, body.Type)
		assert.Equal(t, title, body.Title)
		assert.Equal(t, status, body.Status)
		assert.Equal(t, detail, body.Detail)
		assert.Equal(t, "/test-endpoint", body.Instance)
	})
}
