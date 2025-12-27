import { initObservability } from "./app/observability"
import { initGlobalErrorHandlers } from "./app/globalErrorHandlers"
import { logError } from "./app/logger"
import { initWebVitals, reportBootstrapTTI } from "./app/webVitals"
import { ensureTrustedTypesPolicies } from "./utils/trustedTypes"
import { getBootstrapFallbackCopy, renderBootstrapFallback } from "./utils/bootstrapFallback"

initObservability()
initGlobalErrorHandlers()
const webVitalsEnabled = initWebVitals()
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

    const bootstrapStart =
      typeof performance !== "undefined" && typeof performance.now === "function"
        ? performance.now()
        : undefined

    const [
      ReactMod,
      ReactDOMMod,
      MuiCssBaselineMod,
      MuiCssVarsProviderMod,
      MuiUseColorSchemeMod,
      ReactQueryMod,
      AppMod,
      ErrorBoundaryMod,
      QueryClientLocal,
      ThemeMod,
    ] = await Promise.all([
      import("react"),
      import("react-dom/client"),
      import("@mui/material/CssBaseline"),
      import("@mui/material/styles/CssVarsProvider"),
      import("@mui/material/styles/useColorScheme"),
      import("@tanstack/react-query"),
      import("./App"),
      import("./app/ErrorBoundary"),
      import("./app/queryClient"),
      import("./theme"),
    ])

    const { StrictMode, useEffect } = ReactMod
    const { default: CssBaseline } = MuiCssBaselineMod
    const { default: CssVarsProvider } = MuiCssVarsProviderMod
    const { default: useColorScheme } = MuiUseColorSchemeMod
    const { QueryClientProvider } = ReactQueryMod
    const { default: App } = AppMod
    const { default: ErrorBoundary } = ErrorBoundaryMod
    const { queryClient } = QueryClientLocal
    const { default: theme } = ThemeMod

    await Promise.all([
      import("./styles/tailwind.css"),
      import("./assets/themes.css"),
      import("./i18n/config"),
      import("dayjs/locale/ru"),
    ])

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

    const rootElement = document.getElementById("root")!
    const root = ReactDOMMod.default.createRoot(rootElement)
    root.render(
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
        </QueryClientProvider>
      </StrictMode>
    )

    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        rootElement.classList.add("ready")
      })
    })

    if (webVitalsEnabled && typeof window !== "undefined") {
      const report = () => {
        if (!bootstrapStart) {
          return
        }

        const bootstrapEnd =
          typeof performance !== "undefined" && typeof performance.now === "function"
            ? performance.now()
            : undefined

        if (!bootstrapEnd) {
          return
        }

        reportBootstrapTTI(bootstrapEnd - bootstrapStart)
      }

      if (typeof window.requestIdleCallback === "function") {
        window.requestIdleCallback(report)
      } else {
        window.setTimeout(report, 0)
      }
    }
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
