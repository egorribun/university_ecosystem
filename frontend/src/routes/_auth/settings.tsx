import { createFileRoute } from "@tanstack/react-router"
import { lazy } from "react"
import * as v from "valibot"
import { currentUserQueryOptions } from "@/api/hooks/users"
import { sessionsQueryOptions } from "@/api/hooks/sessions"
import { settingsSearchSchema, SETTINGS_TAB } from "@/features/settings/schema"

const Settings = lazy(() => import("@/pages/Settings"))

export const Route = createFileRoute("/_auth/settings")({
  // Wave 133 SW5 — SSR enabled by inheriting parent _auth.tsx ssr:true
  // (W128 SW2). The page is verified SSR-safe per W133 SW3 plan
  // exploration: top-level component is a tab-routing shell; only
  // useSearch + useState + useRef at render. Spotify-callback handler
  // (Settings.tsx:50-75) lives inside useEffect → SSR-safe.
  //
  // Wave 134 SW2 — added validateSearch (Valibot tab + spotify) so the
  // tab index becomes a deep-linkable URL param (?tab=2 lands on
  // Security; ?tab=4 lands on Sessions). loaderDeps surfaces the
  // tab value to the loader for conditional prefetch decisions. The
  // dedicated Sessions tab is the only one that also prefetches the
  // sessions endpoint; all other tabs need only /users/me.
  //
  // Browser path uses withCredentials. Node SSR uses W133 SW1
  // requestCookieStorage via the axios interceptor.
  validateSearch: (search: Record<string, unknown>) => v.parse(settingsSearchSchema, search),
  loaderDeps: ({ search }) => ({ tab: search.tab }),
  loader: async ({ context, deps }) => {
    const userResult = await context.queryClient
      .ensureQueryData(currentUserQueryOptions())
      .catch(() => null)

    if (deps.tab === SETTINGS_TAB.SESSIONS && userResult?.id) {
      // Sessions tab — prefetch sessions list. Best-effort: any
      // failure (backend down, expired session) does not block the
      // loader, the sessions tab will fall back to its client-side
      // useQuery which fires when tabActive becomes true. Mirrors
      // W128 SW3-followup Promise.allSettled pattern.
      await context.queryClient
        .ensureQueryData(sessionsQueryOptions(userResult.id))
        .catch(() => undefined)
    }

    return null
  },
  component: Settings,
})
