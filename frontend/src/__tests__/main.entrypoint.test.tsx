import type { ReactNode } from "react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import {
  dispatchServiceWorkerBootstrap,
  SERVICE_WORKER_BOOTSTRAP_EVENT,
  type ServiceWorkerBootstrapEventDetail,
} from "../app/pwaEvents"

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
  syncPushForConfirmedIdentity: vi.fn(),
  recoverPushConsentFromBrowser: vi.fn(),
  ensurePushSubscription: vi.fn(),
}))

let requestedIdleOptions: IdleRequestOptions | undefined

vi.mock("react-dom/client", () => ({
  createRoot: mocks.createRoot,
  hydrateRoot: mocks.hydrateRoot,
}))
vi.mock("../App", () => ({ default: () => null }))
vi.mock("@/components/feedback/ErrorBoundary", () => ({
  ErrorBoundary: ({ children }: { children: ReactNode }) => children,
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
  syncPushForConfirmedIdentity: mocks.syncPushForConfirmedIdentity,
  recoverPushConsentFromBrowser: mocks.recoverPushConsentFromBrowser,
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

const observeServiceWorkerBootstrap = () => {
  let status: ServiceWorkerBootstrapEventDetail["status"] | undefined
  window.addEventListener(
    SERVICE_WORKER_BOOTSTRAP_EVENT,
    (event) => {
      status = (event as CustomEvent<ServiceWorkerBootstrapEventDetail>).detail.status
    },
    { once: true }
  )
  return () => status
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
  Object.values(mocks).forEach((mock) => mock.mockReset())
  requestedIdleOptions = undefined
  vi.useRealTimers()

  document.documentElement.innerHTML =
    '<head></head><body><div id="lhci-marker">audit</div><div id="root"></div></body>'
  setReadyState("complete")
  setServiceWorkerSupport(false)
  runIdleImmediately()

  mocks.initWebVitals.mockReturnValue(true)
  mocks.registerServiceWorker.mockResolvedValue({ scope: "/" })
  mocks.syncPushForConfirmedIdentity.mockResolvedValue(null)
  mocks.createRoot.mockReturnValue({ render: mocks.render })
  vi.spyOn(performance, "now").mockReturnValueOnce(100).mockReturnValueOnce(145)
})

afterEach(async () => {
  // Each import owns deferred telemetry imports, even when a test only checks rendering.
  try {
    await vi.dynamicImportSettled()
  } finally {
    vi.useRealTimers()
    vi.unstubAllEnvs()
    vi.restoreAllMocks()
  }
})

describe("browser entrypoint", () => {
  it("installs bootstrap guards, hydrates the document, and reports deferred TTI", async () => {
    vi.stubEnv("PROD", false)
    const readBootstrapStatus = observeServiceWorkerBootstrap()

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
    expect(readBootstrapStatus()).toBe("disabled")
  })

  it("preserves the executed parser theme script while mounting the static SPA fallback", async () => {
    vi.stubEnv("PROD", false)
    const originalClass = document.documentElement.className
    const originalLang = document.documentElement.getAttribute("lang")
    const originalSelectedLanguage = window.__UE_SELECTED_LANG__
    const originalThemeMarker = Object.getOwnPropertyDescriptor(
      window,
      "__UE_THEME_INIT_SCRIPT_RAN__"
    )
    const originalStaticMountMarker = Object.getOwnPropertyDescriptor(
      window,
      "__UE_STATIC_SPA_DOCUMENT_MOUNT__"
    )
    const nonceMeta = document.createElement("meta")
    nonceMeta.setAttribute("property", "csp-nonce")
    nonceMeta.content = "static-spa-nonce"
    const parserThemeScript = document.createElement("script")
    parserThemeScript.id = "theme-init-script"
    parserThemeScript.src = window.location.origin + "/theme-init.js"
    parserThemeScript.setAttribute("nonce", "static-spa-nonce")
    const parserThemeText = parserThemeScript.textContent

    try {
      document.head.append(nonceMeta, parserThemeScript)
      document.documentElement.dataset.renderMode = "static-spa"
      document.documentElement.classList.add("dark")
      document.documentElement.lang = "en"
      window.__UE_SELECTED_LANG__ = "en"
      Reflect.set(window, "__UE_THEME_INIT_SCRIPT_RAN__", true)
      expect(document.querySelectorAll('[id="theme-init-script"]')).toHaveLength(1)

      mocks.createRoot.mockImplementation((container: Document) => {
        expect(Reflect.get(window, "__UE_STATIC_SPA_DOCUMENT_MOUNT__")).toBe(true)
        expect(container).toBe(document)
        expect(parserThemeScript.isConnected).toBe(true)
        expect(document.querySelectorAll('[id="theme-init-script"]')).toHaveLength(1)
        return { render: mocks.render }
      })

      await importMain()

      expect(mocks.createRoot).toHaveBeenCalledWith(document)
      expect(mocks.render).toHaveBeenCalledWith(expect.anything())
      expect(mocks.hydrateRoot).not.toHaveBeenCalled()
      expect(document.documentElement).not.toHaveAttribute("data-render-mode")
      expect(document.documentElement).toHaveClass("dark")
      expect(document.documentElement).toHaveAttribute("lang", "en")
      expect(window.__UE_SELECTED_LANG__).toBe("en")
      expect(parserThemeScript.src).toBe(window.location.origin + "/theme-init.js")
      expect(parserThemeScript.nonce).toBe("static-spa-nonce")
      expect(parserThemeScript.textContent).toBe(parserThemeText)
      expect(parserThemeScript.isConnected).toBe(true)
      expect(document.querySelectorAll('[id="theme-init-script"]')).toHaveLength(1)
    } finally {
      nonceMeta.remove()
      parserThemeScript.remove()
      document.documentElement.className = originalClass
      if (originalLang === null) document.documentElement.removeAttribute("lang")
      else document.documentElement.setAttribute("lang", originalLang)
      if (originalSelectedLanguage === undefined)
        Reflect.deleteProperty(window, "__UE_SELECTED_LANG__")
      else window.__UE_SELECTED_LANG__ = originalSelectedLanguage
      if (originalThemeMarker) {
        Object.defineProperty(window, "__UE_THEME_INIT_SCRIPT_RAN__", originalThemeMarker)
      } else {
        Reflect.deleteProperty(window, "__UE_THEME_INIT_SCRIPT_RAN__")
      }
      if (originalStaticMountMarker) {
        Object.defineProperty(window, "__UE_STATIC_SPA_DOCUMENT_MOUNT__", originalStaticMountMarker)
      } else {
        Reflect.deleteProperty(window, "__UE_STATIC_SPA_DOCUMENT_MOUNT__")
      }
    }
  })

  it.each([
    {
      label: "an unexecuted static asset",
      renderMode: "static-spa",
      source: `${window.location.origin}/theme-init.js`,
      executed: false,
      elementTag: "script",
      parentTag: "head",
    },
    {
      label: "a static asset from another origin",
      renderMode: "static-spa",
      source: "https://example.invalid/theme-init.js",
      executed: true,
      elementTag: "script",
      parentTag: "head",
    },
    {
      label: "an SSR document",
      renderMode: undefined,
      source: `${window.location.origin}/theme-init.js`,
      executed: true,
      elementTag: "script",
      parentTag: "head",
    },
    {
      label: "a non-script HTMLElement with the owned id",
      renderMode: "static-spa",
      source: `${window.location.origin}/theme-init.js`,
      executed: true,
      elementTag: "meta",
      parentTag: "head",
    },
    {
      label: "an executed same-origin script outside document.head",
      renderMode: "static-spa",
      source: `${window.location.origin}/theme-init.js`,
      executed: true,
      elementTag: "script",
      parentTag: "body",
    },
  ])(
    "preserves the parser theme element for $label",
    async ({ renderMode, source, executed, elementTag, parentTag }) => {
      vi.stubEnv("PROD", false)
      const previousThemeMarker = Object.getOwnPropertyDescriptor(
        window,
        "__UE_THEME_INIT_SCRIPT_RAN__"
      )
      const parserThemeNode = document.createElement(elementTag)
      parserThemeNode.id = "theme-init-script"
      if (parserThemeNode instanceof HTMLScriptElement) parserThemeNode.src = source

      try {
        const insertionParent = parentTag === "body" ? document.body : document.head
        insertionParent.append(parserThemeNode)
        if (renderMode) document.documentElement.dataset.renderMode = renderMode
        Reflect.set(window, "__UE_THEME_INIT_SCRIPT_RAN__", executed)

        await importMain()

        expect(parserThemeNode.isConnected).toBe(true)
        if (renderMode) {
          expect(mocks.createRoot).toHaveBeenCalledWith(document)
          expect(mocks.hydrateRoot).not.toHaveBeenCalled()
        } else {
          expect(mocks.hydrateRoot).toHaveBeenCalledWith(document, expect.anything())
          expect(mocks.createRoot).not.toHaveBeenCalled()
        }
      } finally {
        parserThemeNode.remove()
        if (previousThemeMarker) {
          Object.defineProperty(window, "__UE_THEME_INIT_SCRIPT_RAN__", previousThemeMarker)
        } else {
          Reflect.deleteProperty(window, "__UE_THEME_INIT_SCRIPT_RAN__")
        }
      }
    }
  )

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

  it("reports unsupported when production bootstrap lacks the service-worker API", async () => {
    vi.stubEnv("PROD", true)
    setServiceWorkerSupport(false)
    const readBootstrapStatus = observeServiceWorkerBootstrap()

    await importMain()

    expect(readBootstrapStatus()).toBe("unsupported")
    expect(mocks.registerServiceWorker).not.toHaveBeenCalled()
  })

  it("stops service-worker setup when registration returns no registration", async () => {
    vi.stubEnv("PROD", true)
    setServiceWorkerSupport(true)
    mocks.registerServiceWorker.mockResolvedValue(null)

    await importMain()

    await vi.waitFor(() => expect(mocks.registerServiceWorker).toHaveBeenCalledWith("/sw.js"))
    await Promise.resolve()
    expect(mocks.syncPushForConfirmedIdentity).not.toHaveBeenCalled()
  })

  it("delegates push sync to the confirmed-identity gate instead of persisting directly", async () => {
    vi.stubEnv("PROD", true)
    setServiceWorkerSupport(true)
    const registration = { scope: "/sw.js" }
    mocks.registerServiceWorker.mockResolvedValue(registration)

    await importMain()

    await vi.waitFor(() =>
      expect(mocks.syncPushForConfirmedIdentity).toHaveBeenCalledWith({ registration })
    )
    expect(mocks.syncPushForConfirmedIdentity).toHaveBeenCalledOnce()
    expect(mocks.recoverPushConsentFromBrowser).not.toHaveBeenCalled()
    expect(mocks.ensurePushSubscription).not.toHaveBeenCalled()
  })

  it("does not hold service-worker bootstrap on the identity-gated push sync", async () => {
    vi.stubEnv("PROD", true)
    setServiceWorkerSupport(true)
    let resolveSync!: (value: null) => void
    const pendingSync = new Promise<null>((resolve) => {
      resolveSync = resolve
    })
    mocks.syncPushForConfirmedIdentity.mockReturnValue(pendingSync)

    try {
      await importMain()

      await vi.waitFor(() => expect(mocks.syncPushForConfirmedIdentity).toHaveBeenCalledOnce())
      expect(mocks.logError).not.toHaveBeenCalled()
    } finally {
      resolveSync(null)
      await pendingSync
    }
  })

  it("keeps worker readiness when push sync throws synchronously", async () => {
    vi.stubEnv("PROD", true)
    setServiceWorkerSupport(true)
    const registration = { scope: "/sw.js" }
    const failure = new Error("push sync threw synchronously")
    const bootstrapStatuses: ServiceWorkerBootstrapEventDetail["status"][] = []
    const captureBootstrapStatus = (event: Event) => {
      bootstrapStatuses.push(
        (event as CustomEvent<ServiceWorkerBootstrapEventDetail>).detail.status
      )
    }
    window.addEventListener(SERVICE_WORKER_BOOTSTRAP_EVENT, captureBootstrapStatus)
    mocks.registerServiceWorker.mockImplementation(async () => {
      dispatchServiceWorkerBootstrap("ready")
      return registration
    })
    mocks.syncPushForConfirmedIdentity.mockImplementation(() => {
      throw failure
    })

    try {
      await importMain()

      await vi.waitFor(() =>
        expect(mocks.logError).toHaveBeenCalledWith(expect.any(String), failure)
      )
      expect(mocks.registerServiceWorker).toHaveBeenCalledOnce()
      expect(mocks.syncPushForConfirmedIdentity).toHaveBeenCalledWith({ registration })
      expect(bootstrapStatuses).toEqual(["ready"])
    } finally {
      window.removeEventListener(SERVICE_WORKER_BOOTSTRAP_EVENT, captureBootstrapStatus)
    }
  })

  it("logs push sync errors without failing bootstrap", async () => {
    vi.stubEnv("PROD", true)
    setServiceWorkerSupport(true)
    const failure = new Error("push sync failed")
    mocks.syncPushForConfirmedIdentity.mockRejectedValue(failure)

    await importMain()

    await vi.waitFor(() =>
      expect(mocks.logError).toHaveBeenCalledWith("Failed to sync push subscription", failure)
    )
    expect(mocks.logError).not.toHaveBeenCalledWith(
      "Service worker registration failed",
      expect.anything()
    )
  })

  it("reports failure when a lazy service-worker module cannot be imported", async () => {
    vi.stubEnv("PROD", true)
    setServiceWorkerSupport(true)
    const failure = new Error("service-worker module import failed")
    const readBootstrapStatus = observeServiceWorkerBootstrap()
    vi.doMock("../push/subscribe", () => {
      throw failure
    })

    try {
      await importMain()
      await vi.waitFor(() => expect(readBootstrapStatus()).toBe("failed"))
      expect(mocks.registerServiceWorker).not.toHaveBeenCalled()
      expect(mocks.logError).toHaveBeenCalledWith(
        "Service worker registration failed",
        expect.objectContaining({ cause: failure })
      )
    } finally {
      vi.doMock("../push/subscribe", () => ({
        syncPushForConfirmedIdentity: mocks.syncPushForConfirmedIdentity,
        recoverPushConsentFromBrowser: mocks.recoverPushConsentFromBrowser,
        ensurePushSubscription: mocks.ensurePushSubscription,
      }))
    }
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
    const readBootstrapStatus = observeServiceWorkerBootstrap()

    await importMain()
    await vi.waitFor(() => expect(mocks.hydrateRoot).toHaveBeenCalledOnce())

    expect(document.getElementById("lhci-marker")).toHaveStyle({ display: "none" })
    expect(mocks.registerServiceWorker).not.toHaveBeenCalled()
    expect(readBootstrapStatus()).toBe("disabled")
  })

  it("keeps synchronous error guards but skips optional telemetry in LHCI mode", async () => {
    vi.stubEnv("VITE_LHCI", "true")

    await importMain()
    await vi.waitFor(() => expect(mocks.hydrateRoot).toHaveBeenCalledOnce())

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

    await vi.waitFor(() => expect(mocks.hydrateRoot).toHaveBeenCalledOnce())
  })

  it("waits for the document load event before hydrating an LHCI SSR shell", async () => {
    vi.useFakeTimers()
    vi.stubEnv("VITE_LHCI", "true")
    setReadyState("loading")

    await importMain()
    expect(mocks.hydrateRoot).not.toHaveBeenCalled()

    window.dispatchEvent(new Event("load"))
    await vi.runAllTimersAsync()

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
