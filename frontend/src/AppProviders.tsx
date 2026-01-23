import type { ReactNode } from "react"
import { AdapterDayjs } from "@mui/x-date-pickers/AdapterDayjs"
import { LocalizationProvider } from "@mui/x-date-pickers/LocalizationProvider"
import { BrowserRouter as Router } from "react-router-dom"

import ErrorBoundary from "./app/ErrorBoundary"
import { LiveRegionProvider } from "./components/LiveRegionProvider"
import { AppShellProvider } from "./contexts/AppShellContext"
import { AuthProvider } from "./contexts/AuthContext"
import { MessengerProvider } from "./contexts/MessengerContext"
import { LanguageProvider, useLanguage } from "./contexts/LanguageContext"

interface AppProvidersProps {
  children: ReactNode
}

function ProvidersInner({ children }: AppProvidersProps) {
  const { language } = useLanguage()

  return (
    <LiveRegionProvider>
      <AppShellProvider>
        <AuthProvider>
          <MessengerProvider>
            <LocalizationProvider
              key={language}
              dateAdapter={AdapterDayjs}
              adapterLocale={language}
            >
              <ErrorBoundary>
                <Router>{children}</Router>
              </ErrorBoundary>
            </LocalizationProvider>
          </MessengerProvider>
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
