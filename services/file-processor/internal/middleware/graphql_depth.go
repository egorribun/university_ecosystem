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

		// RZ-33-22: Read the full body once, extract only the "query" field for
		// depth estimation, then pass the original body through unchanged.
		// Previous code used DisallowUnknownFields (rejected valid requests with
		// "variables") and re-encoded only the Query field (dropped variables).
		bodyBytes, err := io.ReadAll(r.Body)
		if err != nil {
			http.Error(w, `{"errors":[{"message":"invalid request body"}]}`, http.StatusBadRequest)
			return
		}

		var req graphqlRequest
		if err := json.Unmarshal(bodyBytes, &req); err != nil {
			http.Error(w, `{"errors":[{"message":"invalid request body"}]}`, http.StatusBadRequest)
			return
		}

		depth := estimateQueryDepth(req.Query)
		if depth > maxDepth {
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(http.StatusBadRequest)
			response := struct {
				Errors []struct {
					Message string `json:"message"`
				} `json:"errors"`
			}{Errors: []struct {
				Message string `json:"message"`
			}{{Message: fmt.Sprintf("query depth %d exceeds maximum allowed depth of %d", depth, maxDepth)}}}
			_ = json.NewEncoder(w).Encode(response) //nolint:errcheck
			return
		}

		// Restore the original body for the downstream handler — preserves
		// variables, operationName, and extensions that were in the request.
		r.Body = io.NopCloser(bytes.NewReader(bodyBytes))
		r.ContentLength = int64(len(bodyBytes))

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
	escaped := false // RZ-26-05: track backslash escapes inside strings

	inComment := false // PERF-27-01: skip GraphQL # line comments
	for _, ch := range query {
		if escaped {
			escaped = false
			continue
		}
		// PERF-27-01: Skip # line comments (GraphQL spec section 2.1.2)
		if ch == '#' && !inString {
			inComment = true
			continue
		}
		if inComment {
			if ch == '\n' || ch == '\r' {
				inComment = false
			}
			continue
		}
		switch {
		case ch == '\\' && inString:
			escaped = true // RZ-26-05: skip next char (handles \" inside strings)
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
