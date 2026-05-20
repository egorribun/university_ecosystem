import { createFileRoute, Outlet, redirect } from "@tanstack/react-router"
import { useAuthStore } from "@/stores/useAuthStore"

export const Route = createFileRoute("/_public")({
  // Wave 154 SW1 — removed `ssr: false` workaround (W150 polish-followup commit
  // 7c97de583) since W153 SW2 (commit d931492e3) closed the React #418
  // hydration mismatch root cause via SSR-aware `defaultPendingComponent`
  // (router.ts:88, `import.meta.env.SSR ? null : <Loading…>` literal split).
  // `_public.tsx` now inherits `ssr: true` from root (W128 SW2 inheritance
  // contract: child can only be MORE restrictive). If hydration hazards from
  // ParticleAuthBackground canvas, useId form fields, or theme/lang cookies
  // re-fire post-revert, W155+ scope can re-add explicit `ssr: false` here OR
  // SSR-suppress the specific offending component via `import.meta.env.SSR`
  // pattern matching W153 SW2.
  //
  // Wave 174 SW1 — read live Zustand state via useAuthStore.getState()
  // instead of stale `context.auth.*`. See _auth.tsx for full rationale
  // (W152 Phase 1.7 removed the App.tsx reactive context bridge).
  beforeLoad: () => {
    const { user, loading } = useAuthStore.getState()
    if (loading) return
    if (user) {
      throw redirect({ to: "/dashboard" })
    }
  },
  component: () => <Outlet />,
})
