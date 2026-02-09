import type { ReactNode } from "react"
import { BrowserRouter as Router } from "react-router-dom"

import ErrorBoundary from "./app/ErrorBoundary"
import { LiveRegionProvider } from "./components/LiveRegionProvider"
import { AppShellProvider } from "./contexts/AppShellContext"
import { AuthProvider } from "./contexts/AuthContext"
import { MessengerProvider } from "./contexts/MessengerContext"
import { LanguageProvider } from "./contexts/LanguageContext"

interface AppProvidersProps {
  children: ReactNode
}

function ProvidersInner({ children }: AppProvidersProps) {
  return (
    <LiveRegionProvider>
      <AppShellProvider>
        <AuthProvider>
          <MessengerProvider>
            <ErrorBoundary>
              <Router>{children}</Router>
            </ErrorBoundary>
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




