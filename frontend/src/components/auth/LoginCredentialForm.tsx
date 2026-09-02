import { useTranslation } from "react-i18next"
import { Link } from "@tanstack/react-router"
import { Eye, EyeOff, Sparkles, LogIn } from "lucide-react"

import { FadeIn } from "@/components/ui/motion/FadeIn"
import { Input } from "@/components/ui/Input"
import { Button } from "@/components/ui/Button"
import { Checkbox } from "@/components/ui/Checkbox"
import useMediaQuery from "@/hooks/useMediaQuery"
import type { useLoginForm } from "@/hooks/auth/useLoginFlow"

type LoginCredentialFormProps = {
  form: ReturnType<typeof useLoginForm>
}

import { Controller } from "react-hook-form"

// ... imports

export function LoginCredentialForm({ form }: LoginCredentialFormProps) {
  // Translation keys are fully qualified (``auth:...``), so the component
  // does not need to pin a default namespace.  This keeps the presentational
  // form usable with lightweight i18n test adapters and SSR fallbacks.
  const { t } = useTranslation()
  const prefersReducedMotion = useMediaQuery("(prefers-reduced-motion: reduce)")

  const {
    form: {
      register,
      control,
      formState: { errors },
    },
    caps,
    setCaps,
    showPassword,
    setShowPassword,
    emailSuggestion,
    applySuggestion,
    handleEmailBlur,
    // computed
    submitting,
    submitError,
    onSubmit,
  } = form

  return (
    <FadeIn
      {...(prefersReducedMotion ? { initial: false as const } : {})}
      direction="up"
      distance={8}
      duration={0.2}
      delay={0.2}
      className="auth-card-glass flex w-full min-w-0 flex-col justify-center bg-surface/(--opacity-hover) p-6 sm:p-10"
    >
      <form noValidate autoComplete="on" onSubmit={onSubmit} className="flex flex-col gap-6">
        <div className="space-y-2 text-center">
          <h2 className="text-3xl font-extrabold">{t("auth:login.title")}</h2>
          <p className="text-sm text-text-secondary">{t("auth:login.subtitle")}</p>
        </div>

        <div className="space-y-2">
          <label htmlFor="email" className="text-sm font-semibold text-text-primary">
            {t("auth:fields.email")}
          </label>
          <Input
            id="email"
            {...register("email")}
            type="email"
            className={errors.email ? "border-error-text focus:border-error-text" : ""}
            onBlur={(e) => {
              register("email").onBlur(e)
              handleEmailBlur()
            }}
            autoComplete="username"
            disabled={submitting}
            inputMode="email"
            required
            error={!!errors.email}
            aria-describedby={errors.email ? "login-email-error" : undefined}
          />
          <p
            id="login-email-error"
            role={errors.email ? "alert" : undefined}
            className="text-xs text-text-secondary/(--opacity-hover)"
          >
            {errors.email ? t(errors.email.message || "auth:messages.invalidFormat") : " "}
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
              onClick={() => setShowPassword((v) => !v)}
              className="inline-flex min-h-11 min-w-11 items-center justify-center gap-2 rounded-full border border-transparent px-3 py-1 text-xs font-bold uppercase tracking-widest text-brand transition hover:bg-brand/5 focus:outline-none focus:ring-2 focus:ring-brand/20"
              title={
                t(showPassword ? "auth:actions.hideCredential" : "auth:actions.showPassword") ??
                undefined
              }
              aria-label={
                t(showPassword ? "auth:actions.hideCredential" : "auth:actions.showPassword") ??
                undefined
              }
              aria-pressed={showPassword}
            >
              {showPassword ? (
                <EyeOff className="h-4 w-4" aria-hidden="true" />
              ) : (
                <Eye className="h-4 w-4" aria-hidden="true" />
              )}
              {t(showPassword ? "auth:actions.hideCredential" : "auth:actions.showPassword")}
            </button>
          </div>
          <div className="relative">
            <Input
              id="password"
              {...register("password")}
              type={showPassword ? "text" : "password"}
              onKeyUp={(event: React.KeyboardEvent) => setCaps(event.getModifierState("CapsLock"))}
              onKeyDown={(event: React.KeyboardEvent) =>
                setCaps(event.getModifierState("CapsLock"))
              }
              autoComplete="current-password"
              disabled={submitting}
              required
              error={!!errors.password}
              aria-describedby={errors.password ? "login-password-error" : undefined}
            />
            {caps ? (
              <span className="absolute inset-y-0 right-4 flex items-center text-xs font-semibold text-warning-text">
                {t("auth:messages.capsLock")}
              </span>
            ) : null}
          </div>
          {errors.password && (
            <p id="login-password-error" role="alert" className="text-xs text-error-text">
              {t(errors.password.message || "auth:messages.passwordRequired")}
            </p>
          )}
        </div>

        <div
          role={submitError ? "alert" : undefined}
          className="min-h-6 text-center text-sm font-semibold text-error-text"
          aria-live="assertive"
        >
          {submitError}
        </div>

        <div className="space-y-3">
          <div className="flex min-h-11 items-center gap-3 text-sm font-medium text-text-primary">
            <Controller
              control={control}
              name="rememberEmail"
              render={({ field: { value, onChange, ...field } }) => (
                <Checkbox
                  {...field}
                  id="remember-email"
                  checked={!!value}
                  onCheckedChange={onChange}
                  disabled={submitting}
                  aria-label={t("auth:actions.rememberEmail")}
                />
              )}
            />
            <label htmlFor="remember-email" className="flex-1 cursor-pointer">
              {t("auth:actions.rememberEmail")}
            </label>
          </div>

          <div className="rounded-xl border border-warning-border/(--opacity-medium) bg-warning-bg/(--opacity-subtle) p-3">
            <div className="flex min-h-11 items-center gap-3 text-sm font-semibold text-text-primary">
              <Controller
                control={control}
                name="trustDevice"
                render={({ field: { value, onChange, ...field } }) => (
                  <Checkbox
                    {...field}
                    id="trust-device"
                    checked={!!value}
                    onCheckedChange={onChange}
                    disabled={submitting}
                    aria-label={t("auth:actions.trustDevice")}
                    aria-describedby="trust-device-description"
                  />
                )}
              />
              <label htmlFor="trust-device" className="flex-1 cursor-pointer">
                {t("auth:actions.trustDevice")}
              </label>
            </div>
            <p id="trust-device-description" className="pl-9 text-xs text-text-secondary">
              {t("auth:actions.trustDeviceHint")}
            </p>
          </div>
        </div>

        <div className="flex flex-col gap-3">
          <Button
            id="login-submit"
            type="submit"
            variant="solid"
            size="lg"
            fullWidth
            loading={submitting}
            disabled={submitting}
            className="text-lg font-extrabold shadow-premium hover:shadow-glass-strong"
            leadingIcon={!submitting ? <LogIn className="h-6 w-6" /> : undefined}
          >
            {t("auth:actions.signIn")}
          </Button>
        </div>

        <div className="space-y-2 text-center text-sm">
          {/* Wave 115 SW3 — WCAG 2.2 AA 2.5.8 defensive hit-box sizing.
              The forgot-password + register links render at 19 × ~109 px by
              default (text-sm 14 px + line-height 20 px + no padding), which
              is below the 24 × 24 px target-size minimum. axe-core 4.11.2
              differs between Playwright chromium (passes — likely applies the
              "Inline text" exception) and live dev in chrome-devtools MCP
              (fails — reports 19 × 105 px). `inline-block min-h-[24px]
              px-2 py-1.5 rounded-md` preserves the link's visual weight while
              giving it a 24 × 24 px minimum hit target regardless of axe's
              interpretation. Same treatment applied to the register link —
              the visual pair shouldn't diverge. */}
          <Link
            to="/forgot-password"
            className="inline-block min-h-[24px] rounded-md px-2 py-1.5 font-semibold text-brand underline-offset-4 transition hover:underline"
          >
            {t("auth:login.forgot")}
          </Link>
          <div>
            {t("auth:login.noAccount")}{" "}
            <Link
              to="/register"
              className="inline-block min-h-[24px] rounded-md px-2 py-1.5 font-semibold text-brand underline-offset-4 transition hover:underline"
            >
              {t("auth:login.ctaRegister")}
            </Link>
          </div>
        </div>
      </form>
    </FadeIn>
  )
}
