import { useActionState, useEffect, useMemo, useRef, useState } from "react"
import { Link, useNavigate } from "react-router-dom"
import { useTranslation } from "react-i18next"
import { Eye, EyeOff, Sparkles, UsersRound, ShieldCheck, Crown } from "lucide-react"
import { motion } from "framer-motion"
import ParticleAuthBackground from "@/components/ui/ParticleAuthBackground"
import api from "@/api/client"
import { Input } from "@/components/ui/Input"
import { Select } from "@/components/ui/Select"
import { Button } from "@/components/ui/Button"
import { suggestEmailDomain } from "@/utils/authUtils"
import { cn } from "@/utils/cn"

type RegisterState = {
  status: "idle" | "success" | "error"
  error?: string
  field?: "full_name" | "email" | "password" | "confirm" | "invite_code"
}

// Email suggestion logic centralized in authUtils.ts
const emailRe = /^[^\s@]+@[^\s@]+\.[^\s@]+$/



const Register = () => {
  const { t } = useTranslation(["auth"])
  const navigate = useNavigate()
  const [form, setForm] = useState({
    full_name: "",
    email: "",
    password: "",
    confirm: "",
    role: "student",
    invite_code: "",
  })
  const [showPass, setShowPass] = useState(false)
  const [showConfirm, setShowConfirm] = useState(false)
  const [capsPass, setCapsPass] = useState(false)
  const [capsConfirm, setCapsConfirm] = useState(false)
  const [strength, setStrength] = useState<number | null>(null)
  const [emailSuggestion, setEmailSuggestion] = useState<string | null>(null)

  const fullNameRef = useRef<HTMLInputElement | null>(null)
  const emailRef = useRef<HTMLInputElement | null>(null)
  const inviteRef = useRef<HTMLInputElement | null>(null)
  const passwordRef = useRef<HTMLInputElement | null>(null)
  const confirmRef = useRef<HTMLInputElement | null>(null)

  const needsInvite = form.role === "teacher" || form.role === "admin"
  const minLenOk = form.password.length >= 8
  const matchOk = form.confirm.length > 0 && form.password === form.confirm
  const emailValid = form.email.length === 0 || emailRe.test(form.email)
  const isValid =
    form.full_name.trim().length > 1 &&
    emailRe.test(form.email) &&
    minLenOk &&
    matchOk &&
    (!needsInvite || form.invite_code.trim().length > 0)

  const handleChange = (event: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    setForm((formState) => ({ ...formState, [event.target.name]: event.target.value }))
  }

  const handleEmailBlur = () => {
    const suggestion = suggestEmailDomain(form.email)
    setEmailSuggestion(suggestion && suggestion !== form.email ? suggestion : null)
  }

  const handlePass = async (value: string) => {
    setForm((formState) => ({ ...formState, password: value }))
    if (!value) {
      setStrength(null)
      return
    }
    try {
      const { zxcvbn, zxcvbnOptions } = await import("@zxcvbn-ts/core")
      const zxcvbnCommon = await import("@zxcvbn-ts/language-common")
      zxcvbnOptions.setOptions(zxcvbnCommon)
      const strengthScore = zxcvbn(value).score
      setStrength(strengthScore)
    } catch {
      setStrength(null)
    }
  }

  const [registerState, registerAction, registerPending] = useActionState<RegisterState, FormData>(
    async (_previousState, formData) => {
      const fullName = String(formData.get("full_name") ?? "").trim()
      const email = String(formData.get("email") ?? "").trim()
      const password = String(formData.get("password") ?? "")
      const confirm = String(formData.get("confirm") ?? "")
      const role = String(formData.get("role") ?? "student")
      const inviteCode = String(formData.get("invite_code") ?? "").trim()

      if (!fullName || !email || !password) {
        const field: RegisterState["field"] = !fullName
          ? "full_name"
          : !email
            ? "email"
            : "password"
        return { status: "error" as const, error: t("auth:register.requireFields"), field }
      }

      if (!emailRe.test(email)) {
        return {
          status: "error" as const,
          error: t("auth:messages.invalidFormat"),
          field: "email" as const,
        }
      }

      if (password !== confirm) {
        return {
          status: "error" as const,
          error: t("auth:register.passwordMismatch"),
          field: "confirm" as const,
        }
      }

      if ((role === "teacher" || role === "admin") && !inviteCode) {
        return {
          status: "error" as const,
          error: t("auth:register.inviteRequired"),
          field: "invite_code" as const,
        }
      }

      try {
        await api.post("/auth/register", {
          full_name: fullName,
          email,
          password,
          role,
          invite_code: inviteCode,
        })
        navigate("/login")
        return { status: "success" as const }
      } catch (error: unknown) {
        let errorMessage = t("auth:register.error")
        if (typeof error === "object" && error !== null && "response" in error) {
          const axiosError = error as { response?: { data?: { detail?: string | string[] } } }
          const detail = axiosError.response?.data?.detail
          if (typeof detail === "string") errorMessage = detail
          else if (Array.isArray(detail)) errorMessage = detail.join("; ")
        }
        return { status: "error" as const, error: errorMessage }
      }
    },
    { status: "idle" as const }
  )

  const registerStatus = registerState.status
  const registerErrorField = registerState.field
  const registerErrorMessage = registerStatus === "error" ? (registerState.error ?? "") : ""

  useEffect(() => {
    if (!registerPending && registerStatus === "error" && registerErrorField) {
      if (registerErrorField === "full_name") fullNameRef.current?.focus()
      else if (registerErrorField === "email") emailRef.current?.focus()
      else if (registerErrorField === "password") passwordRef.current?.focus()
      else if (registerErrorField === "confirm") confirmRef.current?.focus()
      else if (registerErrorField === "invite_code") inviteRef.current?.focus()
    }
  }, [registerPending, registerStatus, registerErrorField])

  const passwordStrengthPercent = useMemo(() => {
    if (strength === null) return null
    return [10, 30, 55, 75, 100][strength]
  }, [strength])

  const passwordStrengthLabel = useMemo(() => {
    if (strength === null) return null
    return [
      t("auth:register.passwordStrength.veryWeak", { defaultValue: "Очень слабый" }),
      t("auth:register.passwordStrength.weak", { defaultValue: "Слабый" }),
      t("auth:register.passwordStrength.medium", { defaultValue: "Средний" }),
      t("auth:register.passwordStrength.good", { defaultValue: "Хороший" }),
      t("auth:register.passwordStrength.excellent", { defaultValue: "Отличный" }),
    ][strength]
  }, [strength, t])

  const heroPerks = [
    {
      icon: UsersRound,
      title: t("auth:register.hero.perks.community.title"),
      description: t("auth:register.hero.perks.community.description"),
    },
    {
      icon: ShieldCheck,
      title: t("auth:register.hero.perks.secure.title"),
      description: t("auth:register.hero.perks.secure.description"),
    },
    {
      icon: Sparkles,
      title: t("auth:register.hero.perks.experience.title"),
      description: t("auth:register.hero.perks.experience.description"),
    },
  ]

  const inviteHint = needsInvite
    ? t("auth:register.inviteRequired", { defaultValue: "Пригласительный код обязателен" })
    : t("auth:register.inviteOptional", { defaultValue: "Приглашение необязательно" })

  return (
    <div className="relative min-h-screen w-full overflow-hidden bg-page text-text-primary">
      <ParticleAuthBackground />
      <div className="relative z-surface mx-auto grid min-h-screen w-full max-w-7xl grid-cols-1 items-stretch gap-10 px-4 py-12 sm:px-6 lg:grid-cols-2 lg:px-8">
        <motion.div
          initial={{ x: -200 }}
          animate={{ x: 0 }}
          transition={{ duration: 0.5, ease: "easeOut" }}
          className="auth-card-glass flex w-full min-w-0 flex-col justify-center border-glass-border-subtle p-8 lg:p-12"
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
            {heroPerks.map(({ icon: Icon, title, description }) => (
              <div
                key={title}
                className="auth-perk-card group"
              >
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
        </motion.div>

        <motion.div
          initial={{ y: 200 }}
          animate={{ y: 0 }}
          transition={{ duration: 0.5, ease: "easeOut", delay: 0.2 }}
          className="auth-card-glass flex w-full min-w-0 flex-col justify-center border-glass-border-subtle bg-surface/(--opacity-hover) p-6 sm:p-10"
        >
          <form action={registerAction} autoComplete="off" className="flex flex-col gap-6">
            <div className="grid gap-5 sm:grid-cols-2">
              <div className="space-y-2">
                <label htmlFor="full_name" className="text-sm font-semibold">
                  {t("auth:fields.name")}
                </label>

                <Input
                  id="full_name"
                  name="full_name"
                  value={form.full_name}
                  onChange={handleChange}
                  autoComplete="name"
                  ref={fullNameRef}
                  disabled={registerPending}
                  error={registerStatus === "error" && registerErrorField === "full_name"}
                  placeholder={
                    t("auth:register.namePlaceholder", { defaultValue: "Имя и фамилия" }) ??
                    undefined
                  }
                />
              </div>
              <div className="space-y-2">
                <label id="register-role-label" htmlFor="role" className="text-sm font-semibold">
                  {t("auth:fields.role")}
                </label>
                <div className="relative">
                  <Select
                    id="register-role"
                    aria-labelledby="register-role-label"
                    value={form.role}
                    onValueChange={(val) => setForm((prev) => ({ ...prev, role: val }))}
                    options={[
                      { value: "student", label: t("auth:register.role.student") },
                      { value: "teacher", label: t("auth:register.role.teacher") },
                      { value: "admin", label: t("auth:register.role.admin") },
                    ]}
                    disabled={registerPending}
                    placeholder={t("auth:fields.role")}
                  />

                  <span className="text-text-muted-subtle text-sm">{inviteHint}</span>
                </div>
              </div>
            </div>
            <div className="space-y-2">
              <label htmlFor="email" className="text-sm font-semibold">
                {t("auth:fields.email")}
              </label>
              <Input
                id="email"
                name="email"
                type="email"
                value={form.email}
                onChange={handleChange}
                onBlur={handleEmailBlur}
                error={
                  !emailValid || (registerStatus === "error" && registerErrorField === "email")
                }
                autoComplete="email"
                ref={emailRef}
                disabled={registerPending}
                placeholder="name@university.edu"
              />
              <p className="text-text-secondary text-xs font-medium">
                {!emailValid ? t("auth:messages.invalidFormat") : " "}
              </p>
              {emailSuggestion ? (
                <button
                  type="button"
                  className="badge-brand"
                  onClick={() => {
                    setForm((formState) => ({ ...formState, email: emailSuggestion }))
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
                  name="invite_code"
                  value={form.invite_code}
                  onChange={handleChange}
                  autoComplete="one-time-code"
                  ref={inviteRef}
                  disabled={registerPending}
                  error={registerStatus === "error" && registerErrorField === "invite_code"}
                  placeholder="ABCD-1234"
                />
              </div>
            ) : null}

            <div className="space-y-2">
              <label htmlFor="password" className="text-sm font-semibold">
                {t("auth:fields.password")}
              </label>
              <div className="relative">
                <Input
                  id="password"
                  name="password"
                  type={showPass ? "text" : "password"}
                  value={form.password}
                  onChange={(event) => handlePass(event.target.value)}
                  onKeyUp={(event: React.KeyboardEvent) =>
                    setCapsPass(event.getModifierState("CapsLock"))
                  }
                  onKeyDown={(event: React.KeyboardEvent) =>
                    setCapsPass(event.getModifierState("CapsLock"))
                  }
                  autoComplete="new-password"
                  ref={passwordRef}
                  disabled={registerPending}
                  error={registerStatus === "error" && registerErrorField === "password"}
                />
                <button
                  type="button"
                  onMouseDown={() => setShowPass(true)}
                  onMouseUp={() => setShowPass(false)}
                  onMouseLeave={() => setShowPass(false)}
                  onClick={() => setShowPass((v) => !v)}
                  className="absolute inset-y-0 right-4 flex items-center text-brand"
                  aria-label={t("auth:actions.showPassword") ?? undefined}
                  title={t("auth:actions.holdReveal") ?? undefined}
                >
                  {showPass ? (
                    <EyeOff className="h-5 w-5" aria-hidden="true" />
                  ) : (
                    <Eye className="h-5 w-5" aria-hidden="true" />
                  )}
                </button>
              </div>
              <p className="text-xs text-text-muted-subtle">{t("auth:register.passwordHint")}</p>
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
                    minLenOk ? "border-brand/(--opacity-medium) text-brand" : "text-text-muted-subtle"
                  )}
                >
                  {t("auth:register.passwordChip.minLength")}
                </span>
                <span
                  className={cn(
                    "badge-brand",
                    matchOk ? "border-brand/(--opacity-medium) text-brand" : "text-text-muted-subtle"
                  )}
                >
                  {t("auth:register.passwordChip.match")}
                </span>
              </div>
              {capsPass ? (
                <p className="text-xs font-semibold text-warning-text">
                  {t("auth:messages.capsLock")}
                </p>
              ) : null}
            </div>

            <div className="space-y-2">
              <label htmlFor="confirm" className="text-sm font-semibold">
                {t("auth:fields.confirmPassword")}
              </label>
              <div className="relative">
                <Input
                  id="confirm"
                  name="confirm"
                  type={showConfirm ? "text" : "password"}
                  value={form.confirm}
                  onChange={handleChange}
                  onKeyUp={(event: React.KeyboardEvent) =>
                    setCapsConfirm(event.getModifierState("CapsLock"))
                  }
                  onKeyDown={(event: React.KeyboardEvent) =>
                    setCapsConfirm(event.getModifierState("CapsLock"))
                  }
                  autoComplete="new-password"
                  ref={confirmRef}
                  disabled={registerPending}
                  error={registerStatus === "error" && registerErrorField === "confirm"}
                />
                <button
                  type="button"
                  onMouseDown={() => setShowConfirm(true)}
                  onMouseUp={() => setShowConfirm(false)}
                  onMouseLeave={() => setShowConfirm(false)}
                  onClick={() => setShowConfirm((v) => !v)}
                  className="absolute inset-y-0 right-4 flex items-center text-brand"
                  aria-label={t("auth:actions.showPassword") ?? undefined}
                  title={t("auth:actions.holdReveal") ?? undefined}
                >
                  {showConfirm ? (
                    <EyeOff className="h-5 w-5" aria-hidden="true" />
                  ) : (
                    <Eye className="h-5 w-5" aria-hidden="true" />
                  )}
                </button>
              </div>
              {capsConfirm ? (
                <p className="text-xs font-semibold text-warning-text">
                  {t("auth:messages.capsLock")}
                </p>
              ) : null}
            </div>

            <div
              className="min-h-6 text-center text-sm font-semibold text-error-text"
              aria-live="assertive"
            >
              {registerErrorMessage}
            </div>

            <Button
              id="register-submit"
              type="submit"
              variant="solid"
              size="lg"
              fullWidth
              loading={registerPending}
              disabled={registerPending || !isValid}
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
        </motion.div>
      </div>
    </div>
  )
}

export default Register
