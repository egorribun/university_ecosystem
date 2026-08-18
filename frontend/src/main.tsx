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
    : (cb: () => void) => window.setTimeout(cb, 0)

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

const treeApp = (
  <StrictMode>
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  </StrictMode>
)
// A real server response is route-specific and can be hydrated safely. The
// post-build SPA fallback is intentionally the same file for every URL, so its
// prerendered route content cannot be hydrated at a different deep link. That
// shell carries an explicit marker and is mounted as a fresh document instead.
// React's document root is required because RootShell renders <html> directly.
const isStaticSpaShell = document.documentElement.dataset.renderMode === "static-spa"
if (isStaticSpaShell) {
  delete document.documentElement.dataset.renderMode
  createRoot(document).render(treeApp)
} else {
  hydrateRoot(document, treeApp)
}

const isLHCI = import.meta.env.VITE_LHCI === "true"

// W156 SW3 polish — `.ready` class moved to RootShell JSX (`<div id="root"
// className="ready">`) so server + client both have the attribute from the
// start. Pre-W156 SW3 imperative `classList.add` here was the source of the
// "tree hydrated but some attributes... won't be patched up" warning (rAF
// defer couldn't reliably outrun React 19's concurrent hydration timing).
// The lhci-marker hide logic stays — it's a LHCI-only DOM mutation that runs
// AFTER hydration completes (build-time deterministic flow, no hydration
// mismatch concern).
if (isLHCI) {
  const lhciMarker = document.getElementById("lhci-marker")
  if (lhciMarker) {
    lhciMarker.style.display = "none"
  }
}

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

// Wave 117 SW3 — schedule the deferred observability init AFTER React
// render + SW setup is kicked off so the main-thread idle window is more
// likely to actually be idle when OTEL / Sentry dynamic chunks resolve.
deferObservability(bootstrapStart)
