import type { ReactNode } from "react"

import ErrorBoundary from "@/components/feedback/ErrorBoundary"
import { LiveRegionProvider } from "./components/ui/LiveRegionProvider"
import { AppShellProvider } from "./contexts/AppShellContext"
import { AuthProvider } from "./contexts/AuthContext"
import { WebSocketProvider } from "./hooks/useChatWebSocket"
import { MessengerProvider } from "./contexts/MessengerContext"
import { LanguageProvider } from "./contexts/LanguageContext"
import { GlobalHapticsListener } from "./components/ui/GlobalHapticsListener"

interface AppProvidersProps {
  children: ReactNode
}

function ProvidersInner({ children }: AppProvidersProps) {
  return (
    <LiveRegionProvider>
      <AppShellProvider>
        <AuthProvider>
          <WebSocketProvider>
            <MessengerProvider>
              <ErrorBoundary>
                {children}
              </ErrorBoundary>
            </MessengerProvider>
          </WebSocketProvider>
        </AuthProvider>
      </AppShellProvider>
    </LiveRegionProvider>
  )
}

export function AppProviders({ children }: AppProvidersProps) {
  return (
    <LanguageProvider>
      <ProvidersInner>
        <GlobalHapticsListener />
        {children}
      </ProvidersInner>
    </LanguageProvider>
  )
}
