import type { ReactNode } from "react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

const mocks = vi.hoisted(() => ({
  createRoot: vi.fn(),
  render: vi.fn(),
  hydrateRoot: vi.fn(),
  initGlobalErrorHandlers: vi.fn(),
  ensureTrustedTypesPolicies: vi.fn(),
  logError: vi.fn(),
  initObservability: vi.fn(),
  initWebVitals: vi.fn(),
  reportBootstrapTTI: vi.fn(),
  registerServiceWorker: vi.fn(),
  recoverPushConsentFromBrowser: vi.fn(),
  hasPushConsent: vi.fn(),
  ensurePushSubscription: vi.fn(),
}))

let requestedIdleOptions: IdleRequestOptions | undefined

vi.mock("react-dom/client", () => ({
  createRoot: mocks.createRoot,
  hydrateRoot: mocks.hydrateRoot,
}))
vi.mock("../App", () => ({ default: () => null }))
vi.mock("@/components/feedback/ErrorBoundary", () => ({
  default: ({ children }: { children: ReactNode }) => children,
}))
vi.mock("../app/globalErrorHandlers", () => ({
  initGlobalErrorHandlers: mocks.initGlobalErrorHandlers,
}))
vi.mock("../utils/trustedTypes", () => ({
  ensureTrustedTypesPolicies: mocks.ensureTrustedTypesPolicies,
}))
vi.mock("../app/logger", () => ({ logError: mocks.logError }))
vi.mock("../app/observability", () => ({ initObservability: mocks.initObservability }))
vi.mock("../app/webVitals", () => ({
  initWebVitals: mocks.initWebVitals,
  reportBootstrapTTI: mocks.reportBootstrapTTI,
}))
vi.mock("../push/register-sw", () => ({
  registerServiceWorker: mocks.registerServiceWorker,
}))
vi.mock("../push/subscribe", () => ({
  recoverPushConsentFromBrowser: mocks.recoverPushConsentFromBrowser,
  hasPushConsent: mocks.hasPushConsent,
  ensurePushSubscription: mocks.ensurePushSubscription,
}))

const setReadyState = (readyState: DocumentReadyState) => {
  Object.defineProperty(document, "readyState", {
    configurable: true,
    value: readyState,
  })
}

const setServiceWorkerSupport = (supported: boolean) => {
  if (supported) {
    Object.defineProperty(navigator, "serviceWorker", {
      configurable: true,
      value: {},
    })
  } else {
    Reflect.deleteProperty(navigator, "serviceWorker")
  }
}

const runIdleImmediately = () => {
  Object.defineProperty(window, "requestIdleCallback", {
    configurable: true,
    value: (callback: IdleRequestCallback, options?: IdleRequestOptions) => {
      requestedIdleOptions = options
      callback({ didTimeout: false, timeRemaining: () => 5 } as IdleDeadline)
      return 1
    },
  })
}

const importMain = async () => {
  await import("../main")
}

const waitForDeferredWork = async () => {
  await vi.waitFor(() => expect(mocks.initWebVitals).toHaveBeenCalled())
}

beforeEach(() => {
  vi.resetModules()
  vi.unstubAllEnvs()
  vi.clearAllMocks()
  requestedIdleOptions = undefined
  vi.useRealTimers()

  document.documentElement.innerHTML =
    '<head></head><body><div id="lhci-marker">audit</div><div id="root"></div></body>'
  setReadyState("complete")
  setServiceWorkerSupport(false)
  runIdleImmediately()

  mocks.initWebVitals.mockReturnValue(true)
  mocks.registerServiceWorker.mockResolvedValue({ scope: "/" })
  mocks.recoverPushConsentFromBrowser.mockResolvedValue(false)
  mocks.hasPushConsent.mockReturnValue(false)
  mocks.ensurePushSubscription.mockResolvedValue(undefined)
  mocks.createRoot.mockReturnValue({ render: mocks.render })
  vi.spyOn(performance, "now").mockReturnValueOnce(100).mockReturnValueOnce(145)
})

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllEnvs()
  vi.restoreAllMocks()
})

describe("browser entrypoint", () => {
  it("installs bootstrap guards, hydrates the document, and reports deferred TTI", async () => {
    vi.stubEnv("PROD", false)

    await importMain()
    await waitForDeferredWork()

    expect(mocks.initGlobalErrorHandlers).toHaveBeenCalledOnce()
    expect(mocks.ensureTrustedTypesPolicies).toHaveBeenCalledOnce()
    expect(mocks.hydrateRoot).toHaveBeenCalledWith(document, expect.anything())
    expect(mocks.createRoot).not.toHaveBeenCalled()
    expect(mocks.initObservability).toHaveBeenCalledOnce()
    expect(requestedIdleOptions).toEqual({ timeout: 10_000 })
    expect(mocks.reportBootstrapTTI).toHaveBeenCalledWith(45)
    expect(mocks.registerServiceWorker).not.toHaveBeenCalled()
  })

  it("mounts the static SPA fallback instead of hydrating route-specific shell content", async () => {
    vi.stubEnv("PROD", false)
    document.documentElement.dataset.renderMode = "static-spa"

    await importMain()

    expect(mocks.createRoot).toHaveBeenCalledWith(document)
    expect(mocks.render).toHaveBeenCalledWith(expect.anything())
    expect(mocks.hydrateRoot).not.toHaveBeenCalled()
    expect(document.documentElement).not.toHaveAttribute("data-render-mode")
  })

  it("mounts the LHCI static shell without hydrating route-agnostic markup", async () => {
    vi.stubEnv("PROD", false)
    vi.stubEnv("VITE_LHCI", "true")
    document.documentElement.dataset.renderMode = "static-spa"

    await importMain()

    expect(mocks.createRoot).toHaveBeenCalledWith(document)
    expect(mocks.hydrateRoot).not.toHaveBeenCalled()
    expect(document.documentElement).not.toHaveAttribute("data-render-mode")
  })

  it("uses the timeout idle fallback and skips TTI reporting when web vitals are disabled", async () => {
    vi.useFakeTimers()
    vi.stubEnv("PROD", true)
    mocks.initWebVitals.mockReturnValue(false)
    delete (window as { requestIdleCallback?: typeof window.requestIdleCallback })
      .requestIdleCallback

    await importMain()
    await vi.runAllTimersAsync()

    expect(mocks.initWebVitals).toHaveBeenCalledOnce()
    expect(mocks.reportBootstrapTTI).not.toHaveBeenCalled()
    expect(mocks.registerServiceWorker).not.toHaveBeenCalled()
  })

  it("stops service-worker setup when registration returns no registration", async () => {
    vi.stubEnv("PROD", true)
    setServiceWorkerSupport(true)
    mocks.registerServiceWorker.mockResolvedValue(null)

    await importMain()

    await vi.waitFor(() => expect(mocks.registerServiceWorker).toHaveBeenCalledWith("/sw.js"))
    expect(mocks.recoverPushConsentFromBrowser).not.toHaveBeenCalled()
  })

  it("recovers browser consent but does not subscribe without explicit consent", async () => {
    vi.stubEnv("PROD", true)
    setServiceWorkerSupport(true)

    await importMain()

    await vi.waitFor(() => expect(mocks.recoverPushConsentFromBrowser).toHaveBeenCalledOnce())
    expect(mocks.ensurePushSubscription).not.toHaveBeenCalled()
  })

  it("silently refreshes a consented push subscription", async () => {
    vi.stubEnv("PROD", true)
    setServiceWorkerSupport(true)
    mocks.hasPushConsent.mockReturnValue(true)
    const registration = { scope: "/sw.js" }
    mocks.registerServiceWorker.mockResolvedValue(registration)

    await importMain()

    await vi.waitFor(() =>
      expect(mocks.ensurePushSubscription).toHaveBeenCalledWith({
        registration,
        requestPermission: false,
      })
    )
  })

  it("logs push refresh errors without failing bootstrap", async () => {
    vi.stubEnv("PROD", true)
    setServiceWorkerSupport(true)
    mocks.hasPushConsent.mockReturnValue(true)
    const failure = new Error("push refresh failed")
    mocks.ensurePushSubscription.mockRejectedValue(failure)

    await importMain()

    await vi.waitFor(() =>
      expect(mocks.logError).toHaveBeenCalledWith("Failed to ensure push subscription", failure)
    )
  })

  it("logs service-worker registration failures without failing bootstrap", async () => {
    vi.stubEnv("PROD", true)
    setServiceWorkerSupport(true)
    const failure = new Error("registration failed")
    mocks.registerServiceWorker.mockRejectedValue(failure)

    await importMain()

    await vi.waitFor(() =>
      expect(mocks.logError).toHaveBeenCalledWith("Service worker registration failed", failure)
    )
  })

  it("defers service-worker setup until window load when the document is not complete", async () => {
    vi.stubEnv("PROD", true)
    setServiceWorkerSupport(true)
    setReadyState("loading")

    await importMain()
    expect(mocks.registerServiceWorker).not.toHaveBeenCalled()

    window.dispatchEvent(new Event("load"))
    await vi.waitFor(() => expect(mocks.registerServiceWorker).toHaveBeenCalledWith("/sw.js"))
  })

  it("hides an existing LHCI marker and skips service-worker setup", async () => {
    vi.stubEnv("PROD", true)
    vi.stubEnv("VITE_LHCI", "true")
    setServiceWorkerSupport(true)

    await importMain()

    expect(document.getElementById("lhci-marker")).toHaveStyle({ display: "none" })
    expect(mocks.registerServiceWorker).not.toHaveBeenCalled()
  })

  it("keeps synchronous error guards but skips optional telemetry in LHCI mode", async () => {
    vi.stubEnv("VITE_LHCI", "true")

    await importMain()

    expect(mocks.initGlobalErrorHandlers).toHaveBeenCalledOnce()
    expect(mocks.ensureTrustedTypesPolicies).toHaveBeenCalledOnce()
    expect(mocks.initObservability).not.toHaveBeenCalled()
    expect(mocks.initWebVitals).not.toHaveBeenCalled()
    expect(requestedIdleOptions).toBeUndefined()
  })

  it("tolerates an LHCI document without the optional marker", async () => {
    vi.stubEnv("VITE_LHCI", "true")
    document.getElementById("lhci-marker")?.remove()

    await importMain()

    expect(mocks.hydrateRoot).toHaveBeenCalledOnce()
  })

  it("logs deferred observability failures", async () => {
    const failure = new Error("otel failed")
    mocks.initObservability.mockImplementation(() => {
      throw failure
    })

    await importMain()

    await vi.waitFor(() =>
      expect(mocks.logError).toHaveBeenCalledWith("Deferred observability init failed", failure)
    )
  })

  it("fails fast when the SSR shell has no root marker", async () => {
    document.getElementById("root")?.remove()

    await expect(importMain()).rejects.toThrow("Root element not found")
    expect(mocks.hydrateRoot).not.toHaveBeenCalled()
  })
})
