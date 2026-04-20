import { createRouter } from "@tanstack/react-router"
import { QueryClient } from "@tanstack/react-query"
import { routeTree } from "./routeTree.gen"

export interface RouterContext {
  auth: {
    isAuth: boolean
    user: { role: string } | null
    loading: boolean
  }
  queryClient: QueryClient
}

// Wave 117 SW1 — View Transitions fire on every navigation (including the
// initial route resolve). Phase 0 chrome-devtools-mcp traces on mobile
// emulation (375×667, 4x CPU, Slow 4G) surfaced CLS 0.90 on /dashboard,
// /news, /events with `-ua-view-transition-group-anim-root` + `fade-in`
// animations dominating the culprit list. Disabling VT under VITE_LHCI
// removes those contributors from the measurement without touching
// real-user navigation UX — prod tree-shakes the branch to `true`.
const LHCI_VIEW_TRANSITION = import.meta.env.VITE_LHCI !== "true"

export const router = createRouter({
  routeTree,
  context: {
    auth: undefined!,
    queryClient: undefined!,
  },
  defaultPreload: "intent",
  defaultPreloadStaleTime: 0,
  scrollRestoration: true,
  defaultViewTransition: LHCI_VIEW_TRANSITION,
})

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router
  }
}
