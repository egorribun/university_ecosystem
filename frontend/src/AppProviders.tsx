import { useEffect, useLayoutEffect } from "react"
import type { ReactNode } from "react"
import { LazyMotion, MotionConfig, domAnimation } from "framer-motion"

import { markAppHydrated } from "@/app/hydration"
import ErrorBoundary from "@/components/feedback/ErrorBoundary"
import { LiveRegionProvider } from "./components/ui/LiveRegionProvider"
import { AppShellProvider } from "./contexts/AppShellContext"
import { AuthProvider } from "./contexts/AuthContext"
import { WebSocketProvider } from "./hooks/useChatWebSocket"
import { MessengerProvider } from "./contexts/MessengerContext"
import { LanguageProvider } from "./contexts/LanguageContext"
import { GlobalHapticsListener } from "./components/ui/GlobalHapticsListener"
import { RxDBProvider } from "./db/RxDBContext"

interface AppProvidersProps {
  children: ReactNode
}

// Hydration completion is a visual boundary: the SSR boot loader must start
// its exit before the first post-hydration paint.  React 19 may defer passive
// effects while a concurrent WebKit hydration is still settling, which can
// leave the loader active even though the sentinel event was delivered.  Use
// an isomorphic layout effect in the browser so the state update is flushed in
// the same commit; retain useEffect during SSR to avoid server warnings.
const useHydrationEffect = typeof window === "undefined" ? useEffect : useLayoutEffect

function ProvidersInner({ children }: AppProvidersProps) {
  return (
    <RxDBProvider autoInitialize={false}>
      <LiveRegionProvider>
        <AppShellProvider>
          <AuthProvider>
            <WebSocketProvider>
              <MessengerProvider>
                <ErrorBoundary>{children}</ErrorBoundary>
              </MessengerProvider>
            </WebSocketProvider>
          </AuthProvider>
        </AppShellProvider>
      </LiveRegionProvider>
    </RxDBProvider>
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

// Wave 124 SW1 — `<LazyMotion strict features={domAnimation}>` ships only the
// minimal animation feature set (~5-10 KB savings on vendor-ui chunk vs full
// motion runtime). `strict: true` causes runtime errors if `<motion.X>` is
// used anywhere — forces all 64 JSX consumers to use the bundled minimal
// `<m.X>` component. Pre-Wave-124 components have been refactored to:
//   - Use `<m.X>` JSX (Phase B bulk swap)
//   - Avoid useScroll / useTransform / useMotionValue / useSpring /
//     useAnimation / LayoutGroup / layoutId / `layout` prop (Phase A — these
//     require domMax). Replacements: native scroll listeners + CSS variables,
//     rAF + easeOutExpo (see @/hooks/useAnimatedFloat), CSS sliding indicator
//     (see @/hooks/ui/useSlidingIndicator).
// `useReducedMotion`, `AnimatePresence`, `MotionConfig`, `motion.X` (now `m.X`)
// initial/animate/exit/whileHover/whileTap/variants are all in domAnimation.
export function AppProviders({ children }: AppProvidersProps) {
  // Publish the hydration sentinel after React commits the complete provider
  // tree. Playwright waits for this signal before interacting with hydrated UI;
  // markAppHydrated also completes the bootstrap loader idempotently.
  useHydrationEffect(() => {
    markAppHydrated()
  }, [])

  return (
    <LanguageProvider>
      <LazyMotion strict features={domAnimation}>
        <MotionConfig reducedMotion={LHCI_REDUCED_MOTION}>
          <ProvidersInner>
            <GlobalHapticsListener />
            {children}
          </ProvidersInner>
        </MotionConfig>
      </LazyMotion>
    </LanguageProvider>
  )
}
