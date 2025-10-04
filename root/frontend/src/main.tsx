import React, { Suspense, useEffect } from "react"
import ReactDOM from "react-dom/client"
import { CssBaseline } from "@mui/material"
import { CssVarsProvider, useColorScheme } from "@mui/material/styles"
import { registerSW } from "virtual:pwa-register"
import { QueryClientProvider } from "@tanstack/react-query"
import App from "./App"
import ErrorBoundary from "./app/ErrorBoundary"
import { lazyDevtools, queryClient } from "./app/queryClient"
import { PWA_REFRESH_EVENT, type ServiceWorkerUpdateEventDetail } from "./app/pwaEvents"
import theme from "./theme"
import "./assets/themes.css"
import "dayjs/locale/ru"

const updateSW = registerSW({
  immediate: true,
  onNeedRefresh() {
    const detail: ServiceWorkerUpdateEventDetail = {
      update: () => updateSW(true),
    }
    window.dispatchEvent(
      new CustomEvent<ServiceWorkerUpdateEventDetail>(PWA_REFRESH_EVENT, {
        detail,
      })
    )
  },
  onOfflineReady() {
    console.info("Экосистема ГУУ готова работать офлайн")
  },
  onRegisterError(error: Error) {
    console.error("Service worker registration failed", error)
  },
})

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
