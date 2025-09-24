import React from "react"
import ReactDOM from "react-dom/client"
import { CssBaseline } from "@mui/material"
import { CssVarsProvider, type CssVarsTheme } from "@mui/material/styles"
import InitColorSchemeScript from "@mui/material/InitColorSchemeScript"
import App from "./App"
import theme from "./theme"
import "./assets/themes.css"
import "dayjs/locale/ru"

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <InitColorSchemeScript defaultMode="system" />
    <CssVarsProvider
      theme={theme as unknown as CssVarsTheme}
      defaultMode="system"
      modeStorageKey="mui-mode"
      colorSchemeStorageKey="mui-color-scheme"
      disableTransitionOnChange
    >
      <CssBaseline enableColorScheme />
      <App />
    </CssVarsProvider>
  </React.StrictMode>
)
