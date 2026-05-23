import { useEffect, useRef } from "react"
import { useNavigate, useRouterState } from "@tanstack/react-router"
import ParticleAuthBackground from "@/components/ui/ParticleAuthBackground"
import AuthBackdrop from "@/components/auth/AuthBackdrop"
import useMediaQuery from "@/hooks/useMediaQuery"
import { LoginHero } from "@/components/auth/LoginHero"
import { LoginCredentialForm } from "@/components/auth/LoginCredentialForm"
import { MfaChallengeView } from "@/components/auth/MfaChallengeView"
import { useLoginForm, useMfaFlow } from "@/hooks/auth/useLoginFlow"
import { useAuthStore } from "@/stores/useAuthStore"
import { resolveRedirectPath } from "@/utils/redirect"

const Login = () => {
  const form = useLoginForm()
  const mfa = useMfaFlow()

  // Wave 177 SW1 — close W174 §Honesty #3 edge case (authed user
  // hard-navigates to /login from bookmark / search / external link).
  // useAuthStore.ts:24 initializes loading:true → _public.tsx:19-25
  // beforeLoad returns without redirect → Login renders. Once
  // AuthProvider's useProfileSync settles GET /users/me and calls
  // setUser, this reactive effect catches the user transition null→set
  // and navigates to redirect target with replace:true (no /login in
  // history for authed users). DIFFERS from reverted W175 SW10 by
  // including targeted msw /users/me→401 overrides in the 7 tests that
  // mount Login.tsx (Login.test.tsx renderLogin helper + pageTranslations
  // login case) — see W177 SW2/SW3 + AUDIT_WAVE177.md.
  //
  // Wave 179 SW4 — honor `search.redirect` param (TanStack canonical
  // written by _auth.tsx:47 beforeLoad) to preserve user's intended
  // destination (e.g., /events) across unauth-deflect → re-auth → land
  // on /events (NOT hardcoded /dashboard). Closes W177 §Honesty #3 race.
  // resolveRedirectPath defaults to /dashboard for missing/malformed/
  // cross-origin redirect param (see frontend/src/utils/redirect.ts).
  //
  // redirectedRef guards against re-fire after the initial redirect:
  // navigate({to: target}) clears location.search → useEffect's `search`
  // dep updates → effect re-fires with redirect: undefined → would fall
  // back to /dashboard, overriding the original navigation. Once
  // redirected, the ref blocks subsequent fires from this Login instance.
  // Production: Login typically unmounts on successful navigate; in fast
  // test environments (jsdom + memory history) the effect can re-fire on
  // the still-mounted instance — ref makes both paths deterministic.
  const user = useAuthStore((s) => s.user)
  const navigate = useNavigate()
  const search = useRouterState({ select: (s) => s.location.search })
  const redirectedRef = useRef(false)
  useEffect(() => {
    if (user && !redirectedRef.current) {
      redirectedRef.current = true
      const target = resolveRedirectPath((search as { redirect?: unknown } | null)?.redirect)
      navigate({ to: target, replace: true })
    }
  }, [user, navigate, search])

  // Wave 186 SW3 — useReducedMotion via project's useMediaQuery (jsdom-safe
  // per W184 SW6). MotionConfig at AppProviders (W124 SW1) handles framer-
  // motion globally; explicit prop here is for AuthBackdrop's mobile GPU
  // blur-drop branch (per W183 SW7 + W184 SW5 convention).
  const prefersReducedMotion = useMediaQuery("(prefers-reduced-motion: reduce)")

  // MFA challenge screen — shown when backend requires second factor
  if (mfa.loginChallenge) {
    return (
      <MfaChallengeView
        activeEmail={form.activeEmail}
        trustDevice={!!form.trustDevice}
        onTrustDeviceChange={form.setTrustDevice}
        webauthnSupported={form.webauthnSupported}
        mfa={mfa}
      />
    )
  }

  // Primary login screen — hero panel + credential form. Wave 186 SW3 adds
  // `.auth-theme` scope + AuthBackdrop ambient orbs (teal/cyan) coexisting
  // with ParticleAuthBackground (W113 SW6) — Backdrop = static pixel-anchored
  // orbs at -z-1, particles = ambient canvas overlay.
  return (
    <div className="auth-theme relative min-h-screen w-full overflow-hidden bg-page text-text-primary">
      <AuthBackdrop prefersReducedMotion={prefersReducedMotion} />
      <ParticleAuthBackground />
      <div className="relative z-content mx-auto grid min-h-screen w-full max-w-7xl grid-cols-1 items-stretch gap-12 px-4 py-12 sm:px-6 lg:grid-cols-2 lg:px-8">
        <LoginHero />
        <LoginCredentialForm form={form} />
      </div>
    </div>
  )
}

export default Login
