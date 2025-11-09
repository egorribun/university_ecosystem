import { initObservability } from "./app/observability"
import { initGlobalErrorHandlers } from "./app/globalErrorHandlers"
import { logError } from "./app/logger"
import { initWebVitals } from "./app/webVitals"
import { ensureTrustedTypesPolicies } from "./utils/trustedTypes"
import { getBootstrapFallbackCopy, renderBootstrapFallback } from "./utils/bootstrapFallback"

initObservability()
initGlobalErrorHandlers()
initWebVitals()
ensureTrustedTypesPolicies()

declare global {
  interface Window {
    __APP_BOOTSTRAP_FORCE_ERROR__?: boolean
  }
}

async function bootstrap() {
  try {
    if (typeof window !== "undefined" && window.__APP_BOOTSTRAP_FORCE_ERROR__) {
      throw new Error("Forced bootstrap failure")
    }

    const ReactMod = await import("react")
    const { StrictMode, useEffect } = ReactMod
    const ReactDOMMod = await import("react-dom/client")
    const { CssBaseline } = await import("@mui/material")
    const StylesMod = await import("@mui/material/styles")
    const { CssVarsProvider, useColorScheme } = StylesMod
    const ReactQueryMod = await import("@tanstack/react-query")
    const { QueryClientProvider } = ReactQueryMod
    const AppMod = await import("./App")
    const { default: App } = AppMod
    const ErrorBoundaryMod = await import("./app/ErrorBoundary")
    const { default: ErrorBoundary } = ErrorBoundaryMod
    const QueryClientLocal = await import("./app/queryClient")
    const { queryClient } = QueryClientLocal
    const ThemeMod = await import("./theme")
    const { default: theme } = ThemeMod
    await import("./styles/tailwind.css")
    await import("./assets/themes.css")
    await import("./i18n/config")
    await import("dayjs/locale/ru")
    const SWMod = await import("./push/register-sw")
    const { registerServiceWorker } = SWMod
    const PushMod = await import("./push/subscribe")
    const { ensurePushSubscription, hasPushConsent } = PushMod

    async function setupServiceWorker() {
      if (!import.meta.env.PROD) return
      if (!("serviceWorker" in navigator)) return
      try {
        const registration = await registerServiceWorker("/sw.js")
        if (!registration) return
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

    const ReactQueryDevtools = import.meta.env.DEV
      ? (await import("@tanstack/react-query-devtools")).ReactQueryDevtools
      : null

    ReactDOMMod.default.createRoot(document.getElementById("root")!).render(
      <StrictMode>
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
          {ReactQueryDevtools ? <ReactQueryDevtools buttonPosition="bottom-left" /> : null}
        </QueryClientProvider>
      </StrictMode>
    )
  } catch (error) {
    logError("Failed to bootstrap application", error)

    if (typeof document === "undefined") {
      return
    }

    const rootElement = document.getElementById("root")
    if (!rootElement) {
      return
    }

    rootElement.innerHTML = ""

    const copy = getBootstrapFallbackCopy(document)

    renderBootstrapFallback({
      documentRef: document,
      rootElement,
      copy,
      logError,
    })
  }
}

bootstrap()
