import React, { Suspense, useEffect } from "react"
import ReactDOM from "react-dom/client"
import { CssBaseline } from "@mui/material"
import { CssVarsProvider, useColorScheme } from "@mui/material/styles"
import { QueryClientProvider } from "@tanstack/react-query"
import App from "./App"
import ErrorBoundary from "./app/ErrorBoundary"
import { lazyDevtools, queryClient } from "./app/queryClient"
import theme from "./theme"
import "./assets/themes.css"
import "dayjs/locale/ru"
import { registerServiceWorker } from "./push/register-sw"
import { ensurePushSubscription, hasPushConsent } from "./push/subscribe"
import { ensureTrustedTypesPolicies } from "./utils/trustedTypes"

ensureTrustedTypesPolicies()

async function setupServiceWorker() {
  if (!import.meta.env.PROD) return
  if (!("serviceWorker" in navigator)) return

  try {
    const registration = await registerServiceWorker("/sw.js")
    if (!registration) return

    if (!hasPushConsent()) return

    try {
      await ensurePushSubscription(undefined, registration)
    } catch (error) {
      console.error("Failed to ensure push subscription", error)
    }
  } catch (error) {
    console.error("Service worker registration failed", error)
  }
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

function BodyColorSchemeSync() {
  const { mode, systemMode } = useColorScheme()

  useEffect(() => {
    const resolved = mode === "system" ? (systemMode ?? "light") : (mode ?? "light")
    document.body.dataset.colorScheme = resolved
    document.body.classList.toggle("dark", resolved === "dark")
    return () => {
      document.body.classList.remove("dark")
      document.body.removeAttribute("data-color-scheme")
    }
  }, [mode, systemMode])

  return null
}

const ReactQueryDevtools = lazyDevtools()

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <CssVarsProvider
        theme={theme}
        defaultMode="system"
        modeStorageKey="theme"
        disableTransitionOnChange
      >
        <CssBaseline enableColorScheme />
        <BodyColorSchemeSync />
        <ErrorBoundary>
          <App />
        </ErrorBoundary>
      </CssVarsProvider>
      {ReactQueryDevtools ? (
        <Suspense fallback={null}>
          <ReactQueryDevtools buttonPosition="bottom-left" />
        </Suspense>
      ) : null}
    </QueryClientProvider>
  </React.StrictMode>
)
