//go:build integration

package main

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/stretchr/testify/require"
	"go.opentelemetry.io/contrib/instrumentation/github.com/gin-gonic/gin/otelgin"
	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/baggage"
	"go.opentelemetry.io/otel/propagation"
	"go.opentelemetry.io/otel/trace"
)

// TestIntegration_OTELCompositePropagator verifies MOD-31-02: the gateway
// registers a composite TextMapPropagator that combines W3C TraceContext +
// W3C Baggage. otelgin middleware uses the global propagator to extract
// inbound `traceparent` + `baggage` headers and stash them in the request
// context.
//
// Production wiring at cmd/gateway/main.go:386-391:
//
//	otel.SetTextMapPropagator(propagation.NewCompositeTextMapPropagator(
//	    propagation.TraceContext{},
//	    propagation.Baggage{},
//	))
//
// otelgin.Middleware("gateway") then injects/extracts on every inbound
// request. This test:
//   - Configures the same propagator
//   - Mounts otelgin middleware on a httptest server
//   - Sends a request with both headers set
//   - Asserts the handler context carries the trace span + baggage entries
//
// No external services required.
func TestIntegration_OTELCompositePropagator(t *testing.T) {
	// Set composite propagator (matches main.go:386-391 setup).
	prevPropagator := otel.GetTextMapPropagator()
	t.Cleanup(func() { otel.SetTextMapPropagator(prevPropagator) })
	otel.SetTextMapPropagator(propagation.NewCompositeTextMapPropagator(
		propagation.TraceContext{},
		propagation.Baggage{},
	))

	// Channel-based capture handoff from handler goroutine to test goroutine
	// — race-safe by Go memory model (channel send happens-before receive).
	// A plain `var capturedSpan ... ; var capturedBaggage string` shared
	// between handler + test goroutine is a data race that `go test -race`
	// would flag (writer in net/http server goroutine, reader in test
	// goroutine, no explicit synchronization on heap memory).
	type captured struct {
		span    trace.SpanContext
		baggage string
	}
	captureCh := make(chan captured, 1)

	gin.SetMode(gin.TestMode)
	r := gin.New()
	r.Use(otelgin.Middleware("gateway-test"))
	r.GET("/echo", func(c *gin.Context) {
		select {
		case captureCh <- captured{
			span:    trace.SpanContextFromContext(c.Request.Context()),
			baggage: baggage.FromContext(c.Request.Context()).String(),
		}:
		default:
			// Single-request test; additional captures drop without blocking.
		}
		c.String(http.StatusOK, "ok")
	})

	server := httptest.NewServer(r)
	t.Cleanup(server.Close)

	// Send request with both W3C headers populated.
	req, err := http.NewRequestWithContext(context.Background(), http.MethodGet, server.URL+"/echo", nil)
	require.NoError(t, err)
	// W3C TraceContext spec example values — NOT secrets, just IDs that flow
	// through the propagator chain. pragma: allowlist secret
	req.Header.Set("traceparent", "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01") //nolint:gosec // pragma: allowlist secret
	req.Header.Set("baggage", "user_id=u-1,request_id=r-1")

	resp, err := http.DefaultClient.Do(req)
	require.NoError(t, err)
	defer func() { _ = resp.Body.Close() }() //nolint:errcheck // best-effort body close
	require.Equal(t, http.StatusOK, resp.StatusCode)

	// Receive the captured trace + baggage. Channel ops provide happens-before
	// synchronization between the handler write and the test read.
	var got captured
	select {
	case got = <-captureCh:
	case <-time.After(1 * time.Second):
		t.Fatal("handler never sent capture (otelgin middleware may not have run)")
	}

	// Assert TraceContext extraction: span context is valid, traceId matches.
	require.True(t, got.span.IsValid(),
		"TraceContext header must be extracted into a valid SpanContext")
	require.Equal(t, "0af7651916cd43dd8448eb211c80319c", got.span.TraceID().String(), //nolint:gosec // pragma: allowlist secret (W3C TraceContext spec example)
		"traceparent traceId must propagate end-to-end")
	require.Equal(t, "b7ad6b7169203331", got.span.SpanID().String(), //nolint:gosec // pragma: allowlist secret
		"traceparent spanId must propagate end-to-end")

	// Assert Baggage extraction: both entries present in the captured string.
	require.Contains(t, got.baggage, "user_id=u-1",
		"Baggage user_id entry must be extracted (got: %q)", got.baggage)
	require.Contains(t, got.baggage, "request_id=r-1",
		"Baggage request_id entry must be extracted (got: %q)", got.baggage)
}
