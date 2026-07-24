package middleware

import (
	"fmt"

	"github.com/gin-gonic/gin"
)

// AltSvcMiddleware returns a Gin middleware that injects the Alt-Svc header
// into all outgoing HTTP responses to advertise HTTP/3 availability over UDP.
// Header format: Alt-Svc: h3=":8443"; ma=2592000
func AltSvcMiddleware(h3Port string, maxAge int) gin.HandlerFunc {
	if h3Port == "" {
		h3Port = "8443"
	}
	if maxAge <= 0 {
		maxAge = 2592000
	}
	altSvcValue := fmt.Sprintf(`h3=":%s"; ma=%d`, h3Port, maxAge)

	return func(c *gin.Context) {
		c.Writer.Header().Set("Alt-Svc", altSvcValue)
		c.Next()
	}
}
