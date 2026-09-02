import { StackContextManager, WebTracerProvider } from "@opentelemetry/sdk-trace-web"
import { BatchSpanProcessor, SimpleSpanProcessor } from "@opentelemetry/sdk-trace-base"
import { OTLPTraceExporter } from "@opentelemetry/exporter-trace-otlp-http"
import { registerInstrumentations } from "@opentelemetry/instrumentation"
import { FetchInstrumentation } from "@opentelemetry/instrumentation-fetch"
import { XMLHttpRequestInstrumentation } from "@opentelemetry/instrumentation-xml-http-request"
import { UserInteractionInstrumentation } from "@opentelemetry/instrumentation-user-interaction"
import { resourceFromAttributes } from "@opentelemetry/resources"
import { ATTR_SERVICE_NAME, ATTR_SERVICE_VERSION } from "@opentelemetry/semantic-conventions"

let provider: WebTracerProvider | null = null

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")
}

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

  const exporter = new OTLPTraceExporter({
    url: endpoint,
  })

  const processor = env.DEV ? new SimpleSpanProcessor(exporter) : new BatchSpanProcessor(exporter)

  provider = new WebTracerProvider({
    resource: resourceFromAttributes({
      [ATTR_SERVICE_NAME]: serviceName,
      [ATTR_SERVICE_VERSION]: serviceVersion,
    }),
    spanProcessors: [processor],
  })

  // StackContextManager deliberately avoids Zone.js monkey-patching. Zone's
  // Promise/IndexedDB patches make Dexie transactions commit before RxDB's
  // async collection setup finishes in Chromium (`PrematureCommitError`).
  // StackContextManager is synchronous: handlers that await before starting a
  // later API operation must capture and explicitly re-enter their interaction
  // context with captureActiveTelemetryContext().
  provider.register({ contextManager: new StackContextManager() })

  const backendOrigin = (env.VITE_BACKEND_ORIGIN || "").replace(/\/+$/, "")
  // Keep the relative API target as one canonical expression.  When an
  // absolute backend origin is configured we still include this same-origin
  // target for server-relative requests, but do not duplicate its literal in
  // the fallback branch.
  const sameOriginApiPattern = new RegExp("^/api/")
  const backendApiPattern = backendOrigin
    ? // Build-time origin is escaped so regex metacharacters stay literal.
      // eslint-disable-next-line security/detect-non-literal-regexp -- OpenTelemetry accepts only string or RegExp targets; the origin is escaped above and regression-tested.
      new RegExp(`^${escapeRegExp(backendOrigin)}/api/`) // nosemgrep: javascript.lang.security.audit.detect-non-literal-regexp.detect-non-literal-regexp
    : sameOriginApiPattern
  const traceHeaderTargets = backendOrigin
    ? [backendApiPattern, sameOriginApiPattern]
    : [backendApiPattern]

  registerInstrumentations({
    instrumentations: [
      new FetchInstrumentation({
        propagateTraceHeaderCorsUrls: traceHeaderTargets,
      }),
      new XMLHttpRequestInstrumentation({
        propagateTraceHeaderCorsUrls: traceHeaderTargets,
      }),
      // UserInteractionInstrumentation automatically creates spans for
      // click and submit events, giving Tempo a root span for each user
      // action that triggered an API call.  The shouldPreventSpanCreation
      // guard avoids noise from internal library clicks (e.g. Radix UI).
      new UserInteractionInstrumentation({
        eventNames: ["click", "submit"],
        shouldPreventSpanCreation: (_eventType: string, element: Element) => {
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
