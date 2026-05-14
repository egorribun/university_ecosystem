import { createFileRoute, Outlet, redirect } from "@tanstack/react-router"

export const Route = createFileRoute("/_public")({
  // W150 polish-followup: public auth routes (login/register/forgot-password)
  // are interactive forms with no useful SSR content (heavy ParticleAuthBackground
  // canvas, useId-driven form fields, theme/lang cookie-derived state — all of
  // which are hydration-mismatch hazards). Mirror _auth.tsx + _admin.tsx pattern
  // (W128 SW2 inheritance contract: child can ONLY make MORE restrictive).
  // Resolves React error #418 hydration mismatch on /login post-W149 SW2 hydrateRoot.
  ssr: false,
  beforeLoad: ({ context }) => {
    if (context.auth.loading) return
    if (context.auth.isAuth) {
      throw redirect({ to: "/dashboard" })
    }
  },
  component: () => <Outlet />,
})
