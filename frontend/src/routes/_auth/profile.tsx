import { createFileRoute } from "@tanstack/react-router"
import { lazy } from "react"
import * as v from "valibot"
import { currentUserQueryOptions } from "@/api/hooks/users"
import { profileSearchSchema } from "@/features/profile/schema"

const Profile = lazy(() => import("@/pages/Profile"))

export const Route = createFileRoute("/_auth/profile")({
  validateSearch: (search: Record<string, unknown>) => v.parse(profileSearchSchema, search),
  // Wave 133 SW4 — SSR enabled by inheriting parent _auth.tsx ssr:true
  // (W128 SW2). The page is verified SSR-safe per W133 SW3 plan
  // exploration: window.matchMedia call at top-level is guarded with
  // typeof window !== "undefined"; everything else runs in useEffect.
  //
  // Loader prefetches /users/me so the page can render the auth-aware
  // ProfileHeader server-side instead of a skeleton. Per-subpage data
  // (notification prefs, MFA status, sessions list, etc.) is NOT
  // prefetched in this wave — those are W134+ scope per the W133 design
  // doc honest deferral #1.
  //
  // Browser path uses withCredentials. Node SSR uses W133 SW1
  // requestCookieStorage via the axios interceptor.
  loader: async ({ context }) =>
    Promise.allSettled([context.queryClient.ensureQueryData(currentUserQueryOptions())]),
  component: Profile,
})
