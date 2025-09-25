import React, { useEffect } from "react"
import ReactDOM from "react-dom/client"
import { CssBaseline } from "@mui/material"
import { CssVarsProvider, useColorScheme } from "@mui/material/styles"
import { registerSW } from "virtual:pwa-register"
import App from "./App"
import theme from "./theme"
import "./assets/themes.css"
import "dayjs/locale/ru"

const updateSW = registerSW({
  immediate: true,
  onNeedRefresh() {
    void updateSW(true)
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

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <CssVarsProvider
      theme={theme}
      defaultMode="system"
      modeStorageKey="theme"
      disableTransitionOnChange
    >
      <CssBaseline enableColorScheme />
      <BodyColorSchemeSync />
      <App />
    </CssVarsProvider>
  </React.StrictMode>
)
