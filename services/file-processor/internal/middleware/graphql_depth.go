// Package middleware provides HTTP middleware for the file-processor GraphQL API.
package middleware

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"time"
)

// graphqlRequest represents a parsed GraphQL HTTP request body.
type graphqlRequest struct {
	Query string `json:"query"`
}

// MaxQueryDepthMiddleware rejects GraphQL queries exceeding the given depth.
// RZ-24-05: Parity with Python backend's QueryDepthLimiter defense layer.
func MaxQueryDepthMiddleware(maxDepth int, next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			next.ServeHTTP(w, r)
			return
		}

		// Parse the request body to extract the query
		var req graphqlRequest
		decoder := json.NewDecoder(r.Body)
		decoder.DisallowUnknownFields()
		if err := decoder.Decode(&req); err != nil {
			http.Error(w, `{"errors":[{"message":"invalid request body"}]}`, http.StatusBadRequest)
			return
		}

		depth := estimateQueryDepth(req.Query)
		if depth > maxDepth {
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(http.StatusBadRequest)
			fmt.Fprintf(w, `{"errors":[{"message":"query depth %d exceeds maximum allowed depth of %d"}]}`, depth, maxDepth)
			return
		}

		// Re-encode body for downstream handler since we consumed it
		body, _ := json.Marshal(req)
		r.Body = io.NopCloser(bytes.NewReader(body))
		r.ContentLength = int64(len(body))

		next.ServeHTTP(w, r)
	})
}

// estimateQueryDepth estimates the nesting depth of a GraphQL query
// by counting brace nesting levels. This is a lightweight heuristic
// that avoids the overhead of full AST parsing.
func estimateQueryDepth(query string) int {
	maxDepth := 0
	currentDepth := 0
	inString := false

	for _, ch := range query {
		switch {
		case ch == '"':
			inString = !inString
		case inString:
			continue
		case ch == '{':
			currentDepth++
			if currentDepth > maxDepth {
				maxDepth = currentDepth
			}
		case ch == '}':
			currentDepth--
		}
	}
	return maxDepth
}

// RequestTimeoutMiddleware applies a hard deadline to GraphQL requests.
// RZ-24-05: Prevents long-running queries from consuming server resources.
func RequestTimeoutMiddleware(timeout time.Duration, next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		ctx, cancel := context.WithTimeout(r.Context(), timeout)
		defer cancel()
		next.ServeHTTP(w, r.WithContext(ctx))
	})
}
