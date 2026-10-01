package handlers

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/gin-gonic/gin"
)

func TestProxyHandlerReplacesClientIdentityWithTenantBoundSignature(t *testing.T) {
	const secret = "synthetic-identity-closure-key"// pragma: allowlist secret -- synthetic HMAC test key

	testCases := []struct {
		name               string
		userID             string
		sessionID          string
		tenantID           string
		mustDifferFromBase bool
	}{
		{
			name:      "base identity",
			userID:    "user-verified-1",
			sessionID: "session-verified-1",
			tenantID:  "tenant-verified-1",
		},
		{
			name:               "subject is signed",
			userID:             "user-verified-2",
			sessionID:          "session-verified-1",
			tenantID:           "tenant-verified-1",
			mustDifferFromBase: true,
		},
		{
			name:               "session is signed",
			userID:             "user-verified-1",
			sessionID:          "session-verified-2",
			tenantID:           "tenant-verified-1",
			mustDifferFromBase: true,
		},
		{
			name:               "tenant is signed",
			userID:             "user-verified-1",
			sessionID:          "session-verified-1",
			tenantID:           "tenant-verified-2",
			mustDifferFromBase: true,
		},
		{
			name:      "empty tenant uses two-field contract",
			userID:    "user-verified-1",
			sessionID: "session-verified-1",
		},
	}

	var baseSignature string
	for _, testCase := range testCases {
		t.Run(testCase.name, func(t *testing.T) {
			forwarded := make(chan http.Header, 1)
			backend := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				forwarded <- r.Header.Clone()
				w.WriteHeader(http.StatusNoContent)
			}))
			defer backend.Close()

			router := gin.New()
			router.GET("/api/*path", func(c *gin.Context) {
				// These context values represent claims already authenticated by the
				// gateway middleware; request headers remain entirely untrusted.
				c.Set("user_id", testCase.userID)
				c.Set("session_id", testCase.sessionID)
				c.Set("tenant_id", testCase.tenantID)
				c.Next()
			}, ProxyHandler(createTestProxy(backend.URL), []byte(secret)))

			request := httptest.NewRequest(http.MethodGet, "/api/identity", nil)
			for name, values := range map[string][]string{
				"X-User-ID":            {"forged-user-one", "forged-user-two"},
				"X-Session-ID":         {"forged-session-one", "forged-session-two"},
				"X-Tenant-ID":          {"forged-tenant-one", "forged-tenant-two"},
				"X-Internal-Signature": {"forged-signature-one", "forged-signature-two"},
			} {
				for _, value := range values {
					request.Header.Add(name, value)
				}
			}

			response := newCloseNotifyingRecorder()
			router.ServeHTTP(response, request)
			if response.Code != http.StatusNoContent {
				t.Fatalf("status = %d, want %d; body=%q", response.Code, http.StatusNoContent, response.Body.String())
			}

			var headers http.Header
			select {
			case headers = <-forwarded:
			case <-time.After(5 * time.Second):
				t.Fatal("backend did not receive proxied request")
			}

			assertIdentityHeader(t, headers, "X-User-ID", testCase.userID)
			assertIdentityHeader(t, headers, "X-Session-ID", testCase.sessionID)
			assertIdentityHeader(t, headers, "X-Tenant-ID", testCase.tenantID)

			signature := identityClosureSignature([]byte(secret), testCase.userID, testCase.sessionID, testCase.tenantID)
			assertIdentityHeader(t, headers, "X-Internal-Signature", signature)
			if testCase.name == "base identity" {
				baseSignature = signature
			}
			if testCase.mustDifferFromBase && signature == baseSignature {
				t.Fatal("changing an authenticated identity claim did not change the HMAC")
			}
		})
	}
}

func TestProxyHandlerWithoutSecretDoesNotReuseClientSignature(t *testing.T) {
	forwarded := make(chan http.Header, 1)
	backend := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		forwarded <- r.Header.Clone()
		w.WriteHeader(http.StatusNoContent)
	}))
	defer backend.Close()

	router := gin.New()
	router.GET("/api/*path", func(c *gin.Context) {
		c.Set("user_id", "development-user")
		c.Set("session_id", "development-session")
		c.Set("tenant_id", "development-tenant")
		c.Next()
	}, ProxyHandler(createTestProxy(backend.URL), nil))

	request := httptest.NewRequest(http.MethodGet, "/api/identity", nil)
	request.Header.Set("X-User-ID", "forged-user")
	request.Header.Set("X-Session-ID", "forged-session")
	request.Header.Set("X-Tenant-ID", "forged-tenant")
	request.Header.Set("X-Internal-Signature", "forged-signature")
	response := newCloseNotifyingRecorder()
	router.ServeHTTP(response, request)
	if response.Code != http.StatusNoContent {
		t.Fatalf("status = %d, want %d; body=%q", response.Code, http.StatusNoContent, response.Body.String())
	}

	var headers http.Header
	select {
	case headers = <-forwarded:
	case <-time.After(5 * time.Second):
		t.Fatal("backend did not receive proxied request")
	}
	assertIdentityHeader(t, headers, "X-User-ID", "development-user")
	assertIdentityHeader(t, headers, "X-Session-ID", "development-session")
	assertIdentityHeader(t, headers, "X-Tenant-ID", "development-tenant")
	assertIdentityHeader(t, headers, "X-Internal-Signature", "")
}

func assertIdentityHeader(t *testing.T, headers http.Header, name, expected string) {
	t.Helper()
	values := headers.Values(name)
	if expected == "" {
		if len(values) != 0 {
			t.Errorf("%s = %q, want no forwarded value", name, values)
		}
		return
	}
	if len(values) != 1 || values[0] != expected {
		t.Errorf("%s = %q, want exactly [%q]", name, values, expected)
	}
}

func identityClosureSignature(secret []byte, userID, sessionID, tenantID string) string {
	identity := userID + ":" + sessionID
	if tenantID != "" {
		identity += ":" + tenantID
	}
	mac := hmac.New(sha256.New, secret)
	_, _ = mac.Write([]byte(identity))
	return hex.EncodeToString(mac.Sum(nil))
}
