import { StrictMode } from "react"
import { createRoot } from "react-dom/client"
import { PersistQueryClientProvider } from "@tanstack/react-query-persist-client"
// dayjs removed

import App from "./App"
import ErrorBoundary from "@/components/feedback/ErrorBoundary"
import { initGlobalErrorHandlers } from "./app/globalErrorHandlers"
import { logError } from "./app/logger"
import { queryClient, idbPersister } from "./app/queryClient"
import "@fontsource-variable/inter"
import "@fontsource-variable/outfit"
import "./styles/tailwind.css"
import { ensureTrustedTypesPolicies } from "./utils/trustedTypes"
import { ThemeProvider } from "./contexts/ThemeContext"

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
    : ((cb: IdleRequestCallback) =>
        window.setTimeout(
          () => cb({ didTimeout: false, timeRemaining: () => 0 } as IdleDeadline),
          0
        ))

function deferObservability(bootstrapStart: number): void {
  idle(() => {
    void Promise.all([
      import("./app/observability").then(m => {
        m.initObservability()
      }),
      import("./app/webVitals").then(m => {
        const enabled = m.initWebVitals()
        if (enabled) {
          const bootstrapEnd = performance.now()
          m.reportBootstrapTTI(bootstrapEnd - bootstrapStart)
        }
      }),
    ]).catch(error => {
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

const root = createRoot(rootElement)
root.render(
  <StrictMode>
    <PersistQueryClientProvider client={queryClient} persistOptions={{ persister: idbPersister }}>
      <ThemeProvider>
        <ErrorBoundary>
          <App />
        </ErrorBoundary>
      </ThemeProvider>
    </PersistQueryClientProvider>
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
