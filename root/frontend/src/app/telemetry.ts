import { WebTracerProvider } from "@opentelemetry/sdk-trace-web"
import { BatchSpanProcessor, SimpleSpanProcessor } from "@opentelemetry/sdk-trace-base"
import { OTLPTraceExporter } from "@opentelemetry/exporter-trace-otlp-http"
import { registerInstrumentations } from "@opentelemetry/instrumentation"
import { FetchInstrumentation } from "@opentelemetry/instrumentation-fetch"
import { XMLHttpRequestInstrumentation } from "@opentelemetry/instrumentation-xml-http-request"
import { Resource } from "@opentelemetry/resources"
import { ATTR_SERVICE_NAME, ATTR_SERVICE_VERSION } from "@opentelemetry/semantic-conventions"

let provider: WebTracerProvider | null = null

export function initTelemetry(env: ImportMetaEnv = import.meta.env) {
  if (provider) return

  const serviceName = env.VITE_OTEL_SERVICE_NAME || "university-ecosystem-frontend"
  const serviceVersion = env.VITE_SERVICE_VERSION || "1.0.0"
  const endpoint = env.VITE_OTEL_EXPORTER_OTLP_ENDPOINT || "http://localhost:4318/v1/traces"

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

  provider.addSpanProcessor(processor)
  provider.register()

  registerInstrumentations({
    instrumentations: [
      new FetchInstrumentation({
        propagateTraceHeaderCorsUrls: [
          new RegExp(`${env.VITE_BACKEND_ORIGIN || ""}/api/.*`),
          /^\/api\/.*/,
        ],
      }),
      new XMLHttpRequestInstrumentation({
        propagateTraceHeaderCorsUrls: [
          new RegExp(`${env.VITE_BACKEND_ORIGIN || ""}/api/.*`),
          /^\/api\/.*/,
        ],
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
