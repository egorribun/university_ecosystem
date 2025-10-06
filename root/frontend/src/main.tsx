import { ensureTrustedTypesPolicies } from "./utils/trustedTypes"

ensureTrustedTypesPolicies()

async function bootstrap() {
  const ReactMod = await import("react")
  const { StrictMode, Suspense, useEffect } = ReactMod
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
  const { lazyDevtools, queryClient } = QueryClientLocal
  const ThemeMod = await import("./theme")
  const { default: theme } = ThemeMod
  await import("./assets/themes.css")
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
        {ReactQueryDevtools ? (
          <Suspense fallback={null}>
            <ReactQueryDevtools buttonPosition="bottom-left" />
          </Suspense>
        ) : null}
      </QueryClientProvider>
    </StrictMode>
  )
}

bootstrap()
