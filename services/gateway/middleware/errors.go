package middleware

import (
	"github.com/gin-gonic/gin"
)

// ProblemDetail represents an RFC 7807 problem detail response.
type ProblemDetail struct {
	Type     string `json:"type"`
	Title    string `json:"title"`
	Status   int    `json:"status"`
	Detail   string `json:"detail"`
	Instance string `json:"instance"`
}

// AbortWithProblem stops the request and returns an RFC 7807 response.
func AbortWithProblem(c *gin.Context, status int, title, detail, problemType string) {
	c.Header("Content-Type", "application/problem+json")
	c.AbortWithStatusJSON(status, ProblemDetail{
		Type:     problemType,
		Title:    title,
		Status:   status,
		Detail:   detail,
		Instance: c.Request.URL.Path,
	})
}
