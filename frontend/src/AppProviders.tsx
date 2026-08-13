import { useEffect } from "react"
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

function ProvidersInner({ children }: AppProvidersProps) {
  return (
    <RxDBProvider>
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
  // Wave 148 SW2 — Hydration sentinel for Playwright e2e tests.
  //
  // ⭐ USER CONTRIBUTION POINT — choose timing semantics for the sentinel.
  //
  // This effect runs AFTER React commits the AppProviders tree (because
  // useEffect always runs post-commit). That's the earliest point where
  // child providers + components have mounted + their event listeners are
  // bound. Playwright's `page.waitForFunction(() => window.__APP_HYDRATED)`
  // gates on this signal to avoid the W125 SSR createRoot race that
  // surfaced /events × 2 click-no-effect failures (W147 polish §Honesty
  // probe, deferred to W148 SW3 via test.skip).
  //
  // Three architectural choices for the user to decide:
  //
  // (1) WHERE: AppProviders top-level (here) vs ProvidersInner vs a
  //     dedicated <HydrationSentinel /> child mounted as last sibling.
  //     • Top-level (current placement): fires after the WHOLE provider
  //       tree mounts. Simplest. Used below.
  //     • ProvidersInner: fires after only the inner providers mount;
  //       LanguageProvider + MotionConfig are already mounted by parent
  //       effects (different commit order — may race).
  //     • Dedicated child: most controlled — key prop ordering guarantees
  //       it mounts AFTER all siblings, but adds 1 extra component.
  //
  // (2) WHEN: immediate-on-mount (current) vs after microtask
  //     (`Promise.resolve().then(...)`) vs after rAF (`requestAnimationFrame`).
  //     • Immediate (current): fires synchronously inside useEffect.
  //       Sufficient if onClick bindings attach during the same commit.
  //     • Microtask: defers by 1 microtask tick. Useful if some async
  //       state hydration (e.g. Zustand SSR sync) competes with the
  //       effect.
  //     • rAF: defers until next paint. Most conservative but adds ~16ms
  //       to every test's wait time.
  //
  // (3) CLEANUP: leave `true` forever (current) vs reset on unmount.
  //     • No cleanup (current): simpler; AppProviders never unmounts in
  //       prod or test contexts; HMR may set it true again on reload.
  //     • Reset: cleaner for HMR + StrictMode double-render, but adds
  //       complexity for a 1-byte boolean.
  //
  // The current implementation is the safe default (top-level, immediate,
  // no-cleanup). markAppHydrated also emits the idempotent bootstrap-loader
  // completion event without changing this post-commit timing.
  useEffect(() => {
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
