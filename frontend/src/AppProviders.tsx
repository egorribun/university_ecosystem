import type { ReactNode } from "react"
import { AdapterDayjs } from "@mui/x-date-pickers/AdapterDayjs"
import { LocalizationProvider } from "@mui/x-date-pickers/LocalizationProvider"
import { BrowserRouter as Router } from "react-router-dom"
import type { FutureConfig as RouterDataFutureConfig } from "@remix-run/router"
import type { FutureConfig as RouterComponentFutureConfig } from "react-router"

import ErrorBoundary from "./app/ErrorBoundary"
import { LiveRegionProvider } from "./components/LiveRegionProvider"
import { AppShellProvider } from "./contexts/AppShellContext"
import { AuthProvider } from "./contexts/AuthContext"
import { LanguageProvider, useLanguage } from "./contexts/LanguageContext"

type RouterFutureFlags = Partial<RouterDataFutureConfig> & Partial<RouterComponentFutureConfig>

export const routerFutureFlags = {
  v7_startTransition: true,
  v7_relativeSplatPath: true,
  v7_partialHydration: true,
  v7_fetcherPersist: true,
  v7_normalizeFormMethod: true,
  v7_skipActionErrorRevalidation: true,
} satisfies RouterFutureFlags

interface AppProvidersProps {
  children: ReactNode
}

function ProvidersInner({ children }: AppProvidersProps) {
  const { language } = useLanguage()

  return (
    <LiveRegionProvider>
      <AppShellProvider>
        <AuthProvider>
          <LocalizationProvider key={language} dateAdapter={AdapterDayjs} adapterLocale={language}>
            <ErrorBoundary>
              <Router future={routerFutureFlags}>{children}</Router>
            </ErrorBoundary>
          </LocalizationProvider>
        </AuthProvider>
      </AppShellProvider>
    </LiveRegionProvider>
  )
}

export function AppProviders({ children }: AppProvidersProps) {
  return (
    <LanguageProvider>
      <ProvidersInner>{children}</ProvidersInner>
    </LanguageProvider>
  )
}
