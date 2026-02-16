import { useTranslation } from "react-i18next"
import { Link } from "react-router-dom"
import { Eye, EyeOff, Sparkles, Fingerprint, LogIn } from "lucide-react"

import { FadeIn } from "@/components/ui/motion/FadeIn"
import { Input } from "@/components/ui/Input"
import { Button } from "@/components/ui/Button"
import { Checkbox } from "@/components/ui/Checkbox"
import type { useLoginForm } from "@/hooks/auth/useLoginFlow"

type LoginCredentialFormProps = {
  form: ReturnType<typeof useLoginForm>
}

export function LoginCredentialForm({ form }: LoginCredentialFormProps) {
  const { t } = useTranslation(["auth"])

  const {
    emailRef,
    passwordRef,
    savedEmail,
    trustDevice,
    setTrustDevice,
    caps,
    setCaps,
    showPassword,
    setShowPassword,
    emailSuggestion,
    setEmailMirror,
    emailValid,
    submitting,
    isPending,
    submitError,
    passkeyError,
    webauthnSupported,
    submitAction,
    handleEmailBlur,
    applySuggestion,
    handlePasskeyLogin,
  } = form

  return (
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
              className="inline-flex items-center gap-2 rounded-full border border-border-focus/(--opacity-strong) px-4 py-2 text-xs font-semibold uppercase tracking-[0.2em] text-brand transition hover:bg-brand-subtle"
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
              className="inline-flex items-center gap-2 rounded-full border border-transparent px-3 py-1 text-xs font-bold uppercase tracking-widest text-brand transition hover:bg-brand/5 focus:outline-none focus:ring-2 focus:ring-brand/20"
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

        <div className="flex items-center gap-3 text-sm font-medium text-text-primary">
          <Checkbox
            checked={trustDevice}
            onCheckedChange={(checked) => setTrustDevice(checked === true)}
            disabled={isPending || submitting}
            aria-label={t("auth:actions.rememberEmail")}
          />
          {t("auth:actions.rememberEmail")}
        </div>

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
  )
}
