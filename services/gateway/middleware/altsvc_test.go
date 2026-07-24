package middleware

import (
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/gin-gonic/gin"
	"github.com/stretchr/testify/assert"
)

func TestAltSvcMiddleware_DefaultConfig(t *testing.T) {
	gin.SetMode(gin.TestMode)
	r := gin.New()
	r.Use(AltSvcMiddleware("8443", 2592000))

	r.GET("/health", func(c *gin.Context) {
		c.String(http.StatusOK, "OK")
	})

	w := httptest.NewRecorder()
	req, _ := http.NewRequest(http.MethodGet, "/health", nil)
	r.ServeHTTP(w, req)

	assert.Equal(t, http.StatusOK, w.Code)
	assert.Equal(t, `h3=":8443"; ma=2592000`, w.Header().Get("Alt-Svc"))
}

func TestAltSvcMiddleware_CustomPortAndMaxAge(t *testing.T) {
	gin.SetMode(gin.TestMode)
	r := gin.New()
	r.Use(AltSvcMiddleware("9443", 86400))

	r.GET("/api/v1/test", func(c *gin.Context) {
		c.String(http.StatusOK, "OK")
	})

	w := httptest.NewRecorder()
	req, _ := http.NewRequest(http.MethodGet, "/api/v1/test", nil)
	r.ServeHTTP(w, req)

	assert.Equal(t, http.StatusOK, w.Code)
	assert.Equal(t, `h3=":9443"; ma=86400`, w.Header().Get("Alt-Svc"))
}

func TestAltSvcMiddleware_EmptyDefaults(t *testing.T) {
	gin.SetMode(gin.TestMode)
	r := gin.New()
	r.Use(AltSvcMiddleware("", 0))

	r.GET("/test", func(c *gin.Context) {
		c.String(http.StatusOK, "OK")
	})

	w := httptest.NewRecorder()
	req, _ := http.NewRequest(http.MethodGet, "/test", nil)
	r.ServeHTTP(w, req)

	assert.Equal(t, http.StatusOK, w.Code)
	assert.Equal(t, `h3=":8443"; ma=2592000`, w.Header().Get("Alt-Svc"))
}
