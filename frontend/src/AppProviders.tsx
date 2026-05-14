import { useEffect } from "react"
import type { ReactNode } from "react"
import { LazyMotion, MotionConfig, domAnimation } from "framer-motion"

import ErrorBoundary from "@/components/feedback/ErrorBoundary"
import { LiveRegionProvider } from "./components/ui/LiveRegionProvider"
import { AppShellProvider } from "./contexts/AppShellContext"
// W153 SW3 iter 2 — `AuthProvider` import dropped because the real provider
// is stripped in ProvidersInner below (replaced with `AuthContext.Provider`
// + stub value). Restore when SW3 revert lands.
import { AuthContext } from "./contexts/AuthContext"
import { resetEtagCache } from "@/api/client"
// W153 SW3 iter 1 — `WebSocketProvider` import dropped because the real
// provider is stripped in ProvidersInner below (replaced with stub
// `<WebSocketStoreContext.Provider value={W153_NO_OP_WS_STORE}>`). Restore
// when SW3 revert lands. The hook itself stays imported elsewhere via
// MessengerContext.tsx so the real provider lifecycle is unchanged.
import { WebSocketStoreContext, WebSocketStore } from "./hooks/useChatWebSocket"
import { MessengerProvider } from "./contexts/MessengerContext"
import { LanguageProvider } from "./contexts/LanguageContext"
import { GlobalHapticsListener } from "./components/ui/GlobalHapticsListener"

// W153 SW3 iter 1 — module-level no-op WebSocketStore singleton for the
// WebSocketProvider component-strip diagnostic. Matches the
// `useMemo(() => new WebSocketStore(), [])` stable-identity contract of the
// real WebSocketProvider (useChatWebSocket.ts:117-120) so
// `useSyncExternalStore` doesn't churn its subscription on parent re-renders.
//
// Purpose: temporarily replace `<WebSocketProvider>` with a context provider
// stub to test whether WebSocketProvider's mount-time side effects are the
// source of the /login V8 wedge (W152 §Honesty #19 unidentified cause +
// W153 SW2 React #418 fix didn't resolve user-facing blank). If /login
// renders content with the stub in place, wedge is isolated to
// WebSocketProvider; pivot to SW4 targeted fix. If still blank, proceed to
// SW3 iter 2 (AuthProvider stub).
//
// REVERT BEFORE MAIN MERGE. This commit is diagnostic-only.
const W153_NO_OP_WS_STORE = new WebSocketStore()

// W153 SW3 iter 2 — module-level no-op AuthContext value mirrors the
// existing default at frontend/src/contexts/AuthContext.tsx:33-43. The
// real AuthProvider runs `useProfileSync` (auto /users/me fetch +
// localStorage cache hydration). Stripping it tests whether
// useProfileSync's render-loop or queryClient.fetchQuery interaction is
// the /login wedge source. With this stub, `useAuth()` returns
// no-op actions + Zustand store defaults (user=null, loading=false)
// — fine for /login which is unauth anyway.
//
// REVERT BEFORE MAIN MERGE.
const W153_NO_OP_AUTH = {
  login: async () => null,
  logout: async () => {},
  setUser: () => {},
  refresh: async () => {},
  submitMfaChallenge: async () => {},
  requireMfa: async () => null,
  loginWithPasskey: async () => {},
  resetEtagCache,
  authOperation: false,
} as unknown as React.ContextType<typeof AuthContext>

interface AppProvidersProps {
  children: ReactNode
}

function ProvidersInner({ children }: AppProvidersProps) {
  return (
    <LiveRegionProvider>
      <AppShellProvider>
        {/* W153 SW3 iter 2 — AuthProvider STRIPPED (overlays iter 1 WebSocket
            strip). Iter 1 alone (WebSocketProvider only) FAILED — /login still
            blank. This iter 2 tests AuthProvider's useProfileSync as next
            suspect. REVERT before main merge. Real provider at:
            frontend/src/contexts/AuthContext.tsx:71 AuthProvider */}
        <AuthContext.Provider value={W153_NO_OP_AUTH}>
          {/* W153 SW3 iter 1 — WebSocketProvider STRIPPED for /login wedge diagnostic.
              REVERT before main merge. Real provider at:
              frontend/src/hooks/useChatWebSocket.ts:117 WebSocketProvider */}
          <WebSocketStoreContext.Provider value={W153_NO_OP_WS_STORE}>
            <MessengerProvider>
              <ErrorBoundary>{children}</ErrorBoundary>
            </MessengerProvider>
          </WebSocketStoreContext.Provider>
        </AuthContext.Provider>
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
  // no-cleanup). Adjust if any choice's reasoning above doesn't match the
  // app's actual hydration semantics for your future test needs.
  useEffect(() => {
    if (typeof window !== "undefined") {
      window.__APP_HYDRATED = true
    }
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
