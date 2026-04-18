import type { ReactNode } from "react"
import { MotionConfig } from "framer-motion"

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
      {/* `reducedMotion="user"` makes Framer Motion honour the OS
          `prefers-reduced-motion` setting — animations snap to their end
          state when the user has opted in. WCAG 2.3.3 improvement (Level
          AAA) + eliminates the 900ms Framer settle wait previously needed
          by `tests/e2e/a11y-public.spec.ts` (A11Y-113-03 closed). */}
      <MotionConfig reducedMotion="user">
        <ProvidersInner>
          <GlobalHapticsListener />
          {children}
        </ProvidersInner>
      </MotionConfig>
    </LanguageProvider>
  )
}
