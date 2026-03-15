package telemetry

import (
	"context"

	"github.com/university-ecosystem/ws-hub/pkg/config"

	"github.com/getsentry/sentry-go"
	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracegrpc"
	"go.opentelemetry.io/otel/sdk/resource"
	sdktrace "go.opentelemetry.io/otel/sdk/trace"
	semconv "go.opentelemetry.io/otel/semconv/v1.17.0"
)

func InitSentry(cfg *config.Config) error {
	if cfg.SentryDSN == "" {
		return nil
	}
	return sentry.Init(sentry.ClientOptions{
		Dsn:              cfg.SentryDSN,
		Environment:      cfg.Environment,
		Release:          "ws-hub@1.0.0",
		TracesSampleRate: 1.0,
	})
}

func InitTracer(ctx context.Context, cfg *config.Config) (*sdktrace.TracerProvider, error) {
	// MOD-01 (audit 2026-03-15 Wave 7): Use OTel SDK env-based config instead
	// of hardcoded endpoint + insecure flag.  The SDK automatically reads:
	//   OTEL_EXPORTER_OTLP_ENDPOINT  — collector address (default: localhost:4317)
	//   OTEL_EXPORTER_OTLP_INSECURE  — "true" for local dev, omit for prod (TLS)
	//   OTEL_EXPORTER_OTLP_CERTIFICATE — optional CA bundle path
	// This eliminates the hardcoded "jaeger:4317" and removes the blanket
	// WithInsecure() that was sending traces in plaintext in production.
	exporter, err := otlptracegrpc.New(ctx)
	if err != nil {
		return nil, err
	}

	res, err := resource.New(ctx,
		resource.WithAttributes(
			semconv.ServiceNameKey.String("ws-hub"),
			attribute.String("environment", cfg.Environment),
		),
	)
	if err != nil {
		return nil, err
	}

	// ParentBased sampler respects the sampling decision propagated from
	// upstream services via NATS/HTTP headers.  For root spans (no parent),
	// TraceIDRatioBased(0.01) samples 1% — sufficient for capacity planning
	// and P99 latency tracking at high fan-out without Jaeger write amplification.
	// broadcastMessage creates one span per NATS message; at 1000 msg/s in a
	// popular room this would generate ~1000 spans/s without sampling.
	// (PERF-3: audit 2026-02-24)
	sampler := sdktrace.ParentBased(sdktrace.TraceIDRatioBased(0.01))

	tp := sdktrace.NewTracerProvider(
		sdktrace.WithBatcher(exporter),
		sdktrace.WithResource(res),
		sdktrace.WithSampler(sampler),
	)
	otel.SetTracerProvider(tp)
	return tp, nil
}

