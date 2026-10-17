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

  // If an authenticated user opens /login directly, wait for profile sync
  // before navigating to the validated destination. `replace` keeps /login
  // out of history, and the redirect guard below prevents the fallback target
  // from overriding the requested destination when navigation clears search.
  // Tests that need the login form to remain visible return 401 from /users/me.
  //
  // Honor `search.redirect` (written by _auth.tsx beforeLoad) to preserve the
  // user's intended destination across sign-out deflection and re-authentication
  // instead of always using /dashboard.
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
