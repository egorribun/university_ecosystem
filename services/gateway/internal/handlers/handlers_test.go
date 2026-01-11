package handlers

import (
	"net/http"
	"net/http/httptest"
	"net/http/httputil"
	"net/url"
	"strings"
	"testing"

	"github.com/gin-gonic/gin"
	"github.com/stretchr/testify/assert"
)

type closeNotifyingRecorder struct {
	*httptest.ResponseRecorder
	closed chan bool
}

func (c *closeNotifyingRecorder) CloseNotify() <-chan bool {
	return c.closed
}

func newCloseNotifyingRecorder() *closeNotifyingRecorder {
	return &closeNotifyingRecorder{
		ResponseRecorder: httptest.NewRecorder(),
		closed:           make(chan bool, 1),
	}
}

func init() {
	gin.SetMode(gin.TestMode)
}

func TestGenerateRequestID_ReturnsNonEmptyString(t *testing.T) {
	requestID := GenerateRequestID()

	assert.NotEmpty(t, requestID)
}

func TestGenerateRequestID_ContainsDatePrefix(t *testing.T) {
	requestID := GenerateRequestID()

	assert.Contains(t, requestID, "-")
	parts := strings.Split(requestID, "-")
	assert.Len(t, parts, 2)
	assert.Len(t, parts[0], 14) // Format: 20060102150405
}

func TestGenerateRequestID_HasSuffix(t *testing.T) {
	requestID := GenerateRequestID()

	parts := strings.Split(requestID, "-")
	assert.Len(t, parts[1], 8)
}

func TestHealthHandler_ReturnsOKStatus(t *testing.T) {
	router := gin.New()
	router.GET("/health", HealthHandler)

	request := httptest.NewRequest(http.MethodGet, "/health", nil)
	recorder := httptest.NewRecorder()

	router.ServeHTTP(recorder, request)

	assert.Equal(t, http.StatusOK, recorder.Code)
}

func TestHealthHandler_ReturnsCorrectJSON(t *testing.T) {
	router := gin.New()
	router.GET("/health", HealthHandler)

	request := httptest.NewRequest(http.MethodGet, "/health", nil)
	recorder := httptest.NewRecorder()

	router.ServeHTTP(recorder, request)

	body := recorder.Body.String()
	assert.Contains(t, body, `"status":"healthy"`)
	assert.Contains(t, body, `"service":"gateway"`)
}

func TestMetricsHandler_ReturnsOKStatus(t *testing.T) {
	router := gin.New()
	router.GET("/metrics", MetricsHandler)

	request := httptest.NewRequest(http.MethodGet, "/metrics", nil)
	recorder := httptest.NewRecorder()

	router.ServeHTTP(recorder, request)

	assert.Equal(t, http.StatusOK, recorder.Code)
}

func TestMetricsHandler_ReturnsStatusOK(t *testing.T) {
	router := gin.New()
	router.GET("/metrics", MetricsHandler)

	request := httptest.NewRequest(http.MethodGet, "/metrics", nil)
	recorder := httptest.NewRecorder()

	router.ServeHTTP(recorder, request)

	assert.Contains(t, recorder.Body.String(), `"status":"ok"`)
}

func TestProxyHandler_SetsRequestIDHeader(t *testing.T) {
	backendServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		requestID := r.Header.Get("X-Request-ID")
		assert.NotEmpty(t, requestID)
		w.WriteHeader(http.StatusOK)
	}))
	defer backendServer.Close()

	proxy := createTestProxy(backendServer.URL)
	router := gin.New()
	router.GET("/api/*path", ProxyHandler(proxy))

	request := httptest.NewRequest(http.MethodGet, "/api/test", nil)
	recorder := newCloseNotifyingRecorder()

	router.ServeHTTP(recorder, request)

	assert.Equal(t, http.StatusOK, recorder.Code)
}

func TestProxyHandler_PreservesExistingRequestID(t *testing.T) {
	existingID := "existing-request-id-123"
	var capturedID string

	backendServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		capturedID = r.Header.Get("X-Request-ID")
		w.WriteHeader(http.StatusOK)
	}))
	defer backendServer.Close()

	proxy := createTestProxy(backendServer.URL)
	router := gin.New()
	router.GET("/api/*path", ProxyHandler(proxy))

	request := httptest.NewRequest(http.MethodGet, "/api/test", nil)
	request.Header.Set("X-Request-ID", existingID)
	recorder := newCloseNotifyingRecorder()

	router.ServeHTTP(recorder, request)

	assert.Equal(t, existingID, capturedID)
}

func TestProxyHandler_AddsUserIDHeader(t *testing.T) {
	var capturedUserID string

	backendServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		capturedUserID = r.Header.Get("X-User-ID")
		w.WriteHeader(http.StatusOK)
	}))
	defer backendServer.Close()

	proxy := createTestProxy(backendServer.URL)
	router := gin.New()
	router.GET("/api/*path", func(c *gin.Context) {
		c.Set("user_id", "user-456")
		c.Next()
	}, ProxyHandler(proxy))

	request := httptest.NewRequest(http.MethodGet, "/api/test", nil)
	recorder := newCloseNotifyingRecorder()

	router.ServeHTTP(recorder, request)

	assert.Equal(t, "user-456", capturedUserID)
}

func TestRandomString_ReturnsCorrectLength(t *testing.T) {
	for _, length := range []int{1, 5, 8, 16, 32} {
		result := randomString(length)
		assert.Len(t, result, length)
	}
}

func TestRandomString_ContainsOnlyValidCharacters(t *testing.T) {
	validChars := "abcdefghijklmnopqrstuvwxyz0123456789"
	result := randomString(100)

	for _, char := range result {
		assert.Contains(t, validChars, string(char))
	}
}

func TestGenerateRequestID_IsUnique(t *testing.T) {
	ids := make(map[string]bool)
	for i := 0; i < 100; i++ {
		id := GenerateRequestID()
		assert.False(t, ids[id], "Generated duplicate ID")
		ids[id] = true
	}
}

func createTestProxy(targetURL string) *httputil.ReverseProxy {
	target, _ := url.Parse(targetURL)
	return httputil.NewSingleHostReverseProxy(target)
}
