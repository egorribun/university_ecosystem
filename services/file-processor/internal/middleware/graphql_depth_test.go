package middleware

import (
	"bytes"
	"io"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/stretchr/testify/assert"
)

func TestEstimateQueryDepth(t *testing.T) {
	tests := []struct {
		name  string
		query string
		want  int
	}{
		{"empty", "", 0},
		{"simple", "{ user { id } }", 2},
		{"nested", "{ user { id profile { name avatar { url } } } }", 4},
		{"braces in strings", `{ user(name: "{brackets}") { id } }`, 2},
		{"escaped quotes in strings", `{ user(note: "he said \"{depth}\"") { id } }`, 2},
		{"comments with braces", `{ 
			user { 
				id 
				# { ignored level }
				name
			} 
		}`, 2},
		{"multiple top level", "{ a { b } } { c { d { e } } }", 3},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			assert.Equal(t, tt.want, estimateQueryDepth(tt.query))
		})
	}
}

func TestMaxQueryDepthMiddleware(t *testing.T) {
	nextHandler := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		_, err := w.Write([]byte("OK"))
		assert.NoError(t, err)
	})

	handler := MaxQueryDepthMiddleware(3, nextHandler)

	t.Run("allowed depth", func(t *testing.T) {
		body := `{"query": "{ user { profile { name } } }"}`
		req := httptest.NewRequest(http.MethodPost, "/graphql", bytes.NewBufferString(body))
		rr := httptest.NewRecorder()

		handler.ServeHTTP(rr, req)

		assert.Equal(t, http.StatusOK, rr.Code)
		assert.Equal(t, "OK", rr.Body.String())
	})

	t.Run("exceeded depth", func(t *testing.T) {
		body := `{"query": "{ user { profile { avatar { url { original } } } } }"}`
		req := httptest.NewRequest(http.MethodPost, "/graphql", bytes.NewBufferString(body))
		rr := httptest.NewRecorder()

		handler.ServeHTTP(rr, req)

		assert.Equal(t, http.StatusBadRequest, rr.Code)
		assert.Contains(t, rr.Body.String(), "exceeds maximum allowed depth")
	})

	t.Run("pass variables", func(t *testing.T) {
		// Verify that body is restored correctly and includes variables
		body := `{"query": "query($id: ID!) { user(id: $id) { name } }", "variables": {"id": "123"}}`

		capturedBody := ""
		nextWithCapture := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			b, err := io.ReadAll(r.Body)
			assert.NoError(t, err)
			capturedBody = string(b)
			w.WriteHeader(http.StatusOK)
		})

		h := MaxQueryDepthMiddleware(5, nextWithCapture)
		req := httptest.NewRequest(http.MethodPost, "/graphql", bytes.NewBufferString(body))
		rr := httptest.NewRecorder()

		h.ServeHTTP(rr, req)

		assert.Equal(t, http.StatusOK, rr.Code)
		assert.Equal(t, body, capturedBody, "body should be preserved exactly as sent")
	})

	t.Run("non-post request", func(t *testing.T) {
		req := httptest.NewRequest(http.MethodGet, "/graphql", nil)
		rr := httptest.NewRecorder()

		handler.ServeHTTP(rr, req)

		assert.Equal(t, http.StatusOK, rr.Code)
	})

	t.Run("invalid json", func(t *testing.T) {
		body := `{"query": "{ user { id } }", invalid}`
		req := httptest.NewRequest(http.MethodPost, "/graphql", bytes.NewBufferString(body))
		rr := httptest.NewRecorder()

		handler.ServeHTTP(rr, req)

		assert.Equal(t, http.StatusBadRequest, rr.Code)
		assert.Contains(t, rr.Body.String(), "invalid request body")
	})
}
