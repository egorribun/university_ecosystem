import ParticleAuthBackground from "@/components/ui/ParticleAuthBackground"
import { LoginHero } from "@/components/auth/LoginHero"
import { LoginCredentialForm } from "@/components/auth/LoginCredentialForm"
import { MfaChallengeView } from "@/components/auth/MfaChallengeView"
import { useLoginForm, useMfaFlow } from "@/hooks/auth/useLoginFlow"

const Login = () => {
  const form = useLoginForm()
  const mfa = useMfaFlow()

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
