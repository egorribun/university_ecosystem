import { initObservability } from "./app/observability"
import { initGlobalErrorHandlers } from "./app/globalErrorHandlers"
import { logError } from "./app/logger"
import { initWebVitals } from "./app/webVitals"
import { ensureTrustedTypesPolicies } from "./utils/trustedTypes"

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

    const container = document.createElement("div")
    container.setAttribute("role", "alert")
    container.style.display = "flex"
    container.style.flexDirection = "column"
    container.style.alignItems = "center"
    container.style.justifyContent = "center"
    container.style.minHeight = "100vh"
    container.style.padding = "2rem"
    container.style.gap = "1.5rem"
    container.style.textAlign = "center"
    container.style.backgroundColor = "#f5f5f5"

    const title = document.createElement("h1")
    title.textContent = "Не удалось загрузить приложение"
    title.style.margin = "0"
    title.style.fontSize = "1.75rem"

    const description = document.createElement("p")
    description.textContent =
      "Попробуйте перезагрузить страницу или очистить кэш браузера. Если проблема сохраняется, обратитесь в поддержку."
    description.style.margin = "0"
    description.style.maxWidth = "32rem"
    description.style.color = "#333"

    const actions = document.createElement("div")
    actions.style.display = "flex"
    actions.style.flexWrap = "wrap"
    actions.style.gap = "1rem"
    actions.style.justifyContent = "center"

    const reloadButton = document.createElement("button")
    reloadButton.type = "button"
    reloadButton.textContent = "Перезагрузить страницу"
    reloadButton.style.padding = "0.75rem 1.5rem"
    reloadButton.style.fontSize = "1rem"
    reloadButton.style.borderRadius = "9999px"
    reloadButton.style.border = "none"
    reloadButton.style.cursor = "pointer"
    reloadButton.style.backgroundColor = "#1976d2"
    reloadButton.style.color = "#fff"
    reloadButton.addEventListener("click", () => {
      window.location.reload()
    })

    const clearCacheButton = document.createElement("button")
    clearCacheButton.type = "button"
    clearCacheButton.textContent = "Очистить кэш и перезагрузить"
    clearCacheButton.style.padding = "0.75rem 1.5rem"
    clearCacheButton.style.fontSize = "1rem"
    clearCacheButton.style.borderRadius = "9999px"
    clearCacheButton.style.border = "1px solid #1976d2"
    clearCacheButton.style.cursor = "pointer"
    clearCacheButton.style.backgroundColor = "transparent"
    clearCacheButton.style.color = "#1976d2"
    clearCacheButton.addEventListener("click", () => {
      clearCacheButton.disabled = true
      clearCacheButton.textContent = "Очищаем кэш..."

      void (async () => {
        try {
          if ("serviceWorker" in navigator) {
            const registrations = await navigator.serviceWorker.getRegistrations()
            await Promise.all(registrations.map((registration) => registration.unregister()))
          }
          if ("caches" in window) {
            const cacheKeys = await caches.keys()
            await Promise.all(cacheKeys.map((cacheKey) => caches.delete(cacheKey)))
          }
        } catch (cleanupError) {
          logError("Failed to clear caches after bootstrap error", cleanupError)
        } finally {
          window.location.reload()
        }
      })()
    })

    actions.append(reloadButton, clearCacheButton)

    container.append(title, description, actions)

    rootElement.append(container)
  }
}

bootstrap()
