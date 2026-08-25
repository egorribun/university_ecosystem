import { PerformanceObserver as NodePerformanceObserver } from "node:perf_hooks"
import { describe, expect, it, vi } from "vitest"

describe("real browser telemetry instrumentations", () => {
  it("registers and enables the supported instrumentation set as one compatible toolchain", async () => {
    const originalPerformanceObserver = Object.getOwnPropertyDescriptor(
      globalThis,
      "PerformanceObserver"
    )
    Object.defineProperty(globalThis, "PerformanceObserver", {
      configurable: true,
      value: NodePerformanceObserver,
    })
    vi.resetModules()

    const [
      { registerInstrumentations },
      { FetchInstrumentation },
      { XMLHttpRequestInstrumentation },
      { UserInteractionInstrumentation },
    ] = await Promise.all([
      import("@opentelemetry/instrumentation"),
      import("@opentelemetry/instrumentation-fetch"),
      import("@opentelemetry/instrumentation-xml-http-request"),
      import("@opentelemetry/instrumentation-user-interaction"),
    ])
    const instrumentations = [
      new FetchInstrumentation({ enabled: false }),
      new XMLHttpRequestInstrumentation({ enabled: false }),
      new UserInteractionInstrumentation({ enabled: false, eventNames: ["click", "submit"] }),
    ]
    const originalFetch = globalThis.fetch
    const originalXhrOpen = XMLHttpRequest.prototype.open
    const originalXhrSend = XMLHttpRequest.prototype.send
    const originalPushState = history.pushState
    const originalReplaceState = history.replaceState
    let unregister: (() => void) | undefined

    try {
      expect(() => {
        unregister = registerInstrumentations({ instrumentations })
      }).not.toThrow()
      expect(globalThis.fetch).not.toBe(originalFetch)
      expect(XMLHttpRequest.prototype.open).not.toBe(originalXhrOpen)
      expect(history.pushState).not.toBe(originalPushState)
    } finally {
      unregister?.()
      globalThis.fetch = originalFetch
      XMLHttpRequest.prototype.open = originalXhrOpen
      XMLHttpRequest.prototype.send = originalXhrSend
      history.pushState = originalPushState
      history.replaceState = originalReplaceState
      expect(globalThis.fetch).toBe(originalFetch)
      expect(XMLHttpRequest.prototype.open).toBe(originalXhrOpen)
      expect(history.pushState).toBe(originalPushState)
      if (originalPerformanceObserver) {
        Object.defineProperty(globalThis, "PerformanceObserver", originalPerformanceObserver)
      } else {
        Reflect.deleteProperty(globalThis, "PerformanceObserver")
      }
      vi.resetModules()
    }
  })
})
