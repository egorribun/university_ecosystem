import { useEffect } from "react"
import { useNavigate } from "@tanstack/react-router"
import ParticleAuthBackground from "@/components/ui/ParticleAuthBackground"
import { LoginHero } from "@/components/auth/LoginHero"
import { LoginCredentialForm } from "@/components/auth/LoginCredentialForm"
import { MfaChallengeView } from "@/components/auth/MfaChallengeView"
import { useLoginForm, useMfaFlow } from "@/hooks/auth/useLoginFlow"
import { useAuthStore } from "@/stores/useAuthStore"

const Login = () => {
  const form = useLoginForm()
  const mfa = useMfaFlow()

  // Wave 177 SW1 — close W174 §Honesty #3 edge case (authed user
  // hard-navigates to /login from bookmark / search / external link).
  // useAuthStore.ts:24 initializes loading:true → _public.tsx:19-25
  // beforeLoad returns without redirect → Login renders. Once
  // AuthProvider's useProfileSync settles GET /users/me and calls
  // setUser, this reactive effect catches the user transition null→set
  // and navigates to /dashboard with replace:true (no /login in history
  // for authed users). DIFFERS from reverted W175 SW10 by including
  // targeted msw /users/me→401 overrides in the 7 tests that mount
  // Login.tsx (Login.test.tsx renderLogin helper + pageTranslations
  // login case) — see W177 SW2/SW3 + AUDIT_WAVE177.md.
  const user = useAuthStore((s) => s.user)
  const navigate = useNavigate()
  useEffect(() => {
    if (user) {
      navigate({ to: "/dashboard", replace: true })
    }
  }, [user, navigate])

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

  // Primary login screen — hero panel + credential form
  return (
    <div className="relative min-h-screen w-full overflow-hidden bg-page text-text-primary">
      <ParticleAuthBackground />
      <div className="relative z-content mx-auto grid min-h-screen w-full max-w-7xl grid-cols-1 items-stretch gap-12 px-4 py-12 sm:px-6 lg:grid-cols-2 lg:px-8">
        <LoginHero />
        <LoginCredentialForm form={form} />
      </div>
    </div>
  )
}

export default Login
