import { WebTracerProvider, type SpanProcessor } from "@opentelemetry/sdk-trace-web"
import { BatchSpanProcessor, SimpleSpanProcessor } from "@opentelemetry/sdk-trace-base"
import { OTLPTraceExporter } from "@opentelemetry/exporter-trace-otlp-http"
import { registerInstrumentations } from "@opentelemetry/instrumentation"
import { FetchInstrumentation } from "@opentelemetry/instrumentation-fetch"
import { XMLHttpRequestInstrumentation } from "@opentelemetry/instrumentation-xml-http-request"
import { UserInteractionInstrumentation } from "@opentelemetry/instrumentation-user-interaction"
import { ZoneContextManager } from "@opentelemetry/context-zone"
import { Resource } from "@opentelemetry/resources"
import { ATTR_SERVICE_NAME, ATTR_SERVICE_VERSION } from "@opentelemetry/semantic-conventions"

let provider: WebTracerProvider | null = null

export function initTelemetry(env: ImportMetaEnv = import.meta.env) {
  if (provider) return

  const serviceName = env.VITE_OTEL_SERVICE_NAME || "university-ecosystem-frontend"
  const serviceVersion = env.VITE_SERVICE_VERSION || "1.0.0"

  // Only provide a localhost fallback in development mode.
  // Production MUST strictly use the configured endpoint.
  const defaultEndpoint = env.DEV ? "http://localhost:4318/v1/traces" : ""
  const endpoint = env.VITE_OTEL_EXPORTER_OTLP_ENDPOINT || defaultEndpoint

  if (!endpoint && !env.DEV) {
    // Silently disable telemetry if no endpoint is configured in production
    return
  }

  provider = new WebTracerProvider({
    resource: new Resource({
      [ATTR_SERVICE_NAME]: serviceName,
      [ATTR_SERVICE_VERSION]: serviceVersion,
    }),
  })

  const exporter = new OTLPTraceExporter({
    url: endpoint,
  })

  const processor = env.DEV ? new SimpleSpanProcessor(exporter) : new BatchSpanProcessor(exporter)

  provider.addSpanProcessor(processor as unknown as SpanProcessor)

  // ZoneContextManager propagates trace context across async boundaries
  // (Promise chains, setTimeout, etc.) using Zone.js.  Without it, a span
  // created on a button click is lost before the resulting fetch completes,
  // breaking the frontend → gateway correlation in Grafana Tempo.
  provider.register({ contextManager: new ZoneContextManager() })

  registerInstrumentations({
    instrumentations: [
      new FetchInstrumentation({
        propagateTraceHeaderCorsUrls: [
          // eslint-disable-next-line security/detect-non-literal-regexp -- pattern is derived from build-time env, not user input
          new RegExp(`${env.VITE_BACKEND_ORIGIN || ""}/api/.*`),
          /^\/api\/.*/,
        ],
      }),
      new XMLHttpRequestInstrumentation({
        propagateTraceHeaderCorsUrls: [
          // eslint-disable-next-line security/detect-non-literal-regexp -- pattern is derived from build-time env, not user input
          new RegExp(`${env.VITE_BACKEND_ORIGIN || ""}/api/.*`),
          /^\/api\/.*/,
        ],
      }),
      // UserInteractionInstrumentation automatically creates spans for
      // click and submit events, giving Tempo a root span for each user
      // action that triggered an API call.  The shouldPreventSpanCreation
      // guard avoids noise from internal library clicks (e.g. Radix UI).
      new UserInteractionInstrumentation({
        eventNames: ["click", "submit"],
        shouldPreventSpanCreation: (_eventType, element) => {
          // Skip instrumentation for elements explicitly marked as internal
          return element.getAttribute("data-no-trace") === "true"
        },
      }),
    ],
  })
}

export function getTracer(name: string = "frontend") {
  if (!provider) {
    throw new Error("Telemetry not initialized. Call initTelemetry first.")
  }
  return provider.getTracer(name)
}
