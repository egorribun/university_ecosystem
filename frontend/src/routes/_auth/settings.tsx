import { createFileRoute } from "@tanstack/react-router"
import { lazy } from "react"
import { currentUserQueryOptions } from "@/api/hooks/users"

const Settings = lazy(() => import("@/pages/Settings"))

export const Route = createFileRoute("/_auth/settings")({
  // Wave 133 SW5 — SSR enabled by inheriting parent _auth.tsx ssr:true
  // (W128 SW2). The page is verified SSR-safe per W133 SW3 plan
  // exploration: top-level component is a tab-routing shell (4 subpages:
  // General/Profile/Security/Integrations); only useSearch + useState +
  // useRef at render. The Spotify-callback handler at line 50-75 lives
  // inside useEffect → SSR-safe.
  //
  // Loader prefetches /users/me so the tab shell can render the auth
  // context server-side. Per-subpage data (Spotify integration status,
  // notification preferences, MFA setup state, etc.) is NOT prefetched
  // in this wave — those are W134+ scope per the W133 design doc
  // honest deferral #1.
  //
  // Browser path uses withCredentials. Node SSR uses W133 SW1
  // requestCookieStorage via the axios interceptor.
  loader: async ({ context }) =>
    Promise.allSettled([context.queryClient.ensureQueryData(currentUserQueryOptions())]),
  component: Settings,
})
