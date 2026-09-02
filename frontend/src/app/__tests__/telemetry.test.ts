import { beforeEach, describe, expect, it, vi } from "vitest"

type ProviderDouble = {
  register: ReturnType<typeof vi.fn>
  getTracer: ReturnType<typeof vi.fn>
}

const mocks = vi.hoisted(() => ({
  providers: [] as ProviderDouble[],
  providerOptions: [] as unknown[],
  exporters: [] as Array<{ url?: string }>,
  processors: [] as Array<{ kind: "simple" | "batch"; exporter: unknown }>,
  fetchOptions: [] as unknown[],
  xhrOptions: [] as unknown[],
  interactionOptions: [] as Array<{
    shouldPreventSpanCreation: (eventType: string, element: Element) => boolean
  }>,
  registerInstrumentations: vi.fn(),
  resourceFromAttributes: vi.fn((attributes: unknown) => ({ attributes })),
}))

vi.mock("@opentelemetry/sdk-trace-web", () => ({
  StackContextManager: class {
    readonly kind = "stack"
  },
  WebTracerProvider: class {
    register = vi.fn()
    getTracer = vi.fn((name: string) => ({ name }))

    constructor(options: unknown) {
      mocks.providers.push(this)
      mocks.providerOptions.push(options)
    }
  },
}))

vi.mock("@opentelemetry/sdk-trace-base", () => ({
  SimpleSpanProcessor: class {
    constructor(exporter: unknown) {
      mocks.processors.push({ kind: "simple", exporter })
    }
  },
  BatchSpanProcessor: class {
    constructor(exporter: unknown) {
      mocks.processors.push({ kind: "batch", exporter })
    }
  },
}))

vi.mock("@opentelemetry/exporter-trace-otlp-http", () => ({
  OTLPTraceExporter: class {
    constructor(options: { url?: string }) {
      mocks.exporters.push(options)
    }
  },
}))

vi.mock("@opentelemetry/instrumentation", () => ({
  registerInstrumentations: mocks.registerInstrumentations,
}))
vi.mock("@opentelemetry/instrumentation-fetch", () => ({
  FetchInstrumentation: class {
    constructor(options: unknown) {
      mocks.fetchOptions.push(options)
    }
  },
}))
vi.mock("@opentelemetry/instrumentation-xml-http-request", () => ({
  XMLHttpRequestInstrumentation: class {
    constructor(options: unknown) {
      mocks.xhrOptions.push(options)
    }
  },
}))
vi.mock("@opentelemetry/instrumentation-user-interaction", () => ({
  UserInteractionInstrumentation: class {
    constructor(options: (typeof mocks.interactionOptions)[number]) {
      mocks.interactionOptions.push(options)
    }
  },
}))
vi.mock("@opentelemetry/resources", () => ({
  resourceFromAttributes: mocks.resourceFromAttributes,
}))
vi.mock("@opentelemetry/semantic-conventions", () => ({
  ATTR_SERVICE_NAME: "service.name",
  ATTR_SERVICE_VERSION: "service.version",
}))

const loadTelemetry = () => import("@/app/telemetry")

describe("frontend telemetry", () => {
  beforeEach(() => {
    vi.resetModules()
    mocks.providers.length = 0
    mocks.providerOptions.length = 0
    mocks.exporters.length = 0
    mocks.processors.length = 0
    mocks.fetchOptions.length = 0
    mocks.xhrOptions.length = 0
    mocks.interactionOptions.length = 0
    mocks.registerInstrumentations.mockReset()
    mocks.resourceFromAttributes.mockClear()
  })

  it("stays disabled in production without an explicit endpoint", async () => {
    const { getTracer, initTelemetry } = await loadTelemetry()

    initTelemetry({ DEV: false } as ImportMetaEnv)

    expect(mocks.providers).toHaveLength(0)
    expect(() => getTracer()).toThrow("Telemetry not initialized. Call initTelemetry first.")
  })

  it("initializes development tracing with safe defaults and trace filters", async () => {
    const { getTracer, initTelemetry } = await loadTelemetry()
    const env = { DEV: true } as ImportMetaEnv

    initTelemetry(env)

    expect(mocks.exporters).toEqual([{ url: "http://localhost:4318/v1/traces" }])
    expect(mocks.processors[0]?.kind).toBe("simple")
    expect(mocks.resourceFromAttributes).toHaveBeenCalledWith({
      "service.name": "university-ecosystem-frontend",
      "service.version": "1.0.0",
    })
    expect(mocks.providerOptions[0]).toEqual(
      expect.objectContaining({
        spanProcessors: [expect.any(Object)],
      })
    )
    expect(mocks.providers[0]?.register).toHaveBeenCalledOnce()
    expect(mocks.providers[0]?.register).toHaveBeenCalledWith({
      contextManager: { kind: "stack" },
    })
    expect(mocks.registerInstrumentations).toHaveBeenCalledOnce()

    const filter = mocks.interactionOptions[0]?.shouldPreventSpanCreation
    const internal = document.createElement("button")
    internal.setAttribute("data-no-trace", "true")
    expect(filter?.("click", internal)).toBe(true)
    expect(filter?.("submit", document.createElement("form"))).toBe(false)
    expect(mocks.interactionOptions[0]).toEqual(
      expect.objectContaining({ eventNames: ["click", "submit"] })
    )

    expect(getTracer()).toEqual({ name: "frontend" })
    initTelemetry(env)
    expect(mocks.providers).toHaveLength(1)
  })

  it("uses production batching and configured resource attributes", async () => {
    const { getTracer, initTelemetry } = await loadTelemetry()
    initTelemetry({
      DEV: false,
      VITE_OTEL_EXPORTER_OTLP_ENDPOINT: "https://otel.example/v1/traces",
      VITE_OTEL_SERVICE_NAME: "university-web",
      VITE_SERVICE_VERSION: "2026.8.14",
      VITE_BACKEND_ORIGIN: "https://api.example",
    } as ImportMetaEnv)

    expect(mocks.exporters).toEqual([{ url: "https://otel.example/v1/traces" }])
    expect(mocks.processors[0]?.kind).toBe("batch")
    expect(mocks.resourceFromAttributes).toHaveBeenCalledWith({
      "service.name": "university-web",
      "service.version": "2026.8.14",
    })
    expect(mocks.fetchOptions).toHaveLength(1)
    expect(mocks.xhrOptions).toHaveLength(1)
    const fetchTargets = (mocks.fetchOptions[0] as { propagateTraceHeaderCorsUrls: RegExp[] })
      .propagateTraceHeaderCorsUrls
    const originTarget = fetchTargets[0]
    expect(originTarget?.test("https://api.example/api/users")).toBe(true)
    expect(originTarget?.test("https://apiXexample/api/users")).toBe(false)
    expect(originTarget?.test("https://api.example.evil/api/users")).toBe(false)
    expect(
      (mocks.xhrOptions[0] as { propagateTraceHeaderCorsUrls: RegExp[] })
        .propagateTraceHeaderCorsUrls
    ).toEqual(fetchTargets)
    expect(getTracer("checkout")).toEqual({ name: "checkout" })
  })

  it("keeps the same-origin API target when no backend origin is configured", async () => {
    const { initTelemetry } = await loadTelemetry()
    initTelemetry({ DEV: true } as ImportMetaEnv)

    const targets = (mocks.fetchOptions[0] as { propagateTraceHeaderCorsUrls: RegExp[] })
      .propagateTraceHeaderCorsUrls
    expect(targets).toHaveLength(1)
    expect(targets[0]?.test("/api/users")).toBe(true)
    expect(targets[0]?.test("/not-api/users")).toBe(false)
  })

  it("strips all trailing slashes before constructing an origin regex", async () => {
    const { initTelemetry } = await loadTelemetry()
    initTelemetry({
      DEV: false,
      VITE_OTEL_EXPORTER_OTLP_ENDPOINT: "https://otel.example/v1/traces",
      VITE_BACKEND_ORIGIN: "https://api.example///",
    } as ImportMetaEnv)

    const targets = (mocks.fetchOptions[0] as { propagateTraceHeaderCorsUrls: RegExp[] })
      .propagateTraceHeaderCorsUrls
    expect(targets[0]?.test("https://api.example/api/users")).toBe(true)
    expect(targets[0]?.test("https://api.example///api/users")).toBe(false)
  })
})
