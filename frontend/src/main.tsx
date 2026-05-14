import { StrictMode } from "react"
import { createRoot, hydrateRoot } from "react-dom/client"
// dayjs removed

import App from "./App"
import ErrorBoundary from "@/components/feedback/ErrorBoundary"
import { initGlobalErrorHandlers } from "./app/globalErrorHandlers"
import { logError } from "./app/logger"
// W149 SW2 — PersistQueryClientProvider + queryClient + idbPersister moved to
// __root.tsx RootComponent (client branch) to match SsrRoot's provider tree
// for hydrateRoot reconciliation. createRoot → hydrateRoot reuses the
// SSR-rendered HTML instead of discarding + re-rendering.
import "@fontsource-variable/inter"
import "@fontsource-variable/outfit"
import "./styles/tailwind.css"
import { ensureTrustedTypesPolicies } from "./utils/trustedTypes"
// Wave 127 SW1 — ThemeProvider hoisted to __root.tsx RootComponent (server +
// client). Removed from main.tsx render tree.

// Wave 117 SW3 — keep sync on bootstrap: global error handlers (must catch
// any early throw) + Trusted Types policies (CSP requirement, must be set
// before any innerHTML writes). Everything else moves to requestIdleCallback
// below.
initGlobalErrorHandlers()
ensureTrustedTypesPolicies()

// Wave 117 SW3 — defer Sentry + OTEL + Web Vitals init to post-render via
// requestIdleCallback. Dynamic-import'ing `./app/observability` pulls the
// entire OTEL dependency chain (WebTracerProvider + OTLPTraceExporter +
// FetchInstrumentation + XMLHttpRequestInstrumentation + resources +
// semantic-conventions) out of the main chunk. Paired with the vite.config
// `vendor-otel` manualChunks branch, OTEL now lives in an async chunk that
// loads AFTER first paint. Real users get ~0.5-1.2s earlier LCP on mobile
// 3G; LHCI runs without DSN configured don't benefit at runtime (early
// return in initObservability) but still benefit from the bundle-size
// reduction (smaller main chunk = faster parse/eval).
//
// Early-error gap: synchronous throws during module evaluation (createRoot,
// root.render, ThemeProvider mount) happen BEFORE Sentry attaches its own
// listeners. `initGlobalErrorHandlers` above still catches via window.onerror
// + unhandledrejection — those events sit in the JS task queue and Sentry
// ingests them through its own event hook once it initialises.
const idle =
  typeof window.requestIdleCallback === "function"
    ? window.requestIdleCallback.bind(window)
    : (cb: IdleRequestCallback) =>
        window.setTimeout(
          () => cb({ didTimeout: false, timeRemaining: () => 0 } as IdleDeadline),
          0
        )

function deferObservability(bootstrapStart: number): void {
  idle(() => {
    void Promise.all([
      import("./app/observability").then((m) => {
        m.initObservability()
      }),
      import("./app/webVitals").then((m) => {
        const enabled = m.initWebVitals()
        if (enabled) {
          const bootstrapEnd = performance.now()
          m.reportBootstrapTTI(bootstrapEnd - bootstrapStart)
        }
      }),
    ]).catch((error) => {
      logError("Deferred observability init failed", error)
    })
  })
}

async function setupServiceWorker() {
  if (!import.meta.env.PROD) return
  if (!("serviceWorker" in navigator)) return
  try {
    const [SWMod, PushMod] = await Promise.all([
      import("./push/register-sw"),
      import("./push/subscribe"),
    ])
    const { registerServiceWorker } = SWMod
    const { ensurePushSubscription, hasPushConsent, recoverPushConsentFromBrowser } = PushMod
    const registration = await registerServiceWorker("/sw.js")
    if (!registration) return

    await recoverPushConsentFromBrowser()

    if (!hasPushConsent()) return
    try {
      await ensurePushSubscription({ registration, requestPermission: false })
    } catch (error) {
      logError("Failed to ensure push subscription", error)
    }
  } catch (error) {
    logError("Service worker registration failed", error)
  }
}

const rootElement = document.getElementById("root")
if (!rootElement) throw new Error("Root element not found")

const bootstrapStart = performance.now()

// W149 SW2 + W150 polish-followup — conditional hydrateRoot vs createRoot
// based on whether the SSR shell delivered rendered React content. W149 SW2
// unconditionally used hydrateRoot to complete the W125 Phase 5 SSR migration,
// but when root `ssr: false` (W150 polish-followup dev fallback) OR any
// configuration that produces an empty `<div id="root">` shell, hydrateRoot
// throws React error #418 because the existing DOM doesn't match what React
// expects to render. This conditional gracefully handles BOTH modes:
//   - SSR'd (root has children): hydrateRoot reuses server-rendered tree (W125 perf)
//   - Empty shell (`ssr: false` or build artifact lacks server-render): createRoot
//     mounts a fresh tree — same behavior as pre-W149 SW2.
// Production-quality SSR should use ssr:true with matching SSR/client trees;
// this fallback keeps dev working when SSR is intentionally disabled.
const treeApp = (
  <StrictMode>
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  </StrictMode>
)
// Check for *real* hydrate-able SSR content: any HTML element child (Node.ELEMENT_NODE = 1).
// hasChildNodes() returns TRUE even for React 19 Suspense boundary comment markers
// (`<!--$--><!--/$-->`) emitted when route ssr is false, which would push us into
// hydrateRoot path against an empty Suspense — causing React #418 mismatch.
const hasRealSsrContent = Array.from(rootElement.childNodes).some(
  (n) => n.nodeType === Node.ELEMENT_NODE
)
if (hasRealSsrContent) {
  hydrateRoot(rootElement, treeApp)
} else {
  // Clear any Suspense marker comments so createRoot starts from clean container.
  while (rootElement.firstChild) {
    rootElement.removeChild(rootElement.firstChild)
  }
  createRoot(rootElement).render(treeApp)
}

const isLHCI = import.meta.env.VITE_LHCI === "true"

if (isLHCI) {
  rootElement.classList.add("ready")
  const lhciMarker = document.getElementById("lhci-marker")
  if (lhciMarker) {
    lhciMarker.style.display = "none"
  }
} else {
  requestAnimationFrame(() => {
    requestAnimationFrame(() => {
      rootElement.classList.add("ready")
    })
  })
}

if (typeof window !== "undefined") {
  if (isLHCI) {
    // Skip Service Worker setup
  } else if (document.readyState === "complete") {
    void setupServiceWorker()
  } else {
    window.addEventListener(
      "load",
      () => {
        void setupServiceWorker()
      },
      { once: true }
    )
  }
}

// Wave 117 SW3 — schedule the deferred observability init AFTER React
// render + SW setup is kicked off so the main-thread idle window is more
// likely to actually be idle when OTEL / Sentry dynamic chunks resolve.
deferObservability(bootstrapStart)
