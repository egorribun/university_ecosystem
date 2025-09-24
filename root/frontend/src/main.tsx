import React from "react"
import ReactDOM from "react-dom/client"
import { ThemeProvider, CssBaseline } from "@mui/material"
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

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ThemeProvider theme={theme}>
      <CssBaseline enableColorScheme />
      <App />
    </ThemeProvider>
  </React.StrictMode>
)
