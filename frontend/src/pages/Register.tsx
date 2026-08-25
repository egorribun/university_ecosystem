import { useState, useMemo, useEffect } from "react"
import { Link, useNavigate } from "@tanstack/react-router"
import { useTranslation } from "react-i18next"
import { Eye, EyeOff, Sparkles, UsersRound, ShieldCheck, Crown } from "lucide-react"
import { m } from "framer-motion"
import { useForm, Controller, type SubmitHandler } from "react-hook-form"
import { valibotResolver } from "@hookform/resolvers/valibot"

import ParticleAuthBackground from "@/components/ui/ParticleAuthBackground"
import AuthBackdrop from "@/components/auth/AuthBackdrop"
import useMediaQuery from "@/hooks/useMediaQuery"
import api from "@/api/client"
import { Input } from "@/components/ui/Input"
import { Select } from "@/components/ui/Select"
import { Button } from "@/components/ui/Button"
import { suggestEmailDomain } from "@/utils/authUtils"
import { cn } from "@/utils/cn"
import { registerSchema, type RegisterValues } from "@/features/auth/schemas"
import { analyzePasswordStrength } from "@/utils/passwordStrength"

const Register = () => {
  const { t, i18n } = useTranslation(["auth"])
  const passwordStrengthLanguage = i18n.resolvedLanguage ?? i18n.language
  const navigate = useNavigate()
  // Wave 186 SW3 — useReducedMotion via project's useMediaQuery (jsdom-safe
  // per W184 SW6). Drops AuthBackdrop blur on mobile/reduced-motion.
  const prefersReducedMotion = useMediaQuery("(prefers-reduced-motion: reduce)")
  const [showPass, setShowPass] = useState(false)
  const [showConfirm, setShowConfirm] = useState(false)
  const [capsPass, setCapsPass] = useState(false)
  const [capsConfirm, setCapsConfirm] = useState(false)
  const [strength, setStrength] = useState<number | null>(null)
  const [emailSuggestion, setEmailSuggestion] = useState<string | null>(null)

  const {
    register,
    handleSubmit,
    control,
    watch,
    setValue,
    setError,
    trigger,
    formState: { errors, isSubmitting },
  } = useForm<RegisterValues>({
    resolver: valibotResolver(registerSchema),
    defaultValues: {
      full_name: "",
      email: "",
      role: "student",
      invite_code: "",
      password: "",
      confirmPassword: "",
    },
    mode: "onBlur",
  })

  // Watch fields for UI logic
  const role = watch("role")
  const password = watch("password")
  const email = watch("email")
  const confirmPassword = watch("confirmPassword")

  // Calculate strict checks for UI feedback chips
  const minLenOk = (password?.length || 0) >= 8
  const matchOk = (confirmPassword?.length || 0) > 0 && password === confirmPassword
  const needsInvite = role === "teacher" || role === "admin"

  const handleEmailBlur = () => {
    trigger("email")
    if (email) {
      const suggestion = suggestEmailDomain(email)
      setEmailSuggestion(suggestion && suggestion !== email ? suggestion : null)
    }
  }

  // Password strength calculation
  useEffect(() => {
    if (!password) {
      setStrength(null)
      return
    }
    let active = true

    const checkStrength = async () => {
      try {
        const strengthScore = (await analyzePasswordStrength(password, passwordStrengthLanguage))
          .score
        if (active) setStrength(strengthScore)
      } catch {
        if (active) setStrength(null)
      }
    }
    void checkStrength()
    return () => {
      active = false
    }
  }, [password, passwordStrengthLanguage])

  const onSubmit: SubmitHandler<RegisterValues> = async (data) => {
    try {
      await api.post("/auth/register", {
        full_name: data.full_name,
        email: data.email,
        password: data.password,
        role: data.role,
        invite_code: data.invite_code,
      })
      navigate({ to: "/login" })
    } catch (error: unknown) {
      let errorMessage = t("auth:register.error")
      if (typeof error === "object" && error !== null && "response" in error) {
        const axiosError = error as { response?: { data?: { detail?: string | string[] } } }
        const detail = axiosError.response?.data?.detail
        if (typeof detail === "string") errorMessage = detail
        else if (Array.isArray(detail)) errorMessage = detail.join("; ")
      }
      setError("root", { message: errorMessage })
    }
  }

  const passwordStrengthPercent = useMemo(() => {
    if (strength === null) return null
    return [10, 30, 55, 75, 100][strength]
  }, [strength])

  const passwordStrengthLabel = useMemo(() => {
    if (strength === null) return null
    return [
      t("auth:register.passwordStrengthLevel.veryWeak"),
      t("auth:register.passwordStrengthLevel.weak"),
      t("auth:register.passwordStrengthLevel.medium"),
      t("auth:register.passwordStrengthLevel.good"),
      t("auth:register.passwordStrengthLevel.excellent"),
    ][strength]
  }, [strength, t])

  const heroPerks = [
    {
      id: "community",
      icon: UsersRound,
      title: t("auth:register.hero.perks.community.title"),
      description: t("auth:register.hero.perks.community.description"),
    },
    {
      id: "secure",
      icon: ShieldCheck,
      title: t("auth:register.hero.perks.secure.title"),
      description: t("auth:register.hero.perks.secure.description"),
    },
    {
      id: "experience",
      icon: Sparkles,
      title: t("auth:register.hero.perks.experience.title"),
      description: t("auth:register.hero.perks.experience.description"),
    },
  ]

  const inviteHint = needsInvite
    ? t("auth:register.inviteRequired")
    : t("auth:register.inviteOptional")

  return (
    <div className="auth-theme relative min-h-screen w-full overflow-hidden bg-page text-text-primary">
      <AuthBackdrop prefersReducedMotion={prefersReducedMotion} />
      <ParticleAuthBackground />
      <div className="relative z-surface mx-auto grid min-h-screen w-full max-w-7xl grid-cols-1 items-stretch gap-10 px-4 py-12 sm:px-6 lg:grid-cols-2 lg:px-8">
        {/* Left Column - Hero */}
        <m.div
          initial={prefersReducedMotion ? false : { x: -8 }}
          animate={{ x: 0 }}
          transition={{ duration: 0.2, ease: "easeOut" }}
          className="auth-card-matte flex w-full min-w-0 flex-col justify-center border-glass-border-subtle p-8 lg:p-12"
        >
          <div className="flex items-center gap-3 text-sm font-semibold uppercase tracking-widest text-text-primary/(--opacity-strong)">
            <Crown className="h-5 w-5" aria-hidden="true" />
            {t("auth:register.hero.badge")}
          </div>
          <h1 className="mt-6 text-4xl font-extrabold leading-tight text-text-primary sm:text-5xl">
            {t("auth:register.title")}
          </h1>
          <p className="mt-4 text-lg leading-relaxed text-text-secondary">
            {t("auth:register.hero.description")}
          </p>
          <div className="mt-8 grid gap-5 sm:grid-cols-2">
            {heroPerks.map(({ id, icon: Icon, title, description }) => (
              <div key={id} className="auth-perk-card group">
                <div className="flex items-center gap-3">
                  <div className="flex size-12 items-center justify-center rounded-md bg-brand-subtle-bg text-brand">
                    <Icon className="h-5 w-5" aria-hidden="true" />
                  </div>
                  <p className="text-base font-semibold">{title}</p>
                </div>
                <p className="mt-4 text-sm text-text-secondary">{description}</p>
              </div>
            ))}
          </div>
        </m.div>

        {/* Right Column - Form */}
        <m.div
          initial={prefersReducedMotion ? false : { y: 8 }}
          animate={{ y: 0 }}
          transition={{ duration: 0.2, ease: "easeOut", delay: 0.05 }}
          className="auth-card-matte flex w-full min-w-0 flex-col justify-center border-glass-border-subtle bg-surface/(--opacity-hover) p-6 sm:p-10"
        >
          <form
            onSubmit={handleSubmit(onSubmit)}
            autoComplete="on"
            className="flex flex-col gap-6"
            noValidate
          >
            <div className="grid gap-5 sm:grid-cols-2">
              <div className="space-y-2">
                <label htmlFor="full_name" className="text-sm font-semibold">
                  {t("auth:fields.name")}
                </label>
                <Input
                  id="full_name"
                  {...register("full_name")}
                  autoComplete="name"
                  disabled={isSubmitting}
                  error={!!errors.full_name}
                  aria-describedby={errors.full_name ? "register-name-error" : undefined}
                  placeholder={t("auth:register.namePlaceholder") ?? undefined}
                />
                {errors.full_name && (
                  <p id="register-name-error" role="alert" className="text-xs text-error-text">
                    {errors.full_name.message}
                  </p>
                )}
              </div>

              <div className="space-y-2">
                <label id="register-role-label" htmlFor="role" className="text-sm font-semibold">
                  {t("auth:fields.role")}
                </label>
                <div className="relative">
                  <Controller
                    control={control}
                    name="role"
                    render={({ field }) => (
                      <Select
                        id="register-role"
                        aria-labelledby="register-role-label"
                        aria-describedby="register-role-description"
                        value={field.value}
                        onValueChange={field.onChange}
                        options={[
                          { value: "student", label: t("auth:register.role.student") },
                          { value: "teacher", label: t("auth:register.role.teacher") },
                          { value: "admin", label: t("auth:register.role.admin") },
                        ]}
                        disabled={isSubmitting}
                        placeholder={t("auth:fields.role")}
                      />
                    )}
                  />
                  <span id="register-role-description" className="text-text-muted-subtle text-sm">
                    {inviteHint}
                  </span>
                </div>
              </div>
            </div>

            <div className="space-y-2">
              <label htmlFor="email" className="text-sm font-semibold">
                {t("auth:fields.email")}
              </label>
              <Input
                id="email"
                {...register("email")}
                autoComplete="email"
                onBlur={(e) => {
                  register("email").onBlur(e)
                  handleEmailBlur()
                }}
                disabled={isSubmitting}
                error={!!errors.email}
                aria-describedby={errors.email ? "register-email-error" : undefined}
                placeholder="name@university.edu"
              />
              <p
                id="register-email-error"
                role={errors.email ? "alert" : undefined}
                className="text-text-secondary text-xs font-medium"
              >
                {errors.email ? t(errors.email.message || "auth:messages.invalidFormat") : " "}
              </p>
              {emailSuggestion ? (
                <button
                  type="button"
                  className="badge-brand"
                  onClick={() => {
                    setValue("email", emailSuggestion, { shouldValidate: true })
                    setEmailSuggestion(null)
                  }}
                >
                  <Sparkles className="h-4 w-4" aria-hidden="true" />
                  {t("auth:messages.emailSuggestion", { suggestion: emailSuggestion })}
                </button>
              ) : null}
            </div>

            {needsInvite ? (
              <div className="space-y-2">
                <label htmlFor="invite_code" className="text-sm font-semibold">
                  {t("auth:fields.inviteCode")}
                </label>

                <Input
                  id="invite_code"
                  {...register("invite_code")}
                  autoComplete="one-time-code"
                  disabled={isSubmitting}
                  error={!!errors.invite_code}
                  aria-describedby={errors.invite_code ? "register-invite-error" : undefined}
                  placeholder="ABCD-1234"
                />
                {errors.invite_code && (
                  <p id="register-invite-error" role="alert" className="text-xs text-error-text">
                    {errors.invite_code.message}
                  </p>
                )}
              </div>
            ) : null}

            <div className="space-y-2">
              <label htmlFor="password" className="text-sm font-semibold">
                {t("auth:fields.password")}
              </label>
              <div className="relative">
                <Input
                  id="password"
                  {...register("password")}
                  type={showPass ? "text" : "password"}
                  onKeyUp={(event: React.KeyboardEvent) =>
                    setCapsPass(event.getModifierState("CapsLock"))
                  }
                  onKeyDown={(event: React.KeyboardEvent) =>
                    setCapsPass(event.getModifierState("CapsLock"))
                  }
                  autoComplete="new-password"
                  disabled={isSubmitting}
                  error={!!errors.password}
                  className="pr-14"
                  aria-describedby={`register-password-hint${errors.password ? " register-password-error" : ""}`}
                />
                <button
                  type="button"
                  onClick={() => setShowPass((v) => !v)}
                  className="absolute inset-y-0 right-1 flex min-h-11 min-w-11 items-center justify-center rounded-md text-brand focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
                  aria-label={
                    t(showPass ? "auth:actions.hideCredential" : "auth:actions.showPassword") ??
                    undefined
                  }
                  aria-pressed={showPass}
                >
                  {showPass ? (
                    <EyeOff className="h-5 w-5" aria-hidden="true" />
                  ) : (
                    <Eye className="h-5 w-5" aria-hidden="true" />
                  )}
                </button>
              </div>
              <p id="register-password-hint" className="text-xs text-text-muted-subtle">
                {t("auth:register.passwordHint")}
              </p>
              {passwordStrengthPercent !== null ? (
                <div className="space-y-1">
                  <div className="h-3 w-full rounded-full bg-surface-hover">
                    <div
                      className="h-full rounded-full bg-brand transition-all duration-base"
                      style={{ width: `${passwordStrengthPercent}%` }}
                    />
                  </div>
                  {passwordStrengthLabel ? (
                    <p className="text-xs font-semibold text-text-muted-subtle">
                      {passwordStrengthLabel}
                    </p>
                  ) : null}
                </div>
              ) : null}
              <div className="flex flex-wrap gap-2">
                <span
                  className={cn(
                    "badge-brand",
                    minLenOk
                      ? "border-brand/(--opacity-medium) text-brand"
                      : "text-text-muted-subtle"
                  )}
                >
                  {t("auth:register.passwordChip.minLength")}
                </span>
                <span
                  className={cn(
                    "badge-brand",
                    matchOk
                      ? "border-brand/(--opacity-medium) text-brand"
                      : "text-text-muted-subtle"
                  )}
                >
                  {t("auth:register.passwordChip.match")}
                </span>
              </div>
              {capsPass && (
                <p className="text-xs font-semibold text-warning-text">
                  {t("auth:messages.capsLock")}
                </p>
              )}
              {errors.password && (
                <p id="register-password-error" role="alert" className="text-xs text-error-text">
                  {errors.password.message}
                </p>
              )}
            </div>

            <div className="space-y-2">
              <label htmlFor="confirmPassword" className="text-sm font-semibold">
                {t("auth:fields.confirmPassword")}
              </label>
              <div className="relative">
                <Input
                  id="confirmPassword"
                  {...register("confirmPassword")}
                  type={showConfirm ? "text" : "password"}
                  onKeyUp={(event: React.KeyboardEvent) =>
                    setCapsConfirm(event.getModifierState("CapsLock"))
                  }
                  onKeyDown={(event: React.KeyboardEvent) =>
                    setCapsConfirm(event.getModifierState("CapsLock"))
                  }
                  autoComplete="new-password"
                  disabled={isSubmitting}
                  error={!!errors.confirmPassword}
                  className="pr-14"
                  aria-describedby={
                    errors.confirmPassword ? "register-confirm-password-error" : undefined
                  }
                />
                <button
                  type="button"
                  onClick={() => setShowConfirm((v) => !v)}
                  className="absolute inset-y-0 right-1 flex min-h-11 min-w-11 items-center justify-center rounded-md text-brand focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
                  aria-label={
                    t(showConfirm ? "auth:actions.hideCredential" : "auth:actions.showPassword") ??
                    undefined
                  }
                  aria-pressed={showConfirm}
                >
                  {showConfirm ? (
                    <EyeOff className="h-5 w-5" aria-hidden="true" />
                  ) : (
                    <Eye className="h-5 w-5" aria-hidden="true" />
                  )}
                </button>
              </div>
              {capsConfirm && (
                <p className="text-xs font-semibold text-warning-text">
                  {t("auth:messages.capsLock")}
                </p>
              )}
              {errors.confirmPassword && (
                <p
                  id="register-confirm-password-error"
                  role="alert"
                  className="text-xs text-error-text"
                >
                  {errors.confirmPassword.message}
                </p>
              )}
            </div>

            {errors.root?.message && (
              <div
                role="alert"
                className="min-h-6 text-center text-sm font-semibold text-error-text"
                aria-live="assertive"
              >
                {errors.root.message}
              </div>
            )}

            <Button
              id="register-submit"
              type="submit"
              variant="solid"
              size="lg"
              fullWidth
              loading={isSubmitting}
              disabled={isSubmitting}
              className="text-lg font-extrabold shadow-premium hover:shadow-glass disabled:opacity-strong"
            >
              {t("auth:actions.signUp")}
            </Button>

            <div className="text-center text-sm">
              {t("auth:register.haveAccount")}{" "}
              <Link
                to="/login"
                className="font-semibold text-brand underline-offset-4 transition hover:underline"
              >
                {t("auth:register.ctaLogin")}
              </Link>
            </div>
          </form>
        </m.div>
      </div>
    </div>
  )
}

export default Register
