import { useRouterState } from "@tanstack/react-router"

// Wave 176 SW1 — `hideFooter` now also matches `/messenger` (chat fills the
// viewport with its own scroll context; footer would push the message list
// below the fold). Pre-W176, Footer.tsx maintained its own `isAuthPage` array
// that included /messenger; the duplicate list drifted from `useRouteType`'s
// `isCompactPage` (which separately covers /reset-password). Consolidating into
// a single source of truth eliminates the divergence + makes future
// footer-hiding routes a 1-line edit.
const HIDE_FOOTER_PREFIXES = ["/map", "/schedule", "/messenger"] as const

export function useRouteType() {
  const path = useRouterState({ select: (s) => s.location.pathname })

  const isCompactPage = ["/login", "/register", "/forgot-password", "/reset-password"].some((p) =>
    path.startsWith(p)
  )

  const isMessenger = path.startsWith("/messenger")
  // Wave 184 SW5 (Path D) — flag for /profile route enables MainLayout (and
  // any future global chrome) to scope rose-palette decoration to this surface
  // only. Same single-source-of-truth pattern as `isMessenger` per W176 SW1.
  const isProfile = path.startsWith("/profile")
  // Wave 184 SW6 (Path D) — same as isProfile but for /settings polish arc.
  const isSettings = path.startsWith("/settings")
  // Wave 186 SW2 (Path C) — flag for auth pages (/login + /register +
  // /forgot-password + /reset-password). Currently identical to
  // isCompactPage's route set (same 4 prefixes), but kept as a separate
  // concept so adding/removing auth routes doesn't affect compact-page
  // layout logic. Used by AuthBackdrop mount conditions in Login +
  // Register + ForgotPassword + ResetPassword (SW3 integration).
  const isAuth = isCompactPage
  const hideFooter = HIDE_FOOTER_PREFIXES.some((p) => path.startsWith(p))

  return {
    isCompactPage,
    isMessenger,
    isProfile,
    isSettings,
    isAuth,
    hideFooter,
    loading: false, // Future proofing if we need async check
  }
}
