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
  const hideFooter = HIDE_FOOTER_PREFIXES.some((p) => path.startsWith(p))

  return {
    isCompactPage,
    isMessenger,
    hideFooter,
    loading: false, // Future proofing if we need async check
  }
}
