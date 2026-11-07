package middleware

// Coverage tests (testing session 9) for the GraphQL depth middleware
// residual branches: unsupported methods rejected, including OPTIONS,
// invalid-JSON 400, bounded body reads, body restoration for downstream
// handlers, and the estimateQueryDepth heuristic table.

import (
	"fmt"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	gql "github.com/graph-gophers/graphql-go"
	"github.com/graph-gophers/graphql-go/relay"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestMaxQueryDepth_RejectsUnsupportedMethods(t *testing.T) {
	cases := []struct {
		name   string
		method string
		target string
	}{
		{"GET with deep query", http.MethodGet, "/graphql?query={a{b{c{d}}}}"},
		{"HEAD", http.MethodHead, "/graphql"},
		{"PUT", http.MethodPut, "/graphql"},
		{"DELETE", http.MethodDelete, "/graphql"},
		{"PATCH", http.MethodPatch, "/graphql"},
		{"OPTIONS with deep GraphQL body", http.MethodOptions, "/graphql"},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			bodyContent := "must not be read"
			if tc.method == http.MethodOptions {
				bodyContent = `{"query":"{ a { b { c { d } } } }"}`
			}
			body := newTrackedRequestBody(bodyContent)
			called := false
			handler := MaxQueryDepthMiddleware(2, http.HandlerFunc(func(_ http.ResponseWriter, _ *http.Request) {
				called = true
			}))
			req := httptest.NewRequestWithContext(t.Context(), tc.method, tc.target, nil)
			req.Body = body
			rec := httptest.NewRecorder()

			handler.ServeHTTP(rec, req)

			assert.False(t, called, "unsupported methods must not reach the relay handler")
			assert.Equal(t, http.StatusMethodNotAllowed, rec.Code)
			assert.Equal(t, "POST", rec.Header().Get("Allow"))
			assert.Equal(t, "text/plain; charset=utf-8", rec.Header().Get("Content-Type"))
			assert.Zero(t, body.bytesRead, "unsupported request bodies must not be consumed")
			assert.True(t, body.closed, "request body must be closed on rejection")
		})
	}
}

type optionsRelayRootResolver struct{ called *bool }

func (r *optionsRelayRootResolver) A() *optionsRelayAResolver {
	*r.called = true
	return &optionsRelayAResolver{}
}

type optionsRelayAResolver struct{}

func (*optionsRelayAResolver) B() *optionsRelayBResolver { return &optionsRelayBResolver{} }

type optionsRelayBResolver struct{}

func (*optionsRelayBResolver) C() *optionsRelayCResolver { return &optionsRelayCResolver{} }

type optionsRelayCResolver struct{}

func (*optionsRelayCResolver) Value() string { return "ok" }

func TestMaxQueryDepth_OPTIONSCannotReadOrExecuteRelayBody(t *testing.T) {
	var resolverCalled bool
	schema, err := gql.ParseSchema(`
		type Query { a: OptionsRelayA! }
		type OptionsRelayA { b: OptionsRelayB! }
		type OptionsRelayB { c: OptionsRelayC! }
		type OptionsRelayC { value: String! }
	`, &optionsRelayRootResolver{called: &resolverCalled})
	require.NoError(t, err)

	bodyContent := `{"query":"{ a { b { c { value } } } }","padding":"` + strings.Repeat("x", maxGraphQLBodyBytes) + `"}`
	body := newTrackedRequestBody(bodyContent)
	handler := MaxQueryDepthMiddleware(2,
		RequestTimeoutMiddleware(time.Second, &relay.Handler{Schema: schema}),
	)
	request := httptest.NewRequestWithContext(t.Context(), http.MethodOptions, "/graphql", nil)
	request.Body = body
	recorder := httptest.NewRecorder()

	handler.ServeHTTP(recorder, request)

	assert.Equal(t, http.StatusMethodNotAllowed, recorder.Code)
	assert.Equal(t, "POST", recorder.Header().Get("Allow"))
	assert.Zero(t, body.bytesRead, "OPTIONS body must not be read by the relay")
	assert.True(t, body.closed, "rejected OPTIONS body must be closed")
	assert.False(t, resolverCalled, "OPTIONS must never execute the GraphQL schema")
}

type trackedRequestBody struct {
	reader    *strings.Reader
	bytesRead int
	closed    bool
	closeErr  error
}

func newTrackedRequestBody(body string) *trackedRequestBody {
	return &trackedRequestBody{reader: strings.NewReader(body)}
}

func (b *trackedRequestBody) Read(p []byte) (int, error) {
	n, err := b.reader.Read(p)
	b.bytesRead += n
	return n, err
}

func (b *trackedRequestBody) Close() error {
	b.closed = true
	return b.closeErr
}

func TestMaxQueryDepth_CloseErrorDoesNotReplaceHandlerResponse(t *testing.T) {
	body := newTrackedRequestBody(`{"query":"{ health }"}`)
	body.closeErr = io.ErrClosedPipe
	handler := MaxQueryDepthMiddleware(2, http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusNoContent)
	}))
	request := httptest.NewRequestWithContext(t.Context(), http.MethodPost, "/graphql", nil)
	request.Body = body
	recorder := httptest.NewRecorder()

	handler.ServeHTTP(recorder, request)

	assert.Equal(t, http.StatusNoContent, recorder.Code)
	assert.True(t, body.closed, "the original request body must still be closed")
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
	requestBody := newTrackedRequestBody(body)
	var downstreamBody string
	var downstreamContentType string
	var downstreamContentLength int64
	handler := MaxQueryDepthMiddleware(5, http.HandlerFunc(func(_ http.ResponseWriter, r *http.Request) {
		downstreamContentType = r.Header.Get("Content-Type")
		downstreamContentLength = r.ContentLength
		data, err := io.ReadAll(r.Body)
		require.NoError(t, err)
		downstreamBody = string(data)
	}))
	req := httptest.NewRequestWithContext(t.Context(), http.MethodPost, "/graphql", nil)
	req.Body = requestBody
	req.ContentLength = int64(len(body))
	req.Header.Set("Content-Type", "application/json")
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	assert.Equal(t, http.StatusOK, rec.Code)
	assert.Equal(t, body, downstreamBody, "variables/operationName must survive the middleware")
	assert.Equal(t, "application/json", downstreamContentType)
	assert.Equal(t, int64(len(body)), downstreamContentLength)
	assert.True(t, requestBody.closed, "original request body must be closed after inspection")
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

type errorReader struct{}

func (errorReader) Read(p []byte) (n int, err error) {
	return 0, fmt.Errorf("read error")
}

func TestMaxQueryDepth_BodyReadError(t *testing.T) {
	handler := MaxQueryDepthMiddleware(2, http.HandlerFunc(func(_ http.ResponseWriter, _ *http.Request) {
		t.Fatal("downstream must not be called")
	}))
	req := httptest.NewRequestWithContext(t.Context(), http.MethodPost, "/graphql", errorReader{})
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	assert.Equal(t, http.StatusBadRequest, rec.Code)
	assert.Contains(t, rec.Body.String(), "invalid request body")
}

func TestMaxQueryDepth_OversizedBodyRejected(t *testing.T) {
	called := false
	handler := MaxQueryDepthMiddleware(2, http.HandlerFunc(func(_ http.ResponseWriter, _ *http.Request) {
		called = true
	}))
	requestBody := newTrackedRequestBody(strings.Repeat("x", maxGraphQLBodyBytes+100))
	req := httptest.NewRequestWithContext(t.Context(), http.MethodPost, "/graphql", nil)
	req.Body = requestBody
	rec := httptest.NewRecorder()

	handler.ServeHTTP(rec, req)

	assert.Equal(t, http.StatusRequestEntityTooLarge, rec.Code)
	assert.Equal(t, "text/plain; charset=utf-8", rec.Header().Get("Content-Type"))
	assert.False(t, called)
	assert.Equal(t, maxGraphQLBodyBytes+1, requestBody.bytesRead, "oversized body reads must stop after one byte past the cap")
	assert.True(t, requestBody.closed, "oversized request body must be closed")
}
