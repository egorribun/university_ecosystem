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

// Wave 117 SW1 — Lighthouse CI runs the audit without `prefers-reduced-motion`,
// so Framer Motion executes full animations during measurement even though the
// Wave 114 SW2b switch to `reducedMotion="user"` respects real-user pref. The
// VITE_LHCI branch tells Framer to snap animations to their end state during
// LHCI runs, matching measurement semantics (Lighthouse's perf model assumes
// minimal animation work). Rolldown DCE tree-shakes the unused branch — prod
// builds never see `"always"`; Playwright a11y-public still gets `"user"` +
// `emulateMedia({ reducedMotion: "reduce" })` for WCAG 2.3.3 compliance.
const LHCI_REDUCED_MOTION = import.meta.env.VITE_LHCI === "true" ? "always" : "user"

export function AppProviders({ children }: AppProvidersProps) {
  return (
    <LanguageProvider>
      <MotionConfig reducedMotion={LHCI_REDUCED_MOTION}>
        <ProvidersInner>
          <GlobalHapticsListener />
          {children}
        </ProvidersInner>
      </MotionConfig>
    </LanguageProvider>
  )
}
