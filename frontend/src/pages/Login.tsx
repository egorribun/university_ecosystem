import { useEffect, useRef } from "react"
import { useNavigate, useRouterState } from "@tanstack/react-router"
import "@/styles/tokens/auth.css"
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

  // MFA challenge screen — shown when backend requires second factor
  if (mfa.loginChallenge) {
    return <MfaChallengeView activeEmail={form.activeEmail} mfa={mfa} />
  }

  return (
    <div className="auth-theme min-h-screen bg-page text-text-primary">
      <main className="auth-shell auth-shell--login" aria-labelledby="login-heading">
        <LoginCredentialForm form={form} />
      </main>
    </div>
  )
}

export default Login
