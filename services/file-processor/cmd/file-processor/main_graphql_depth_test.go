package main

import (
	"context"
	"fmt"
	"strings"
	"testing"

	"github.com/graph-gophers/graphql-go"
	"github.com/stretchr/testify/require"
	"github.com/university-ecosystem/file-processor/internal/config"
)

func TestGraphQLServerEnforcesExpandedFragmentDepth(t *testing.T) {
	useRepositoryGraphQLSchema(t)
	oldParse := parseGraphQLSchemaFunc
	t.Cleanup(func() { parseGraphQLSchemaFunc = oldParse })
	var schema *graphql.Schema
	// Capture the actual schema built by production bootstrap, preserving all
	// supplied options and the real parser/resolver. No validation is mocked.
	parseGraphQLSchemaFunc = func(source string, resolver interface{}, opts ...graphql.SchemaOpt) (*graphql.Schema, error) {
		parsed, err := oldParse(source, resolver, opts...)
		schema = parsed
		return parsed, err
	}
	_, err := setupGraphQLServer(context.Background(), &config.Config{
		Environment: "development",
		GraphQLPort: "0",
		JWTSecret:   "test-secret",
	}, nil, nil, discardLogger())
	require.NoError(t, err)
	require.NotNil(t, schema)

	for _, depth := range []int{9, 10, 11, 20} {
		t.Run(fmt.Sprintf("depth_%d", depth), func(t *testing.T) {
			// Every definition has at most two nested braces. The lexical
			// middleware therefore cannot detect the expanded field depth.
			response := schema.Exec(context.Background(), fragmentDepthQuery(depth), "", nil)
			if depth <= 10 {
				require.Empty(t, response.Errors)
				require.NotEmpty(t, response.Data)
				return
			}
			require.NotEmpty(t, response.Errors)
			require.Equal(t, "MaxDepthExceeded", response.Errors[0].Rule)
			require.Empty(t, response.Data)
		})
	}
	response := schema.Exec(context.Background(), "{ health }", "", nil)
	require.Empty(t, response.Errors)
	require.JSONEq(t, `{"health":"OK"}`, string(response.Data))
}

// __type is depth 1; each ofType field adds one; name is the final field.
// The schema's real introspection types provide recursion without adding a
// test-only resolver or changing the application's deliberately shallow API.
func fragmentDepthQuery(depth int) string {
	var query strings.Builder
	query.WriteString(`query { __type(name: "Query") { ...D0 } } `)
	for index := 0; index < depth-2; index++ {
		fmt.Fprintf(&query, "fragment D%d on __Type { ofType { ...D%d } } ", index, index+1)
	}
	fmt.Fprintf(&query, "fragment D%d on __Type { name }", depth-2)
	return query.String()
}
