import { PerformanceObserver as NodePerformanceObserver } from "node:perf_hooks"
import { context, SpanKind, trace } from "@opentelemetry/api"
import { describe, expect, it, vi } from "vitest"
import { captureActiveTelemetryContext } from "@/utils/telemetryContext"

function deferred(): { promise: Promise<void>; resolve: () => void } {
  let resolve!: () => void
  const promise = new Promise<void>((complete) => {
    resolve = complete
  })
  return { promise, resolve }
}

describe("explicit browser telemetry context propagation", () => {
  it("links fetch spans to concurrent interaction parents after await without context bleed", async () => {
    const originalPerformanceObserver = Object.getOwnPropertyDescriptor(
      globalThis,
      "PerformanceObserver"
    )
    Object.defineProperty(globalThis, "PerformanceObserver", {
      configurable: true,
      value: NodePerformanceObserver,
    })
    const originalFetch = globalThis.fetch
    const uninstrumentedFetch = vi.fn(async () => new Response(null, { status: 204 }))
    globalThis.fetch = uninstrumentedFetch

    const [traceBase, traceWeb, instrumentation, instrumentationFetch] = await Promise.all([
      import("@opentelemetry/sdk-trace-base"),
      import("@opentelemetry/sdk-trace-web"),
      import("@opentelemetry/instrumentation"),
      import("@opentelemetry/instrumentation-fetch"),
    ])
    context.disable()
    trace.disable()
    const exporter = new traceBase.InMemorySpanExporter()
    const provider = new traceWeb.WebTracerProvider({
      spanProcessors: [new traceBase.SimpleSpanProcessor(exporter)],
    })
    const contextManager = new traceWeb.StackContextManager().enable()
    provider.register({ contextManager })
    const unregister = instrumentation.registerInstrumentations({
      tracerProvider: provider,
      instrumentations: [
        new instrumentationFetch.FetchInstrumentation({
          propagateTraceHeaderCorsUrls: [/^http:\/\/localhost\/api\//],
        }),
      ],
    })
    const tracer = provider.getTracer("telemetry-context-integration")
    const firstRelease = deferred()
    const secondRelease = deferred()
    const observedAfterAwait: string[] = []

    const runInteraction = (name: string, release: Promise<void>, url: string): Promise<void> =>
      tracer.startActiveSpan(name, async (interactionSpan) => {
        const captured = captureActiveTelemetryContext()
        await release
        await captured.run(async () => {
          observedAfterAwait.push(trace.getSpan(context.active())?.spanContext().spanId ?? "")
          await fetch(url)
        })
        interactionSpan.end()
      })

    try {
      expect(globalThis.fetch).not.toBe(uninstrumentedFetch)
      const first = runInteraction(
        "interaction:first",
        firstRelease.promise,
        "http://localhost/api/first"
      )
      const second = runInteraction(
        "interaction:second",
        secondRelease.promise,
        "http://localhost/api/second"
      )
      secondRelease.resolve()
      await second
      firstRelease.resolve()
      await first
      await vi.waitFor(() => {
        expect(
          exporter.getFinishedSpans().filter((span) => span.kind === SpanKind.CLIENT)
        ).toHaveLength(2)
      })
      await provider.forceFlush()

      const spans = exporter.getFinishedSpans()
      const firstInteraction = spans.find((span) => span.name === "interaction:first")
      const secondInteraction = spans.find((span) => span.name === "interaction:second")
      const fetchSpans = spans.filter((span) => span.kind === SpanKind.CLIENT)

      expect(observedAfterAwait).toEqual([
        secondInteraction?.spanContext().spanId,
        firstInteraction?.spanContext().spanId,
      ])
      expect(fetchSpans).toHaveLength(2)
      expect(fetchSpans.map((span) => span.parentSpanContext?.spanId).sort()).toEqual(
        [firstInteraction?.spanContext().spanId, secondInteraction?.spanContext().spanId].sort()
      )
      expect(trace.getSpan(context.active())).toBeUndefined()
      expect(uninstrumentedFetch).toHaveBeenCalledTimes(2)
    } finally {
      unregister()
      await provider.shutdown()
      context.disable()
      trace.disable()
      globalThis.fetch = originalFetch
      if (originalPerformanceObserver) {
        Object.defineProperty(globalThis, "PerformanceObserver", originalPerformanceObserver)
      } else {
        Reflect.deleteProperty(globalThis, "PerformanceObserver")
      }
    }
  })
})
