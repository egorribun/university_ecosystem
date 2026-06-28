package middleware

// Coverage tests (testing session 9) for the GraphQL depth middleware
// residual branches: GET pass-through, invalid-JSON 400, body restoration
// for downstream handlers, and the estimateQueryDepth heuristic table
// (strings with braces, escaped quotes, # comments, unbalanced braces).

import (
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestMaxQueryDepth_GETPassesThrough(t *testing.T) {
	called := false
	handler := MaxQueryDepthMiddleware(2, http.HandlerFunc(func(_ http.ResponseWriter, _ *http.Request) {
		called = true
	}))
	req := httptest.NewRequestWithContext(t.Context(), http.MethodGet, "/graphql?query={a{b{c{d}}}}", nil)
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	assert.True(t, called, "GET requests bypass depth estimation")
	assert.Equal(t, http.StatusOK, rec.Code)
}

func TestMaxQueryDepth_InvalidJSONRejected(t *testing.T) {
	handler := MaxQueryDepthMiddleware(2, http.HandlerFunc(func(_ http.ResponseWriter, _ *http.Request) {
		t.Fatal("downstream must not be called")
	}))
	req := httptest.NewRequestWithContext(t.Context(), http.MethodPost, "/graphql", strings.NewReader("{broken"))
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	assert.Equal(t, http.StatusBadRequest, rec.Code)
	assert.Contains(t, rec.Body.String(), "invalid request body")
}

func TestMaxQueryDepth_RestoresBodyForDownstream(t *testing.T) {
	body := `{"query":"{ health }","variables":{"x":1},"operationName":"Op"}`
	var downstreamBody string
	handler := MaxQueryDepthMiddleware(5, http.HandlerFunc(func(_ http.ResponseWriter, r *http.Request) {
		data, err := io.ReadAll(r.Body)
		require.NoError(t, err)
		downstreamBody = string(data)
	}))
	req := httptest.NewRequestWithContext(t.Context(), http.MethodPost, "/graphql", strings.NewReader(body))
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	assert.Equal(t, http.StatusOK, rec.Code)
	assert.Equal(t, body, downstreamBody, "variables/operationName must survive the middleware")
}

func TestEstimateQueryDepth_Table(t *testing.T) {
	cases := []struct {
		name  string
		query string
		want  int
	}{
		{"empty", "", 0},
		{"flat", "{ health }", 1},
		{"nested three", "{ a { b { c } } }", 3},
		{"braces inside string ignored", `{ a(filter: "{{{") { b } }`, 2},
		{"escaped quote inside string", `{ a(label: "say \"hi\" {x}") { b } }`, 2},
		{"line comment ignored", "{ a { b } } # trailing {{{{\n", 2},
		{"comment then code", "# header {{{\n{ a { b { c } } }", 3},
		{"unbalanced extra close", "{ a } } }", 1},
		{"sibling blocks keep max", "{ a { b } c { d { e } } }", 3},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			assert.Equal(t, tc.want, estimateQueryDepth(tc.query))
		})
	}
}

func TestRequestTimeout_ContextDeadlineApplied(t *testing.T) {
	var sawDeadline bool
	handler := RequestTimeoutMiddleware(50*time.Millisecond, http.HandlerFunc(func(_ http.ResponseWriter, r *http.Request) {
		_, sawDeadline = r.Context().Deadline()
	}))
	req := httptest.NewRequestWithContext(t.Context(), http.MethodPost, "/graphql", strings.NewReader("{}"))
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	assert.True(t, sawDeadline, "downstream context must carry a deadline")
}
