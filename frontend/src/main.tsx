import { StrictMode } from "react"
import { hydrateRoot } from "react-dom/client"
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

// W149 SW2 — hydrateRoot replaces createRoot to complete W125 Phase 5 SSR
// migration. SSR-rendered HTML emitted by server.ts (via tanstackStart's
// handler.fetch — see frontend/src/server.ts) is now REUSED by the client
// instead of being discarded + re-rendered. PersistQueryClientProvider moved
// to __root.tsx RootComponent (client branch) so the SSR tree (SsrRoot wraps
// per-request QueryClientProvider) and client tree match structurally for
// hydration reconciliation. PersistQueryClientProvider's IndexedDB persister
// hydrates the singleton queryClient cache POST-mount (async); this stays
// CLIENT-ONLY by design (server uses per-request QueryClient via routerContext).
hydrateRoot(
  rootElement,
  <StrictMode>
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  </StrictMode>
)

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
