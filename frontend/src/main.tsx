import React, { StrictMode, useEffect } from "react"
import { createRoot } from "react-dom/client"
import CssBaseline from "@mui/material/CssBaseline"
import { CssVarsProvider } from "@mui/material/styles"
import { useColorScheme } from "@mui/material/styles"
import { QueryClientProvider } from "@tanstack/react-query"
import dayjs from "dayjs"
import "dayjs/locale/ru"

import App from "./App"
import ErrorBoundary from "./app/ErrorBoundary"
import { initGlobalErrorHandlers } from "./app/globalErrorHandlers"
import { logError } from "./app/logger"
import { initObservability } from "./app/observability"
import { queryClient } from "./app/queryClient"
import { initWebVitals, reportBootstrapTTI } from "./app/webVitals"
import "./assets/themes.css"
import "./i18n/config"
import "./styles/tailwind.css"
import theme from "./theme"
import { ensureTrustedTypesPolicies } from "./utils/trustedTypes"

// Note: Imports ordered to ensure critical services init first where possible,
// though imports are hoisted. Side-effect imports above run first.

initObservability()
initGlobalErrorHandlers()
const webVitalsEnabled = initWebVitals()
ensureTrustedTypesPolicies()
dayjs.locale("ru")

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

    // Try to recover consent if localStorage was cleared but browser still has subscription
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

function BodyColorSchemeSync() {
  const { mode, systemMode } = useColorScheme()
  useEffect(() => {
    const resolved = mode === "system" ? (systemMode ?? "light") : (mode ?? "light")
    // Apply dark class to both html and body elements
    // html for Tailwind CSS, body for themes.css compatibility
    document.documentElement.classList.toggle("dark", resolved === "dark")
    document.body.classList.toggle("dark", resolved === "dark")
    // Also set data attribute for consistency
    document.documentElement.dataset.colorScheme = resolved
    document.body.dataset.colorScheme = resolved
    return () => {
      document.documentElement.classList.remove("dark")
      document.body.classList.remove("dark")
      document.documentElement.removeAttribute("data-color-scheme")
      document.body.removeAttribute("data-color-scheme")
    }
  }, [mode, systemMode])
  return null
}

const rootElement = document.getElementById("root")
if (!rootElement) throw new Error("Root element not found")

const bootstrapStart = performance.now()

const root = createRoot(rootElement)
root.render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <CssVarsProvider
        theme={theme}
        defaultMode="system"
        modeStorageKey="ue-mode"
        disableTransitionOnChange
      >
        <CssBaseline enableColorScheme />
        <BodyColorSchemeSync />
        <ErrorBoundary>
          <App />
        </ErrorBoundary>
      </CssVarsProvider>
    </QueryClientProvider>
  </StrictMode>
)

const isLHCI = import.meta.env.VITE_LHCI === "true"

if (isLHCI) {
  rootElement.classList.add("ready")
} else {
  requestAnimationFrame(() => {
    requestAnimationFrame(() => {
      rootElement.classList.add("ready")
    })
  })
}

if (typeof window !== "undefined") {
  if (document.readyState === "complete") {
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
