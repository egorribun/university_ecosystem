import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { Link, useNavigate } from "react-router-dom"
import { useTranslation } from "react-i18next"
import { ShieldCheck, Sparkles, BookOpen, Eye, EyeOff, Zap } from "lucide-react"
import { ChallengeLockedError, type PendingMfaState, useAuth } from "@/contexts/AuthContext"
import OtpEntry from "@/components/mfa/OtpEntry"
import ParticleAuthBackground from "@/components/ui/ParticleAuthBackground"

type ChallengeMethod = PendingMfaState["methods"][number]
type ChallengeWithAttempts = ChallengeMethod &
  Partial<{ attempt_limit: number | null; remaining_attempts: number | null }>

function levenshtein(a: string, b: string) {
  const m = a.length
  const n = b.length
  if (!m) return n
  if (!n) return m

  const dp = Array.from({ length: m + 1 }, () => new Array(n + 1).fill(0))
  for (let i = 0; i <= m; i++) dp[i][0] = i
  for (let j = 0; j <= n; j++) dp[0][j] = j

  for (let i = 1; i <= m; i++) {
    for (let j = 1; j <= n; j++) {
      const cost = a[i - 1] === b[j - 1] ? 0 : 1
      dp[i][j] = Math.min(dp[i - 1][j] + 1, dp[i][j - 1] + 1, dp[i - 1][j - 1] + cost)
    }
  }
  return dp[m][n]
}

const COMMON_EMAIL_DOMAINS = [
  "gmail.com",
  "googlemail.com",
  "yahoo.com",
  "outlook.com",
  "hotmail.com",
  "live.com",
  "icloud.com",
  "mail.ru",
  "bk.ru",
  "list.ru",
  "inbox.ru",
  "yandex.ru",
  "yandex.com",
  "rambler.ru",
  "proton.me",
]

const emailRe = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

function suggestEmailDomain(email: string) {
  const at = email.indexOf("@")
  if (at < 0) return null

  const local = email.slice(0, at).trim()
  const dom = email
    .slice(at + 1)
    .trim()
    .toLowerCase()

  if (!local || !dom) return null
  if (COMMON_EMAIL_DOMAINS.includes(dom)) return null

  let best: { d: string; dist: number } | null = null
  for (const cand of COMMON_EMAIL_DOMAINS) {
    const dist = levenshtein(dom, cand)
    if (dist <= 2 && (!best || dist < best.dist)) best = { d: cand, dist }
  }
  return best ? `${local}@${best.d}` : null
}

const inputBaseClass =
  "w-full rounded-[1.2rem] border border-[color:color-mix(in_srgb,white_12%,var(--nav-link)_88%)] " +
  "bg-[color:color-mix(in_srgb,var(--card-bg)_96%,rgba(255,255,255,0.94)_4%)] px-4 py-3 text-base font-medium " +
  "text-[color:var(--page-text)] shadow-[0_10px_30px_rgba(15,23,42,0.08)] focus:border-[color:var(--nav-link)] " +
  "focus:outline-none focus:shadow-[0_0_0_3px_color-mix(in_srgb,var(--nav-link)_20%,transparent)] " +
  "placeholder:text-[color:color-mix(in_srgb,var(--placeholder-fg)_75%,transparent)] " +
  "dark:border-[color:color-mix(in_srgb,white_8%,var(--nav-link)_92%)] " +
  "dark:bg-[color:color-mix(in_srgb,var(--card-bg)_92%,rgba(10,18,32,0.94)_8%)]"

const badgeClass =
  "inline-flex items-center gap-2 rounded-full border border-[color:color-mix(in_srgb,var(--glass-border)_80%,transparent)] " +
  "bg-[color:color-mix(in_srgb,var(--card-bg)_92%,rgba(255,255,255,0.12)_8%)] px-4 py-2 text-sm font-semibold " +
  "text-[color:color-mix(in_srgb,var(--page-text)_90%,var(--nav-link)_10%)] shadow-[0_6px_20px_rgba(15,23,42,0.12)]"

const Spinner = () => (
  <span
    className="inline-flex h-5 w-5 animate-spin rounded-full border-2 border-current/60 border-t-transparent"
    aria-hidden="true"
  />
)

const Login = () => {
  const { t } = useTranslation(["auth"])
  const navigate = useNavigate()
  const { login, pendingMfa, submitMfaChallenge } = useAuth()

  const savedEmail = useRef<string>(localStorage.getItem("auth:lastEmail") || "")
  const [remember, setRemember] = useState<boolean>(
    () => localStorage.getItem("auth:remember") === "1"
  )
  const [caps, setCaps] = useState(false)
  const [showPassword, setShowPassword] = useState(false)
  const [emailSuggestion, setEmailSuggestion] = useState<string | null>(null)
  const [emailMirror, setEmailMirror] = useState(savedEmail.current)

  const emailRef = useRef<HTMLInputElement | null>(null)
  const passwordRef = useRef<HTMLInputElement | null>(null)

  const currentEmail = (emailRef.current?.value ?? emailMirror ?? "").trim()
  const emailValid = useMemo(
    () => currentEmail.length === 0 || emailRe.test(currentEmail),
    [currentEmail]
  )

  const [pendingEmail, setPendingEmail] = useState<string | null>(
    savedEmail.current ? savedEmail.current : null
  )
  const [mfaBusy, setMfaBusy] = useState(false)
  const [mfaError, setMfaError] = useState<string | null>(null)
  const [mfaErrorSource, setMfaErrorSource] = useState<"totp" | "general" | null>(null)

  const loginChallenge = useMemo(
    () => (pendingMfa?.reason === "login" ? pendingMfa : null),
    [pendingMfa]
  )

  const otpChallenge = useMemo<ChallengeMethod | null>(
    () => (loginChallenge ? (loginChallenge.methods[0] ?? null) : null),
    [loginChallenge]
  )

  const formatRemainingAttempts = useCallback(
    (challenge: ChallengeMethod | null) => {
      if (!challenge) return null
      const meta = challenge as ChallengeWithAttempts
      const limit = typeof meta.attempt_limit === "number" ? meta.attempt_limit : null
      const remaining = typeof meta.remaining_attempts === "number" ? meta.remaining_attempts : null
      if (!limit || limit <= 0 || remaining === null) {
        return null
      }
      return t("auth:mfa.otp.attemptsRemaining", { count: Math.max(remaining, 0) })
    },
    [t]
  )

  const otpHelperText = useMemo(
    () => formatRemainingAttempts(otpChallenge),
    [formatRemainingAttempts, otpChallenge]
  )

  useEffect(() => {
    if (!loginChallenge) {
      setMfaBusy(false)
      setMfaError(null)
      setMfaErrorSource(null)
    }
  }, [loginChallenge])

  useEffect(() => {
    const t1 = setTimeout(() => {
      if (emailRef.current && emailRef.current.value && !emailMirror)
        setEmailMirror(emailRef.current.value)
      if (passwordRef.current && passwordRef.current.value) setCaps(false)
    }, 250)
    const t2 = setTimeout(() => {
      if (emailRef.current && emailRef.current.value && !emailMirror)
        setEmailMirror(emailRef.current.value)
    }, 1000)
    return () => {
      clearTimeout(t1)
      clearTimeout(t2)
    }
  }, [emailMirror])

  const applySuggestion = () => {
    if (emailSuggestion && emailRef.current) {
      emailRef.current.value = emailSuggestion
      setEmailMirror(emailSuggestion)
      setEmailSuggestion(null)
    }
  }

  const handleEmailBlur = () => {
    const val = (emailRef.current?.value || "").trim()
    const s = suggestEmailDomain(val)
    setEmailSuggestion(s && s !== val ? s : null)
  }

  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const formData = new FormData(event.currentTarget)
    const username = String(formData.get("username") ?? "").trim()
    const passwordValue = String(formData.get("password") ?? "")

    if (!emailRe.test(username)) {
      setSubmitError(t("auth:messages.invalidEmail"))
      emailRef.current?.focus()
      return
    }

    if (!passwordValue) {
      setSubmitError(t("auth:messages.passwordRequired"))
      passwordRef.current?.focus()
      return
    }

    setSubmitError(null)
    setSubmitting(true)
    setPendingEmail(username)
    try {
      const challenge = await login(username, passwordValue)

      if (remember) {
        localStorage.setItem("auth:lastEmail", username)
        savedEmail.current = username
      }
      localStorage.setItem("auth:remember", remember ? "1" : "0")

      if (challenge) {
        setMfaError(null)
        setMfaErrorSource(null)
        return
      }

      navigate("/dashboard")
    } catch (err) {
      const message = err instanceof Error && err.message ? err.message : t("auth:login.error")
      setSubmitError(message)
    } finally {
      setSubmitting(false)
    }
  }

  const handleOtpVerify = useCallback(
    async (code: string) => {
      if (!loginChallenge) {
        setMfaError(t("auth:mfa.errors.expired"))
        setMfaErrorSource("general")
        return
      }
      const challenge = loginChallenge.methods[0]
      if (!challenge) {
        setMfaError(t("auth:mfa.errors.missingChallenge"))
        setMfaErrorSource("general")
        return
      }

      setMfaBusy(true)
      setMfaError(null)
      setMfaErrorSource(null)

      try {
        await submitMfaChallenge({
          code,
          challengeToken: challenge.challenge_token,
        })
        navigate("/dashboard")
      } catch (err) {
        if (err instanceof ChallengeLockedError) {
          setMfaError(err.message)
          setMfaErrorSource("general")
        } else {
          const message =
            err instanceof Error && err.message ? err.message : t("auth:mfa.errors.generic")
          setMfaError(message)
          setMfaErrorSource("totp")
        }
      } finally {
        setMfaBusy(false)
      }
    },
    [loginChallenge, navigate, submitMfaChallenge, t]
  )

  const activeEmail = pendingEmail || currentEmail || savedEmail.current || ""
  const generalMfaError = mfaErrorSource === "general" ? mfaError : null

  const heroHighlights = [
    {
      icon: ShieldCheck,
      title: t("auth:login.highlightSecurity", {
        defaultValue: "Многоуровневая защита",
      }),
      description: t("auth:login.highlightSecurityDescription", {
        defaultValue: "MFA и интеллектуальные подсказки для безошибочного входа.",
      }),
    },
    {
      icon: Sparkles,
      title: t("auth:login.highlightExperience", {
        defaultValue: "Премиальный опыт",
      }),
      description: t("auth:login.highlightExperienceDescription", {
        defaultValue: "Продуманный интерфейс, вдохновляющий с первого экрана.",
      }),
    },
    {
      icon: BookOpen,
      title: t("auth:login.highlightContent", {
        defaultValue: "Весь кампус под рукой",
      }),
      description: t("auth:login.highlightContentDescription", {
        defaultValue: "События, профиль и обучение — всё доступно после входа.",
      }),
    },
  ]

  const statPills = [
    {
      value: t("auth:login.statStudents", { defaultValue: "120k+" }),
      label: t("auth:login.statStudentsLabel", { defaultValue: "студентов доверяют" }),
    },
    {
      value: t("auth:login.statSatisfaction", { defaultValue: "98%" }),
      label: t("auth:login.statSatisfactionLabel", { defaultValue: "удовлетворённость" }),
    },
  ]

  if (loginChallenge) {
    return (
      <div className="relative min-h-screen w-full bg-[color:var(--page-bg)] text-[color:var(--page-text)]">
        <ParticleAuthBackground />
        <div className="relative z-10 flex min-h-screen items-center justify-center px-4 py-12 sm:px-6 lg:px-8">
          <div className="w-full max-w-2xl rounded-[2rem] border border-[color:color-mix(in_srgb,var(--glass-border)_80%,transparent)] bg-[color:color-mix(in_srgb,var(--card-bg)_95%,rgba(255,255,255,0.08)_5%)] p-8 shadow-[0_35px_80px_rgba(15,23,42,0.35)] backdrop-blur-2xl">
            <div className="flex flex-col items-center gap-6 text-center">
              <div className="inline-flex items-center gap-2 rounded-full border border-[color:color-mix(in_srgb,var(--glass-border)_80%,transparent)] bg-[color:color-mix(in_srgb,var(--card-bg)_92%,rgba(255,255,255,0.14)_8%)] px-4 py-1 text-sm font-semibold tracking-wide text-[color:color-mix(in_srgb,var(--page-text)_90%,var(--nav-link)_10%)]">
                <ShieldCheck className="h-4 w-4" aria-hidden="true" />
                {t("auth:mfa.verifyTitle")}
              </div>
              <div className="space-y-3">
                <h1 className="text-3xl font-extrabold leading-tight sm:text-4xl">
                  {t("auth:mfa.verifySubtitle", {
                    email: activeEmail || t("auth:mfa.unknownEmail"),
                  })}
                </h1>
              </div>

              {generalMfaError ? (
                <div className="w-full rounded-2xl border border-red-400/50 bg-red-400/10 px-4 py-3 text-sm font-semibold text-red-200 dark:text-red-100">
                  {generalMfaError}
                </div>
              ) : null}

              {otpChallenge ? (
                <div className="w-full">
                  <OtpEntry
                    loading={mfaBusy}
                    error={mfaErrorSource === "totp" ? mfaError : null}
                    helperText={otpHelperText ?? null}
                    onSubmit={handleOtpVerify}
                  />
                </div>
              ) : (
                <div className="w-full rounded-2xl border border-amber-400/40 bg-amber-400/10 px-4 py-3 text-sm font-semibold text-amber-200">
                  {t("auth:mfa.noMethods")}
                </div>
              )}

              <button
                type="button"
                onClick={() => window.location.reload()}
                className="inline-flex items-center gap-2 rounded-full border border-[color:color-mix(in_srgb,var(--nav-link)_50%,transparent)] px-5 py-2 text-sm font-semibold text-[color:var(--nav-link)] transition hover:bg-[color:color-mix(in_srgb,var(--nav-link)_12%,transparent)]"
              >
                <Zap className="h-4 w-4" aria-hidden="true" />
                {t("auth:mfa.startOver")}
              </button>
            </div>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="relative min-h-screen w-full overflow-hidden bg-[color:var(--page-bg)] text-[color:var(--page-text)]">
      <ParticleAuthBackground />
      <div className="relative z-10 mx-auto flex min-h-screen w-full max-w-6xl flex-col items-center justify-center gap-10 px-4 py-12 sm:px-6 lg:px-8 lg:flex-row">
        <div className="w-full rounded-[2.4rem] border border-[color:color-mix(in_srgb,var(--glass-border)_80%,transparent)] bg-[color:color-mix(in_srgb,var(--card-bg)_94%,rgba(255,255,255,0.1)_6%)] p-8 shadow-[0_30px_90px_rgba(15,23,42,0.28)] backdrop-blur-3xl lg:p-12">
          <p className="text-sm font-semibold uppercase tracking-[0.3em] text-[color:color-mix(in_srgb,var(--page-text)_70%,var(--nav-link)_30%)]">
            {t("auth:login.heroBadge", { defaultValue: "University Ecosystem" })}
          </p>
          <h1 className="mt-4 text-4xl font-extrabold leading-tight text-[color:var(--page-text)] sm:text-5xl">
            {t("auth:login.heroHeading", {
              defaultValue: "Добро пожаловать в кампус нового поколения",
            })}
          </h1>
          <p className="mt-4 text-lg leading-relaxed text-[color:color-mix(in_srgb,var(--page-text)_82%,var(--secondary-text)_18%)]">
            {t("auth:login.heroDescription", {
              defaultValue:
                "Войдите, чтобы управлять расписанием, следить за событиями и общаться с наставниками в единой цифровой среде.",
            })}
          </p>

          <div className="mt-8 grid gap-4 sm:grid-cols-2">
            {heroHighlights.map(({ icon: Icon, title, description }) => (
              <div
                key={title}
                className="group relative overflow-hidden rounded-3xl border border-[color:color-mix(in_srgb,var(--glass-border)_85%,transparent)] bg-[color:color-mix(in_srgb,var(--card-bg)_96%,rgba(255,255,255,0.08)_4%)] px-5 py-6 shadow-[0_20px_50px_rgba(15,23,42,0.18)] transition-transform duration-300 hover:-translate-y-1"
              >
                <div className="flex items-center gap-3">
                  <span className="flex size-12 items-center justify-center rounded-2xl bg-[color:color-mix(in_srgb,var(--nav-link)_15%,transparent)] text-[color:var(--nav-link)]">
                    <Icon className="h-5 w-5" aria-hidden="true" />
                  </span>
                  <p className="text-base font-semibold">{title}</p>
                </div>
                <p className="mt-4 text-sm text-[color:color-mix(in_srgb,var(--page-text)_78%,var(--secondary-text)_22%)]">
                  {description}
                </p>
              </div>
            ))}
          </div>

          <div className="mt-10 flex flex-wrap gap-4">
            {statPills.map((pill) => (
              <div key={pill.label} className={badgeClass}>
                <span className="text-2xl font-extrabold">{pill.value}</span>
                <span className="text-xs uppercase tracking-[0.2em] opacity-80">{pill.label}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="w-full max-w-xl rounded-[2.4rem] border border-[color:color-mix(in_srgb,var(--glass-border)_80%,transparent)] bg-[color:color-mix(in_srgb,var(--card-bg)_98%,rgba(255,255,255,0.12)_2%)] p-6 shadow-[0_30px_70px_rgba(15,23,42,0.3)] backdrop-blur-2xl sm:p-10">
          <form
            noValidate
            autoComplete="on"
            onSubmit={handleSubmit}
            className="flex flex-col gap-6"
          >
            <div className="space-y-2 text-center">
              <h2 className="text-3xl font-extrabold">{t("auth:login.title")}</h2>
              <p className="text-sm text-[color:color-mix(in_srgb,var(--page-text)_78%,var(--secondary-text)_22%)]">
                {t("auth:login.subtitle", {
                  defaultValue: "Войдите, чтобы продолжить путешествие по университету",
                })}
              </p>
            </div>

            <div className="space-y-2">
              <label
                htmlFor="username"
                className="text-sm font-semibold text-[color:var(--page-text)]"
              >
                {t("auth:fields.email")}
              </label>
              <input
                id="username"
                name="username"
                type="email"
                className={`${inputBaseClass} ${!emailValid ? "border-red-400 focus:border-red-400" : ""}`}
                defaultValue={savedEmail.current}
                ref={emailRef}
                onChange={(e) => setEmailMirror(e.target.value)}
                onBlur={handleEmailBlur}
                autoComplete="username"
                autoFocus
                disabled={submitting}
                inputMode="email"
                required
              />
              <p className="text-xs text-[color:color-mix(in_srgb,var(--page-text)_70%,var(--secondary-text)_30%)]">
                {!emailValid ? t("auth:messages.invalidFormat") : " "}
              </p>
              {emailSuggestion ? (
                <button
                  type="button"
                  onClick={applySuggestion}
                  className="inline-flex items-center gap-2 rounded-full border border-[color:color-mix(in_srgb,var(--nav-link)_60%,transparent)] px-4 py-2 text-xs font-semibold uppercase tracking-[0.2em] text-[color:var(--nav-link)] transition hover:bg-[color:color-mix(in_srgb,var(--nav-link)_12%,transparent)]"
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
                  className="inline-flex items-center gap-2 rounded-full border border-transparent px-3 py-1 text-xs font-semibold uppercase tracking-[0.2em] text-[color:var(--nav-link)] transition hover:border-[color:color-mix(in_srgb,var(--nav-link)_50%,transparent)]"
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
                <input
                  id="password"
                  name="password"
                  type={showPassword ? "text" : "password"}
                  className={inputBaseClass}
                  ref={passwordRef}
                  onKeyUp={(e) => setCaps((e as any).getModifierState?.("CapsLock"))}
                  onKeyDown={(e) => setCaps((e as any).getModifierState?.("CapsLock"))}
                  autoComplete="current-password"
                  disabled={submitting}
                  required
                />
                {caps ? (
                  <span className="absolute inset-y-0 right-4 flex items-center text-xs font-semibold text-amber-400">
                    {t("auth:messages.capsLock")}
                  </span>
                ) : null}
              </div>
            </div>

            <div
              className="min-h-[1.5rem] text-center text-sm font-semibold text-red-400"
              aria-live="assertive"
            >
              {submitError}
            </div>

            <label className="flex items-center gap-3 text-sm font-medium text-[color:color-mix(in_srgb,var(--page-text)_90%,var(--secondary-text)_10%)]">
              <input
                type="checkbox"
                className="size-5 rounded-lg border-[color:color-mix(in_srgb,var(--nav-link)_50%,transparent)] bg-transparent accent-[color:var(--nav-link)]"
                checked={remember}
                onChange={(e) => setRemember(e.target.checked)}
                disabled={submitting}
              />
              {t("auth:actions.rememberEmail")}
            </label>

            <button
              type="submit"
              className="inline-flex w-full items-center justify-center gap-2 rounded-[1.6rem] bg-[radial-gradient(circle_at_top,var(--nav-link),var(--nav-link-hover))] px-6 py-4 text-lg font-extrabold text-white shadow-[0_20px_45px_rgba(36,99,235,0.35)] transition hover:translate-y-[-2px] hover:shadow-[0_30px_60px_rgba(36,99,235,0.45)] disabled:opacity-60"
              disabled={submitting}
            >
              {submitting ? (
                <>
                  <Spinner />
                  {t("auth:login.processing", { defaultValue: "Входим..." })}
                </>
              ) : (
                t("auth:actions.signIn")
              )}
            </button>

            <div className="space-y-2 text-center text-sm">
              <Link
                to="/forgot-password"
                className="font-semibold text-[color:var(--nav-link)] underline-offset-4 transition hover:underline"
              >
                {t("auth:login.forgot")}
              </Link>
              <div>
                {t("auth:login.noAccount")}{" "}
                <Link
                  to="/register"
                  className="font-semibold text-[color:var(--nav-link)] underline-offset-4 transition hover:underline"
                >
                  {t("auth:login.ctaRegister")}
                </Link>
              </div>
            </div>
          </form>
        </div>
      </div>
    </div>
  )
}

export default Login
