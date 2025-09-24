import React from "react"
import ReactDOM from "react-dom/client"
import { ThemeProvider, CssBaseline } from "@mui/material"
import App from "./App"
import theme from "./theme"
import "./assets/themes.css"
import "dayjs/locale/ru"

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ThemeProvider theme={theme}>
      <CssBaseline enableColorScheme />
      <App />
    </ThemeProvider>
  </React.StrictMode>
)
