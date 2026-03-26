package handlers

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"net/http"
	"net/http/httptest"
	"net/http/httputil"
	"net/url"
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

func TestProxyHandler_SetsRequestIDHeader(t *testing.T) {
	backendServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		requestID := r.Header.Get("X-Request-ID")
		assert.NotEmpty(t, requestID)
		w.WriteHeader(http.StatusOK)
	}))
	defer backendServer.Close()

	proxy := createTestProxy(backendServer.URL)
	router := gin.New()
	router.GET("/api/*path", ProxyHandler(proxy, nil))

	request := httptest.NewRequest(http.MethodGet, "/api/test", nil)
	recorder := newCloseNotifyingRecorder()

	router.ServeHTTP(recorder, request)

	assert.Equal(t, http.StatusOK, recorder.Code)
}

func TestProxyHandler_PreservesExistingRequestID(t *testing.T) {
	// Must be a valid UUID v4 (lowercase hex) — the handler replaces non-UUID values.
	existingID := "550e8400-e29b-41d4-a716-446655440000"
	var capturedID string

	backendServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		capturedID = r.Header.Get("X-Request-ID")
		w.WriteHeader(http.StatusOK)
	}))
	defer backendServer.Close()

	proxy := createTestProxy(backendServer.URL)
	router := gin.New()
	router.GET("/api/*path", ProxyHandler(proxy, nil))

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
	}, ProxyHandler(proxy, nil))

	request := httptest.NewRequest(http.MethodGet, "/api/test", nil)
	recorder := newCloseNotifyingRecorder()

	router.ServeHTTP(recorder, request)

	assert.Equal(t, "user-456", capturedUserID)
}

// TestProxyHandler_SetsInternalSignature verifies that when an HMAC secret is
// configured, ProxyHandler computes X-Internal-Signature as
// HMAC-SHA256("{user_id}:{session_id}") and that client-supplied forgeries are
// stripped before a fresh signature is added. (RZ-14-05)
func TestProxyHandler_SetsInternalSignature(t *testing.T) {
	const (
		testUserID    = "550e8400-e29b-41d4-a716-446655440000"
		testSessionID = "session-jti-abc123"
	)
	secret := []byte("test-internal-hmac-secret-32bytes!")

	var capturedSig, capturedUserID, capturedSessionID string
	backendServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		capturedSig = r.Header.Get("X-Internal-Signature")
		capturedUserID = r.Header.Get("X-User-ID")
		capturedSessionID = r.Header.Get("X-Session-ID")
		w.WriteHeader(http.StatusOK)
	}))
	defer backendServer.Close()

	proxy := createTestProxy(backendServer.URL)
	router := gin.New()
	router.GET("/api/*path", func(c *gin.Context) {
		c.Set("user_id", testUserID)
		c.Set("session_id", testSessionID)
		c.Next()
	}, ProxyHandler(proxy, secret))

	// Attempt to forge signature — must be replaced with the real one.
	request := httptest.NewRequest(http.MethodGet, "/api/test", nil)
	request.Header.Set("X-Internal-Signature", "forged-signature")
	recorder := newCloseNotifyingRecorder()

	router.ServeHTTP(recorder, request)

	assert.Equal(t, http.StatusOK, recorder.Code)
	assert.Equal(t, testUserID, capturedUserID)
	assert.Equal(t, testSessionID, capturedSessionID)

	// Compute expected HMAC-SHA256 independently.
	mac := hmac.New(sha256.New, secret)
	mac.Write([]byte(testUserID + ":" + testSessionID))
	expected := hex.EncodeToString(mac.Sum(nil))
	assert.Equal(t, expected, capturedSig, "X-Internal-Signature must be HMAC-SHA256 of user_id:session_id")
}

// TestProxyHandler_NoSignatureWithoutSecret ensures X-Internal-Signature is
// NOT set when no HMAC secret is configured (dev mode).
func TestProxyHandler_NoSignatureWithoutSecret(t *testing.T) {
	var capturedSig string
	backendServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		capturedSig = r.Header.Get("X-Internal-Signature")
		w.WriteHeader(http.StatusOK)
	}))
	defer backendServer.Close()

	proxy := createTestProxy(backendServer.URL)
	router := gin.New()
	router.GET("/api/*path", func(c *gin.Context) {
		c.Set("user_id", "some-user")
		c.Set("session_id", "some-session")
		c.Next()
	}, ProxyHandler(proxy, nil))

	request := httptest.NewRequest(http.MethodGet, "/api/test", nil)
	recorder := newCloseNotifyingRecorder()
	router.ServeHTTP(recorder, request)

	assert.Empty(t, capturedSig, "X-Internal-Signature must not be set when HMAC secret is empty")
}

// TestProxyHandler_DropsForgedSignatureWhenNoSecret ensures that a client-supplied
// X-Internal-Signature is deleted even when the gateway has no secret configured.
func TestProxyHandler_DropsForgedSignatureWhenNoSecret(t *testing.T) {
	var capturedSig string
	backendServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		capturedSig = r.Header.Get("X-Internal-Signature")
		w.WriteHeader(http.StatusOK)
	}))
	defer backendServer.Close()

	proxy := createTestProxy(backendServer.URL)
	router := gin.New()
	router.GET("/api/*path", ProxyHandler(proxy, nil))

	request := httptest.NewRequest(http.MethodGet, "/api/test", nil)
	request.Header.Set("X-Internal-Signature", "attacker-forged")
	recorder := newCloseNotifyingRecorder()
	router.ServeHTTP(recorder, request)

	assert.Empty(t, capturedSig, "Client-supplied X-Internal-Signature must always be stripped")
}

func createTestProxy(targetURL string) *httputil.ReverseProxy {
	target, err := url.Parse(targetURL)
	if err != nil {
		panic(fmt.Sprintf("failed to parse test backend URL: %v", err))
	}
	return httputil.NewSingleHostReverseProxy(target)
}
