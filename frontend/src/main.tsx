import { StrictMode } from "react"
import { createRoot } from "react-dom/client"
import { PersistQueryClientProvider } from "@tanstack/react-query-persist-client"
// dayjs removed

import App from "./App"
import ErrorBoundary from "@/components/feedback/ErrorBoundary"
import { initGlobalErrorHandlers } from "./app/globalErrorHandlers"
import { logError } from "./app/logger"
import { initObservability } from "./app/observability"
import { queryClient, idbPersister } from "./app/queryClient"
import { initWebVitals, reportBootstrapTTI } from "./app/webVitals"
import "@fontsource-variable/inter"
import "@fontsource-variable/outfit"
import "./styles/tailwind.css"
import { ensureTrustedTypesPolicies } from "./utils/trustedTypes"
import { ThemeProvider } from "./contexts/ThemeContext"

initObservability()
initGlobalErrorHandlers()
const webVitalsEnabled = initWebVitals()
ensureTrustedTypesPolicies()

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

if (webVitalsEnabled) {
  const report = () => {
    const bootstrapEnd = performance.now()
    reportBootstrapTTI(bootstrapEnd - bootstrapStart)
  }

  if (typeof window.requestIdleCallback === "function") {
    window.requestIdleCallback(report)
  } else {
    window.setTimeout(report, 0)
  }
}
