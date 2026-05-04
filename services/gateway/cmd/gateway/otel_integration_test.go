//go:build integration

package main

import (
	"net/http"
	"net/http/httptest"
	"testing"

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

	var capturedSpan trace.SpanContext
	var capturedBaggage string

	gin.SetMode(gin.TestMode)
	r := gin.New()
	r.Use(otelgin.Middleware("gateway-test"))
	r.GET("/echo", func(c *gin.Context) {
		capturedSpan = trace.SpanContextFromContext(c.Request.Context())
		b := baggage.FromContext(c.Request.Context())
		capturedBaggage = b.String()
		c.String(http.StatusOK, "ok")
	})

	server := httptest.NewServer(r)
	t.Cleanup(server.Close)

	// Send request with both W3C headers populated.
	req, err := http.NewRequest(http.MethodGet, server.URL+"/echo", nil)
	require.NoError(t, err)
	// W3C TraceContext spec example values — NOT secrets, just IDs that flow
	// through the propagator chain. pragma: allowlist secret
	req.Header.Set("traceparent", "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01") //nolint:gosec // pragma: allowlist secret
	req.Header.Set("baggage", "user_id=u-1,request_id=r-1")

	resp, err := http.DefaultClient.Do(req)
	require.NoError(t, err)
	defer resp.Body.Close()
	require.Equal(t, http.StatusOK, resp.StatusCode)

	// Assert TraceContext extraction: span context is valid, traceId matches.
	require.True(t, capturedSpan.IsValid(),
		"TraceContext header must be extracted into a valid SpanContext")
	require.Equal(t, "0af7651916cd43dd8448eb211c80319c", capturedSpan.TraceID().String(), //nolint:gosec // pragma: allowlist secret (W3C TraceContext spec example)
		"traceparent traceId must propagate end-to-end")
	require.Equal(t, "b7ad6b7169203331", capturedSpan.SpanID().String(), //nolint:gosec // pragma: allowlist secret
		"traceparent spanId must propagate end-to-end")

	// Assert Baggage extraction: both entries present in the captured string.
	require.Contains(t, capturedBaggage, "user_id=u-1",
		"Baggage user_id entry must be extracted (got: %q)", capturedBaggage)
	require.Contains(t, capturedBaggage, "request_id=r-1",
		"Baggage request_id entry must be extracted (got: %q)", capturedBaggage)
}
