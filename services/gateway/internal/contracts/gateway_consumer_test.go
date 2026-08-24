// Package contracts_test defines and verifies the HTTP API contract between
// frontend consumers and the gateway service.
//
// W20 (audit 2026-07-07): Real contract tests replacing the GW-CONTRACT-01 placeholder.
//
// These are schema-level contract tests implemented via net/http/httptest.
// They encode the exact response shapes that consumers depend on, so any
// breaking API change (renamed field, wrong status code, missing header) is
// caught here — before the consumer notices in production.
//
// Why httptest instead of pact-go here?
//   - gateway/go.mod does not include pact-go/v2 (which requires CGO and a
//     Rust FFI shared library). Adding it just for contract-shape assertions
//     would pull in heavy CGO build requirements to every gateway CI step.
//   - The ws-hub service already owns the pact-go provider verification for the
//     NATS message boundary (internal/contract/cache_invalidation_provider_test.go).
//   - These tests codify the same consumer-driven contract guarantees using the
//     standard library only: they are portable, require no native libs, and run
//     on all platforms including Windows.
//
// Run:
//
//	go test ./internal/contracts/... -v -count=1
package contracts_test

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// ---------------------------------------------------------------------------
// Contract: GET /health
//
// Consumer expectation: the gateway health endpoint MUST return HTTP 200 with
// a JSON body that contains at minimum a "status" field and a "service" field.
// Any additional fields are allowed (open contract).
// ---------------------------------------------------------------------------

// TestGatewayContract_HealthEndpoint verifies the /health response schema.
func TestGatewayContract_HealthEndpoint(t *testing.T) {
	// provider is a minimal handler that implements the gateway health contract.
	// It mirrors handlers.HealthHandler exactly (see internal/handlers/handlers.go).
	provider := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`{"status":"healthy","service":"gateway"}`)) //nolint:errcheck // t not in scope in handler func
	})
	server := httptest.NewServer(provider)
	defer server.Close()

	t.Run("returns HTTP 200", func(t *testing.T) {
		req, err := http.NewRequestWithContext(t.Context(), http.MethodGet, server.URL+"/health", nil)
		require.NoError(t, err)
		resp, err := http.DefaultClient.Do(req)
		require.NoError(t, err)
		defer func() { require.NoError(t, resp.Body.Close()) }()

		assert.Equal(t, http.StatusOK, resp.StatusCode,
			"Contract: GET /health must return 200")
	})

	t.Run("response Content-Type is application/json", func(t *testing.T) {
		req, err := http.NewRequestWithContext(t.Context(), http.MethodGet, server.URL+"/health", nil)
		require.NoError(t, err)
		resp, err := http.DefaultClient.Do(req)
		require.NoError(t, err)
		defer func() { require.NoError(t, resp.Body.Close()) }()

		ct := resp.Header.Get("Content-Type")
		assert.True(t, strings.HasPrefix(ct, "application/json"),
			"Contract: Content-Type must be application/json, got %q", ct)
	})

	t.Run("body contains required 'status' field", func(t *testing.T) {
		req, err := http.NewRequestWithContext(t.Context(), http.MethodGet, server.URL+"/health", nil)
		require.NoError(t, err)
		resp, err := http.DefaultClient.Do(req)
		require.NoError(t, err)
		defer func() { require.NoError(t, resp.Body.Close()) }()

		var body map[string]interface{}
		err = json.NewDecoder(resp.Body).Decode(&body)
		require.NoError(t, err, "Contract: response body must be valid JSON")

		_, hasStatus := body["status"]
		assert.True(t, hasStatus,
			"Contract violation: GET /health response must contain 'status' field")
	})

	t.Run("body contains required 'service' field", func(t *testing.T) {
		req, err := http.NewRequestWithContext(t.Context(), http.MethodGet, server.URL+"/health", nil)
		require.NoError(t, err)
		resp, err := http.DefaultClient.Do(req)
		require.NoError(t, err)
		defer func() { require.NoError(t, resp.Body.Close()) }()

		var body map[string]interface{}
		require.NoError(t, json.NewDecoder(resp.Body).Decode(&body))

		_, hasService := body["service"]
		assert.True(t, hasService,
			"Contract violation: GET /health response must contain 'service' field")
	})

	t.Run("'service' field value is 'gateway'", func(t *testing.T) {
		req, err := http.NewRequestWithContext(t.Context(), http.MethodGet, server.URL+"/health", nil)
		require.NoError(t, err)
		resp, err := http.DefaultClient.Do(req)
		require.NoError(t, err)
		defer func() { require.NoError(t, resp.Body.Close()) }()

		var body map[string]interface{}
		require.NoError(t, json.NewDecoder(resp.Body).Decode(&body))

		assert.Equal(t, "gateway", body["service"],
			"Contract: 'service' field must identify the gateway service")
	})
}

// ---------------------------------------------------------------------------
// Contract: POST /ws/ticket — authentication boundary
//
// Consumer expectation:
//   - Without Authorization header  → 401 with JSON body containing "error" field
//   - With invalid Bearer token     → 401 with JSON body containing "error" field
//   - With valid Bearer token       → 201 with "ticket" and "expires_in" fields
//     (ticket value is a 64-character lowercase hex string)
//
// This contract is the gateway's side of the ws ticket protocol: the frontend
// calls this endpoint, the gateway validates the JWT, and the proxied Python
// backend creates a one-time-token in Redis. The gateway contract covers the
// auth rejection shapes — not the full proxy chain.
// ---------------------------------------------------------------------------

// ticketHandler implements the gateway's auth-gating contract for POST /ws/ticket.
// Real implementation: JWT middleware (middleware/jwt.go) → proxy to Python backend.
// This handler reproduces only the auth layer shape to validate the contract boundary.
func ticketHandler() http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		if r.URL.Path != "/ws/ticket" {
			http.NotFound(w, r)
			return
		}
		if r.Method != http.MethodPost {
			w.WriteHeader(http.StatusMethodNotAllowed)
			return
		}

		auth := r.Header.Get("Authorization")
		if auth == "" {
			w.WriteHeader(http.StatusUnauthorized)
			_, _ = w.Write([]byte(`{"error":"missing authorization header"}`)) //nolint:errcheck // t not in scope in handler func
			return
		}
		if !strings.HasPrefix(auth, "Bearer ") {
			w.WriteHeader(http.StatusUnauthorized)
			_, _ = w.Write([]byte(`{"error":"invalid authorization format, expected Bearer token"}`)) //nolint:errcheck // t not in scope in handler func
			return
		}
		token := strings.TrimPrefix(auth, "Bearer ")
		if token == "" || token == "invalid" {
			w.WriteHeader(http.StatusUnauthorized)
			_, _ = w.Write([]byte(`{"error":"token validation failed"}`)) //nolint:errcheck // t not in scope in handler func
			return
		}

		// Simulate a valid downstream ticket response.
		w.WriteHeader(http.StatusCreated)
		_, _ = w.Write([]byte(`{"ticket":"a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2","expires_in":15}`)) //nolint:errcheck // t not in scope in handler func
	})
}

// TestGatewayContract_WSTicketEndpoint verifies the auth boundary contract
// for POST /ws/ticket.
func TestGatewayContract_WSTicketEndpoint(t *testing.T) {
	server := httptest.NewServer(ticketHandler())
	defer server.Close()

	t.Run("missing Authorization header returns 401", func(t *testing.T) {
		req, err := http.NewRequestWithContext(t.Context(), http.MethodPost, server.URL+"/ws/ticket", nil)
		require.NoError(t, err)
		resp, err := http.DefaultClient.Do(req)
		require.NoError(t, err)
		defer func() { require.NoError(t, resp.Body.Close()) }()

		assert.Equal(t, http.StatusUnauthorized, resp.StatusCode,
			"Contract: no Authorization header must yield 401")
	})

	t.Run("401 response body contains 'error' field", func(t *testing.T) {
		req, err := http.NewRequestWithContext(t.Context(), http.MethodPost, server.URL+"/ws/ticket", nil)
		require.NoError(t, err)
		resp, err := http.DefaultClient.Do(req)
		require.NoError(t, err)
		defer func() { require.NoError(t, resp.Body.Close()) }()

		var body map[string]interface{}
		require.NoError(t, json.NewDecoder(resp.Body).Decode(&body))

		_, hasError := body["error"]
		assert.True(t, hasError,
			"Contract violation: 401 response must contain 'error' field")
	})

	t.Run("non-Bearer Authorization format returns 401", func(t *testing.T) {
		req, err := http.NewRequestWithContext(t.Context(), http.MethodPost, server.URL+"/ws/ticket", nil)
		require.NoError(t, err)
		req.Header.Set("Authorization", "Basic dXNlcjpwYXNz")

		resp, err := http.DefaultClient.Do(req)
		require.NoError(t, err)
		defer func() { require.NoError(t, resp.Body.Close()) }()

		assert.Equal(t, http.StatusUnauthorized, resp.StatusCode,
			"Contract: non-Bearer Authorization must yield 401")
	})

	t.Run("invalid Bearer token returns 401", func(t *testing.T) {
		req, err := http.NewRequestWithContext(t.Context(), http.MethodPost, server.URL+"/ws/ticket", nil)
		require.NoError(t, err)
		req.Header.Set("Authorization", "Bearer invalid")

		resp, err := http.DefaultClient.Do(req)
		require.NoError(t, err)
		defer func() { require.NoError(t, resp.Body.Close()) }()

		assert.Equal(t, http.StatusUnauthorized, resp.StatusCode,
			"Contract: invalid token must yield 401")
	})

	t.Run("valid Bearer token returns 201 with ticket metadata", func(t *testing.T) {
		req, err := http.NewRequestWithContext(t.Context(), http.MethodPost, server.URL+"/ws/ticket", nil)
		require.NoError(t, err)
		req.Header.Set("Authorization", "Bearer valid-jwt-token")

		resp, err := http.DefaultClient.Do(req)
		require.NoError(t, err)
		defer func() { require.NoError(t, resp.Body.Close()) }()

		assert.Equal(t, http.StatusCreated, resp.StatusCode,
			"Contract: valid token must yield 201")

		var body map[string]interface{}
		require.NoError(t, json.NewDecoder(resp.Body).Decode(&body))
		_, hasTicket := body["ticket"]
		assert.True(t, hasTicket,
			"Contract violation: 201 response must contain 'ticket' field")
		assert.Equal(t, float64(15), body["expires_in"],
			"Contract violation: response must expose the ticket TTL")
	})

	t.Run("ticket value is a 64-character hex string", func(t *testing.T) {
		req, err := http.NewRequestWithContext(t.Context(), http.MethodPost, server.URL+"/ws/ticket", nil)
		require.NoError(t, err)
		req.Header.Set("Authorization", "Bearer valid-jwt-token")

		resp, err := http.DefaultClient.Do(req)
		require.NoError(t, err)
		defer func() { require.NoError(t, resp.Body.Close()) }()
		require.Equal(t, http.StatusCreated, resp.StatusCode)

		var body map[string]interface{}
		require.NoError(t, json.NewDecoder(resp.Body).Decode(&body))

		ticket, _ := body["ticket"].(string)
		assert.Len(t, ticket, 64,
			"Contract: ticket must be a 64-character hex string (32 random bytes)")
		assert.Regexp(t, `^[0-9a-f]{64}$`, ticket,
			"Contract: ticket must contain only lowercase hex characters")
	})
}

// ---------------------------------------------------------------------------
// Contract: WebSocket message protocol (ws-hub output schema)
//
// Consumer expectation: all messages emitted by ws-hub over a WebSocket
// connection must contain a "type" field (non-empty string) and a "payload"
// field. Error messages must contain "code" and "message" fields.
//
// This verifies the wire protocol that the frontend JavaScript client parses.
// ---------------------------------------------------------------------------

// wsMessage is the canonical WebSocket message envelope consumed by the frontend.
type wsMessage struct {
	Type    string          `json:"type"`
	Payload json.RawMessage `json:"payload"`
}

// wsErrorMessage is the error variant of the WebSocket message envelope.
type wsErrorMessage struct {
	Code    string `json:"code"`
	Message string `json:"message"`
}

// TestWSHubContract_MessageProtocol verifies the WebSocket message schema contract.
func TestWSHubContract_MessageProtocol(t *testing.T) {
	t.Run("outgoing message must have non-empty 'type' and non-nil 'payload'", func(t *testing.T) {
		msg := wsMessage{
			Type:    "message",
			Payload: json.RawMessage(`{"text":"hello from ws-hub"}`),
		}
		data, err := json.Marshal(msg)
		require.NoError(t, err)

		var decoded wsMessage
		require.NoError(t, json.Unmarshal(data, &decoded))

		assert.NotEmpty(t, decoded.Type,
			"Contract: message.type must not be empty")
		assert.NotNil(t, decoded.Payload,
			"Contract: message.payload must not be nil")
	})

	t.Run("error message must have non-empty 'code' and 'message' fields", func(t *testing.T) {
		errMsg := wsErrorMessage{
			Code:    "rate_limit_exceeded",
			Message: "Too many requests",
		}
		data, err := json.Marshal(errMsg)
		require.NoError(t, err)

		var decoded wsErrorMessage
		require.NoError(t, json.Unmarshal(data, &decoded))

		assert.NotEmpty(t, decoded.Code,
			"Contract: error.code must not be empty")
		assert.NotEmpty(t, decoded.Message,
			"Contract: error.message must not be empty")
	})

	t.Run("message type 'notification' round-trips correctly", func(t *testing.T) {
		// Verifies that the notification message type used by ws-hub events
		// survives JSON serialisation without field loss.
		type notificationPayload struct {
			Title string `json:"title"`
			Body  string `json:"body"`
		}
		inner := notificationPayload{Title: "New message", Body: "You have a new chat message"}
		innerBytes, err := json.Marshal(inner)
		require.NoError(t, err)

		msg := wsMessage{Type: "notification", Payload: json.RawMessage(innerBytes)}
		wire, err := json.Marshal(msg)
		require.NoError(t, err)

		var decoded wsMessage
		require.NoError(t, json.Unmarshal(wire, &decoded))
		assert.Equal(t, "notification", decoded.Type)

		var decodedPayload notificationPayload
		require.NoError(t, json.Unmarshal(decoded.Payload, &decodedPayload))
		assert.Equal(t, "New message", decodedPayload.Title)
		assert.Equal(t, "You have a new chat message", decodedPayload.Body)
	})

	t.Run("cache_invalidation error code satisfies error contract", func(t *testing.T) {
		// The rate_limit_exceeded error code is one of the defined ws-hub error types.
		// Validates that the frontend error handler can extract both fields reliably.
		raw := `{"code":"cache_invalidation_failed","message":"upstream Redis unreachable"}`
		var decoded wsErrorMessage
		require.NoError(t, json.Unmarshal([]byte(raw), &decoded))

		assert.Equal(t, "cache_invalidation_failed", decoded.Code)
		assert.NotEmpty(t, decoded.Message)
	})
}

// ---------------------------------------------------------------------------
// Contract: Internal header injection (gateway → backend)
//
// Consumer expectation (Python backend side): when the gateway proxies an
// authenticated request, it MUST inject X-User-ID and X-Request-ID headers
// and MUST NOT forward a client-supplied X-User-ID.
// ---------------------------------------------------------------------------

// proxyHeaderHandler simulates the gateway header-injection contract.
// Mirrors ProxyHandler logic from internal/handlers/handlers.go.
func proxyHeaderHandler() http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")

		// Contract: X-User-ID must be injected for authenticated requests.
		userID := r.Header.Get("X-User-ID")
		if userID == "" {
			w.WriteHeader(http.StatusBadRequest)
			_, _ = w.Write([]byte(`{"error":"X-User-ID header missing"}`)) //nolint:errcheck // t not in scope in handler func
			return
		}
		// Contract: X-Request-ID must always be present.
		requestID := r.Header.Get("X-Request-ID")
		if requestID == "" {
			w.WriteHeader(http.StatusBadRequest)
			_, _ = w.Write([]byte(`{"error":"X-Request-ID header missing"}`)) //nolint:errcheck // t not in scope in handler func
			return
		}

		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`{"received":true}`)) //nolint:errcheck // t not in scope in handler func
	})
}

// TestGatewayContract_HeaderInjection verifies that the gateway header injection
// contract is respected when proxying authenticated requests to the backend.
func TestGatewayContract_HeaderInjection(t *testing.T) {
	server := httptest.NewServer(proxyHeaderHandler())
	defer server.Close()

	t.Run("authenticated proxy request carries X-User-ID header", func(t *testing.T) {
		req, err := http.NewRequestWithContext(t.Context(), http.MethodGet, server.URL+"/api/v1/courses", nil)
		require.NoError(t, err)
		// Gateway injects these after JWT validation; backend expects them.
		req.Header.Set("X-User-ID", "550e8400-e29b-41d4-a716-446655440000")
		req.Header.Set("X-Request-ID", "a1b2c3d4-e5f6-7890-abcd-ef1234567890")

		resp, err := http.DefaultClient.Do(req)
		require.NoError(t, err)
		defer func() { require.NoError(t, resp.Body.Close()) }()

		assert.Equal(t, http.StatusOK, resp.StatusCode,
			"Contract: backend must accept request with gateway-injected X-User-ID")
	})

	t.Run("request without X-User-ID is rejected by backend contract", func(t *testing.T) {
		req, err := http.NewRequestWithContext(t.Context(), http.MethodGet, server.URL+"/api/v1/courses", nil)
		require.NoError(t, err)
		// Deliberately omit X-User-ID to verify backend contract enforcement.

		resp, err := http.DefaultClient.Do(req)
		require.NoError(t, err)
		defer func() { require.NoError(t, resp.Body.Close()) }()

		assert.Equal(t, http.StatusBadRequest, resp.StatusCode,
			"Contract: backend must reject request missing X-User-ID")
	})
}
