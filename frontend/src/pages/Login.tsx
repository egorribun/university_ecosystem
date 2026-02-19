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
<<<<<<< HEAD
      <div className="relative z-navbar mx-auto grid min-h-screen w-full max-w-7xl grid-cols-1 items-stretch gap-12 px-4 py-12 sm:px-6 lg:grid-cols-2 lg:px-8">
        <FadeIn
          direction="left"
          distance={200}
          duration={0.5}
          className="auth-card-glass flex w-full min-w-0 flex-col justify-center p-8 lg:p-12"
        >
          <p
            className="text-sm font-semibold uppercase text-text-primary/(--opacity-strong)"
            style={{ letterSpacing: "0.3em" }}
          >
            {t("auth:login.hero.badge")}
          </p>
          <h1 className="mt-4 text-4xl font-extrabold leading-tight text-text-primary sm:text-5xl">
            {t("auth:login.hero.heading")}
          </h1>
          <p className="mt-4 text-lg leading-relaxed text-text-secondary">
            {t("auth:login.hero.description")}
          </p>

          <div className="mt-8 grid gap-4 sm:grid-cols-2">
            {heroHighlights.map(({ icon: Icon, title, description }) => (
              <div
                key={title}
                className="auth-perk-card group"
              >
                <div className="relative z-base flex items-center gap-3">
                  <span className="flex size-12 items-center justify-center rounded-md bg-brand-subtle-bg text-brand">
                    <Icon className="h-5 w-5" aria-hidden="true" />
                  </span>
                  <p className="text-base font-semibold">{title}</p>
                </div>
                <p className="mt-4 text-sm text-text-secondary">{description}</p>
              </div>
            ))}
          </div>

          <div className="mt-10 flex flex-wrap gap-4">
            <div className="auth-stat-glass w-40">
              <Zap className="mr-1 h-4 w-4 text-brand" strokeWidth={3} />
              <span
                className="text-xs font-extrabold uppercase"
                style={{ letterSpacing: "0.2em" }}
              >
                {t("auth:login.statFast", { defaultValue: "Быстро" })}
              </span>
              <span
                className="text-xs font-extrabold uppercase ml-1"
                style={{ letterSpacing: "0.2em" }}
              >
                {t("auth:login.statFastLabel", { defaultValue: "и безопасно" })}
              </span>
            </div>
            <div className="auth-stat-glass w-40">
              <Sparkles className="mr-1 h-4 w-4 text-brand" strokeWidth={3} />
              <span
                className="text-xs font-extrabold uppercase"
                style={{ letterSpacing: "0.2em" }}
              >
                {t("auth:login.statSmart", { defaultValue: "Умный интерфейс" })}
              </span>
            </div>
          </div>
        </FadeIn>

        <FadeIn
          direction="up"
          distance={200}
          duration={0.5}
          delay={0.2}
          className="auth-card-glass flex w-full min-w-0 flex-col justify-center bg-surface/(--opacity-hover) p-6 sm:p-10"
        >
          <form noValidate autoComplete="on" action={submitAction} className="flex flex-col gap-6">
            <div className="space-y-2 text-center">
              <h2 className="text-3xl font-extrabold">{t("auth:login.title")}</h2>
              <p className="text-sm text-text-secondary">
                {t("auth:login.subtitle", {
                  defaultValue: "Войдите, чтобы продолжить путешествие по университету",
                })}
              </p>
            </div>

            <div className="space-y-2">
              <label htmlFor="username" className="text-sm font-semibold text-text-primary">
                {t("auth:fields.email")}
              </label>
              <Input
                id="username"
                name="username"
                type="email"
                className={!emailValid ? "border-error-text focus:border-error-text" : ""}
                defaultValue={savedEmail}
                ref={(el) => {
                  emailRef.current = el
                  if (el) {
                    setTimeout(() => el.focus(), 0)
                  }
                }}
                onChange={(event) => setEmailMirror(event.target.value)}
                onBlur={handleEmailBlur}
                autoComplete="username"
                disabled={isPending || submitting}
                inputMode="email"
                required
              />
              <p className="text-xs text-text-secondary/(--opacity-hover)">
                {!emailValid ? t("auth:messages.invalidFormat") : " "}
              </p>
              {emailSuggestion ? (
                <button
                  type="button"
                  onClick={applySuggestion}
                  className="inline-flex items-center gap-2 rounded-full border border-border-focus/(--opacity-strong) px-4 py-2 text-xs font-semibold uppercase text-brand transition hover:bg-brand-subtle"
                  style={{ letterSpacing: "0.2em" }}
                >
                  <Sparkles className="h-4 w-4" aria-hidden="true" />
                  {t("auth:messages.emailSuggestion", { suggestion: emailSuggestion })}
                </button>
              ) : null}
            </div>

            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <label htmlFor="password" className="text-sm font-semibold">
                  {t("auth:fields.password")}
                </label>
                <button
                  type="button"
                  onMouseDown={() => setShowPassword(true)}
                  onMouseUp={() => setShowPassword(false)}
                  onMouseLeave={() => setShowPassword(false)}
                  onClick={() => setShowPassword((v) => !v)}
                  className="inline-flex items-center gap-2 rounded-full border border-transparent px-3 py-1 text-xs font-bold uppercase tracking-widest text-brand transition focus:outline-none focus:ring-2 focus:ring-brand/20"
                  style={{ backgroundColor: "rgba(var(--brand-main), 0.05)" }}
                  title={t("auth:actions.holdReveal") ?? undefined}
                  aria-label={t("auth:actions.showPassword") ?? undefined}
                >
                  {showPassword ? (
                    <EyeOff className="h-4 w-4" aria-hidden="true" />
                  ) : (
                    <Eye className="h-4 w-4" aria-hidden="true" />
                  )}
                  {t("auth:actions.showPassword")}
                </button>
              </div>
              <div className="relative">
                <Input
                  id="password"
                  name="password"
                  type={showPassword ? "text" : "password"}
                  ref={passwordRef}
                  onKeyUp={(event: React.KeyboardEvent) =>
                    setCaps(event.getModifierState("CapsLock"))
                  }
                  onKeyDown={(event: React.KeyboardEvent) =>
                    setCaps(event.getModifierState("CapsLock"))
                  }
                  autoComplete="current-password"
                  disabled={isPending || submitting}
                  required
                />
                {caps ? (
                  <span className="absolute inset-y-0 right-4 flex items-center text-xs font-semibold text-warning-text">
                    {t("auth:messages.capsLock")}
                  </span>
                ) : null}
              </div>
            </div>

            <div
              className="min-h-6 text-center text-sm font-semibold text-error-text"
              aria-live="assertive"
            >
              {submitError || passkeyError}
            </div>

            <label className="flex items-center gap-3 text-sm font-medium text-text-primary">
              <input
                type="checkbox"
                className="size-5 rounded-lg border-brand/(--opacity-medium) bg-transparent accent-brand"
                checked={trustDevice}
                onChange={(e) => setTrustDevice(e.target.checked)}
                disabled={isPending || submitting}
              />
              {t("auth:actions.rememberEmail")}
            </label>

            <div className="flex flex-col gap-3">
              <Button
                id="login-submit"
                type="submit"
                variant="solid"
                size="lg"
                fullWidth
                loading={isPending || submitting}
                disabled={isPending || submitting}
                className="text-lg font-extrabold shadow-premium hover:shadow-glass-strong"
                leadingIcon={!(isPending || submitting) ? <LogIn className="h-6 w-6" /> : undefined}
              >
                {t("auth:actions.signIn")}
              </Button>

              {webauthnSupported && (
                <Button
                  id="login-passkey"
                  type="button"
                  onClick={handlePasskeyLogin}
                  disabled={submitting}
                  variant="outline"
                  size="lg"
                  fullWidth
                  className="border-brand/(--opacity-medium) bg-brand/(--opacity-subtle) text-lg font-extrabold text-brand hover:bg-brand/(--opacity-dim)"
                  leadingIcon={<Fingerprint className="h-6 w-6" />}
                >
                  {t("auth:login.signInWithPasskey")}
                </Button>
              )}
            </div>

            <div className="space-y-2 text-center text-sm">
              <Link
                to="/forgot-password"
                className="font-semibold text-brand underline-offset-4 transition hover:underline"
              >
                {t("auth:login.forgot")}
              </Link>
              <div>
                {t("auth:login.noAccount")}{" "}
                <Link
                  to="/register"
                  className="font-semibold text-brand underline-offset-4 transition hover:underline"
                >
                  {t("auth:login.ctaRegister")}
                </Link>
              </div>
            </div>
          </form>
        </FadeIn>
=======
      <div className="relative z-content mx-auto grid min-h-screen w-full max-w-7xl grid-cols-1 items-stretch gap-12 px-4 py-12 sm:px-6 lg:grid-cols-2 lg:px-8">
        <LoginHero />
        <LoginCredentialForm form={form} />
>>>>>>> origin/main
      </div>
    </div>
  )
}

export default Login
