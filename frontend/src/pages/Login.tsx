import { useCallback, useEffect, useMemo, useRef, useState, useActionState } from "react"
import { Link, useNavigate, useLocation } from "react-router-dom"
import { useTranslation } from "react-i18next"
import {
  Calendar,
  MessageCircle,
  Newspaper,
  Eye,
  EyeOff,
  Zap,
  ShieldCheck,
  Sparkles,
} from "lucide-react"
import { motion } from "framer-motion"
import { ChallengeLockedError, useAuth } from "@/contexts/AuthContext"
import type { PendingMfaState } from "@/types/Auth"
import { isAxiosError } from "axios"
import OtpEntry from "@/components/mfa/OtpEntry"
import ParticleAuthBackground from "@/components/ui/ParticleAuthBackground"
import { Input } from "@/components/ui/Input"
import { startAuthentication, browserSupportsWebAuthn } from "@simplewebauthn/browser"
import { Fingerprint } from "lucide-react"
import { useLocalStorage } from "@/hooks/useLocalStorage"
import { levenshtein } from "@/utils/levenshtein"
import { COMMON_EMAIL_DOMAINS } from "@/constants/emailDomains"

type ChallengeMethod = PendingMfaState["methods"][number]
type ChallengeWithAttempts = ChallengeMethod &
  Partial<{ attempt_limit: number | null; remaining_attempts: number | null }>

const emailRe = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

function suggestEmailDomain(email: string) {
  const atIndex = email.indexOf("@")
  if (atIndex < 0) return null

  const localPart = email.slice(0, atIndex).trim()
  const domain = email
    .slice(atIndex + 1)
    .trim()
    .toLowerCase()

  if (!localPart || !domain) return null
  if ((COMMON_EMAIL_DOMAINS as ReadonlyArray<string>).includes(domain)) return null

  let bestMatch: { domain: string; distance: number } | null = null
  for (const candidate of COMMON_EMAIL_DOMAINS) {
    const distance = levenshtein(domain, candidate)
    if (distance <= 2 && (!bestMatch || distance < bestMatch.distance)) {
      bestMatch = { domain: candidate, distance }
    }
  }
  return bestMatch ? `${localPart}@${bestMatch.domain}` : null
}

const badgeClass =
  "inline-flex w-40 items-baseline justify-center gap-2 rounded-full border border-glass-border-subtle/(--opacity-hover) " +
  "bg-glass backdrop-blur-md px-4 py-2 text-sm font-semibold " +
  "text-(--text-primary)/(--opacity-heavy) shadow-sm"

const Spinner = () => (
  <span
    className="inline-flex h-5 w-5 animate-spin rounded-full border-2 border-current/(--opacity-strong) border-t-transparent"
    aria-hidden="true"
  />
)

const Login = () => {
  const { t } = useTranslation(["auth"])
  const navigate = useNavigate()
  const location = useLocation()
  const { login, pendingMfa, submitMfaChallenge, loginWithPasskey } = useAuth()

  const state = location.state as { from?: { pathname: string } } | null
  const redirectPath = state?.from?.pathname || "/dashboard"

  const [savedEmail, setSavedEmail] = useLocalStorage<string>("auth:lastEmail", "")
  // Keep savedEmail ref for internal logic consistency with minimum changes
  const savedEmailRef = useRef(savedEmail)
  useEffect(() => {
    savedEmailRef.current = savedEmail
  }, [savedEmail])

  const [trustDeviceStored, setTrustDeviceStored] = useLocalStorage<string>("auth:trustDevice", "0")
  const [trustDevice, setTrustDevice] = useState<boolean>(trustDeviceStored === "1")

  // Sync trustDevice state back to storage
  useEffect(() => {
    setTrustDeviceStored(trustDevice ? "1" : "0")
  }, [trustDevice, setTrustDeviceStored])

  const [caps, setCaps] = useState(false)
  const [showPassword, setShowPassword] = useState(false)
  const [emailSuggestion, setEmailSuggestion] = useState<string | null>(null)
  const [emailMirror, setEmailMirror] = useState(savedEmail)

  const emailRef = useRef<HTMLInputElement | null>(null)
  const passwordRef = useRef<HTMLInputElement | null>(null)

  const currentEmail = (emailRef.current?.value ?? emailMirror ?? "").trim()
  const emailValid = useMemo(
    () => currentEmail.length === 0 || emailRe.test(currentEmail),
    [currentEmail]
  )

  const [pendingEmail, setPendingEmail] = useState<string | null>(savedEmail ? savedEmail : null)
  const [mfaBusy, setMfaBusy] = useState(false)
  const [mfaError, setMfaError] = useState<string | null>(null)
  const [mfaErrorSource, setMfaErrorSource] = useState<"totp" | "general" | null>(null)

  const [submitting, setSubmitting] = useState(false)

  const [submitError, submitAction, isPending] = useActionState(
    async (_previousState: string | null, formData: FormData) => {
      const username = String(formData.get("username") ?? "").trim()
      const passwordValue = String(formData.get("password") ?? "")

      if (!emailRe.test(username)) {
        emailRef.current?.focus()
        return t("auth:messages.invalidEmail")
      }

      if (!passwordValue) {
        passwordRef.current?.focus()
        return t("auth:messages.passwordRequired")
      }

      setPendingEmail(username)

      try {
        const challenge = await login(username, passwordValue, trustDevice)

        if (trustDevice) {
          setSavedEmail(username)
        }

        if (challenge) {
          setMfaError(null)
          setMfaErrorSource(null)
          return null
        }

        navigate(redirectPath, { replace: true })
        return null
      } catch (error) {
        let message = t("auth:login.error")
        if (error instanceof Error && error.message) {
          message = error.message
        }
        if (isAxiosError(error) && error.response?.data?.detail) {
          message = error.response.data.detail
        }
        return message
      }
    },
    null
  )

  // Sync submitting state for other parts of UI (like passkey) if needed,
  // or just use isPending for the form.
  // Note: handlePasskeyLogin still uses 'submitting' state.
  // We keep 'submitting' for passkey but use 'isPending' for form.

  const [passkeyError, setPasskeyError] = useState<string | null>(null)

  const otpHelperText = null

  const handleEmailBlur = () => {
    const raw = (emailRef.current?.value ?? "").trim()
    if (!raw) return
    const suggestion = suggestEmailDomain(raw)
    setEmailSuggestion(suggestion)
  }

  const applySuggestion = () => {
    if (!emailSuggestion || !emailRef.current) return
    emailRef.current.value = emailSuggestion
    setEmailMirror(emailSuggestion)
    setEmailSuggestion(null)
    emailRef.current.focus()
  }

  const loginChallenge = useMemo(
    () => (pendingMfa?.reason === "login" ? pendingMfa : null),
    [pendingMfa]
  )

  const otpChallenge = useMemo(
    () => loginChallenge?.challenges?.find((c) => c.method === "totp"),
    [loginChallenge]
  ) as ChallengeWithAttempts | undefined

  const webauthnChallenge = useMemo(
    () => loginChallenge?.challenges?.find((c) => c.method === "webauthn"),
    [loginChallenge]
  )

  // Check if browser supports WebAuthn (requires secure context: HTTPS or localhost)
  const webauthnSupported = useMemo(() => browserSupportsWebAuthn(), [])

  const handlePasskeyLogin = async () => {
    const email = (emailRef.current?.value ?? emailMirror ?? "").trim()
    if (!emailRe.test(email)) {
      setPasskeyError(t("auth:messages.invalidEmail"))
      emailRef.current?.focus()
      return
    }

    setPasskeyError(null)
    setSubmitting(true)
    try {
      await loginWithPasskey(email, trustDevice)
      navigate(redirectPath, { replace: true })
    } catch (error) {
      let message = t("auth:login.error")
      if (error instanceof Error) message = error.message
      if (isAxiosError(error) && error.response?.data?.detail) {
        message = error.response.data.detail
      }
      setPasskeyError(message)
    } finally {
      setSubmitting(false)
    }
  }

  const handleOtpVerify = useCallback(
    async (code: string) => {
      if (!loginChallenge || !otpChallenge) {
        setMfaError(t("auth:mfa.errors.expired"))
        setMfaErrorSource("general")
        return
      }

      setMfaBusy(true)
      setMfaError(null)
      setMfaErrorSource(null)

      try {
        await submitMfaChallenge({
          method: "totp",
          code,
          challengeToken: otpChallenge.challenge_token,
          trustDevice,
        })
        navigate(redirectPath, { replace: true })
      } catch (error) {
        if (error instanceof ChallengeLockedError) {
          setMfaError(error.message)
          setMfaErrorSource("general")
        } else {
          let message = t("auth:mfa.errors.generic")
          if (error instanceof Error && error.message) {
            message = error.message
          }
          if (isAxiosError(error) && error.response?.data?.detail) {
            message = error.response.data.detail
          }
          setMfaError(message)
          setMfaErrorSource("totp")
        }
      } finally {
        setMfaBusy(false)
      }
    },
    [loginChallenge, otpChallenge, navigate, submitMfaChallenge, t, trustDevice]
  )

  const handleWebAuthnVerify = useCallback(async () => {
    if (!loginChallenge || !webauthnChallenge || !webauthnChallenge.options) {
      setMfaError(t("auth:mfa.errors.expired"))
      setMfaErrorSource("general")
      return
    }

    setMfaBusy(true)
    setMfaError(null)
    setMfaErrorSource(null)

    try {
      const response = await startAuthentication({
        optionsJSON: webauthnChallenge.options as unknown as Parameters<
          typeof startAuthentication
        >[0]["optionsJSON"],
      })

      await submitMfaChallenge({
        method: "webauthn",
        webauthnResponse: response,
        challengeToken: webauthnChallenge.challenge_token,
        trustDevice,
      })
      navigate(redirectPath, { replace: true })
    } catch (error) {
      let message = t("auth:mfa.errors.generic")
      if (error instanceof Error && error.message) {
        message = error.message
      }
      if (isAxiosError(error) && error.response?.data?.detail) {
        message = error.response.data.detail
      }
      setMfaError(message)
      setMfaErrorSource("general")
    } finally {
      setMfaBusy(false)
    }
  }, [loginChallenge, webauthnChallenge, navigate, submitMfaChallenge, t, trustDevice])

  const activeEmail = pendingEmail || currentEmail || savedEmail || ""
  const generalMfaError = mfaErrorSource === "general" ? mfaError : null

  const heroHighlights = [
    {
      icon: Calendar,
      title: t("auth:login.highlightSchedule", {
        defaultValue: "Расписание занятий",
      }),
      description: t("auth:login.highlightScheduleDescription", {
        defaultValue: "Актуальное расписание пар, экзаменов и консультаций.",
      }),
    },
    {
      icon: Newspaper,
      title: t("auth:login.highlightNews", {
        defaultValue: "Новости и мероприятия",
      }),
      description: t("auth:login.highlightNewsDescription", {
        defaultValue: "Будьте в курсе университетской жизни и важных событий.",
      }),
    },
    {
      icon: MessageCircle,
      title: t("auth:login.highlightMessenger", {
        defaultValue: "Мессенджер",
      }),
      description: t("auth:login.highlightMessengerDescription", {
        defaultValue: "Общайтесь с одногруппниками и преподавателями.",
      }),
    },
  ]

  const statPills = [
    {
      icon: Zap,
      value: t("auth:login.statFast", { defaultValue: "Быстро" }),
      label: t("auth:login.statFastLabel", { defaultValue: "и безопасно" }),
    },
    {
      icon: Sparkles,
      value: t("auth:login.statSmart", { defaultValue: "Удобный и умный интерфейс" }),
    },
  ]

  if (loginChallenge) {
    return (
      <div className="fixed inset-0 min-h-screen w-full bg-linear-to-b from-slate-50 to-slate-100 dark:from-slate-950 dark:to-slate-900">
        <ParticleAuthBackground />
        <div className="relative z-(--z-navbar) flex min-h-screen items-center justify-center px-4 py-12 sm:px-6 lg:px-8">
          <div className="w-full max-w-2xl rounded-4xl glass-high-fidelity p-8">
            <div className="flex flex-col items-center gap-6 text-center">
              <div className="inline-flex items-center gap-2 rounded-full border border-glass-border-subtle bg-(--bg-surface-hover)/(--opacity-subtle) px-4 py-1 text-sm font-semibold tracking-wide text-(--text-primary)">
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
                <div className="w-full rounded-md border border-error-border/(--opacity-medium) bg-error-bg/(--opacity-dim) px-4 py-3 text-sm font-semibold text-error-text">
                  {generalMfaError}
                </div>
              ) : null}

              {webauthnChallenge && (
                <>
                  {webauthnSupported ? (
                    <button
                      type="button"
                      onClick={handleWebAuthnVerify}
                      disabled={mfaBusy}
                      className="inline-flex w-full items-center justify-center gap-3 rounded-xl bg-brand/(--opacity-subtle) px-6 py-4 text-lg font-bold text-brand transition hover:bg-brand/(--opacity-dim) disabled:opacity-(--opacity-medium)"
                    >
                      <Fingerprint className="h-6 w-6" />
                      {t("auth:mfa.webauthn.useSecurityKey", {
                        defaultValue: "Использовать ключ безопасности",
                      })}
                    </button>
                  ) : (
                    <div className="w-full rounded-md border border-warning-border/(--opacity-medium) bg-warning-bg/(--opacity-subtle) px-4 py-3 text-sm font-semibold text-warning-text text-center">
                      {t("auth:mfa.webauthn.notSupported", {
                        defaultValue:
                          "WebAuthn недоступен в этом браузере. Используйте HTTPS или код аутентификатора ниже.",
                      })}
                    </div>
                  )}
                </>
              )}

              {otpChallenge && (
                <>
                  {webauthnChallenge && (
                    <div className="relative z-(--z-base) w-full py-2">
                      <div className="absolute inset-0 flex items-center">
                        <div className="w-full border-t border-glass-border-subtle"></div>
                      </div>
                      <div className="relative flex justify-center text-xs uppercase">
                        <span className="bg-(--bg-surface) px-2 text-(--text-secondary)">
                          {t("auth:mfa.or", { defaultValue: "ИЛИ" })}
                        </span>
                      </div>
                    </div>
                  )}

                  <div className="w-full">
                    <OtpEntry
                      loading={mfaBusy}
                      error={mfaErrorSource === "totp" ? mfaError : null}
                      helperText={otpHelperText ?? null}
                      onSubmit={handleOtpVerify}
                    />
                  </div>

                  <label className="flex items-center gap-3 text-sm font-medium text-(--text-primary)">
                    <input
                      type="checkbox"
                      className="size-5 rounded-lg border-brand/(--opacity-medium) bg-transparent accent-brand"
                      checked={trustDevice}
                      onChange={(event) => setTrustDevice(event.target.checked)}
                      disabled={mfaBusy}
                    />
                    {t("auth:actions.trustDevice", { defaultValue: "Доверять этому устройству" })}
                  </label>
                </>
              )}

              {!otpChallenge && !webauthnChallenge && (
                <div className="w-full rounded-md border border-warning-border/(--opacity-medium) bg-warning-bg/(--opacity-subtle) px-4 py-3 text-sm font-semibold text-warning-text">
                  {t("auth:mfa.noMethods")}
                </div>
              )}

              <button
                type="button"
                onClick={() => window.location.reload()}
                className="inline-flex items-center gap-2 rounded-full border border-brand/(--opacity-medium) px-5 py-2 text-sm font-semibold text-brand transition hover:bg-brand/(--opacity-subtle)"
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
    <div className="relative min-h-screen w-full overflow-hidden bg-(--bg-page) text-(--text-primary)">
      <ParticleAuthBackground />
      <div className="relative z-(--z-navbar) mx-auto grid min-h-screen w-full max-w-7xl grid-cols-1 items-stretch gap-12 px-4 py-12 sm:px-6 lg:grid-cols-2 lg:px-8">
        <motion.div
          initial={{ x: -200 }}
          animate={{ x: 0 }}
          transition={{ duration: 0.5, ease: "easeOut" }}
          className="flex w-full min-w-0 flex-col justify-center rounded-4xl border border-glass-border/(--opacity-hover) bg-(--bg-surface)/(--opacity-strong) p-8 shadow-glass backdrop-blur-3xl lg:p-12"
        >
          <p className="text-sm font-semibold uppercase tracking-[0.3em] text-(--text-primary)/(--opacity-strong)">
            {t("auth:login.heroBadge", { defaultValue: "University Ecosystem" })}
          </p>
          <h1 className="mt-4 text-4xl font-extrabold leading-tight text-(--text-primary) sm:text-5xl">
            {t("auth:login.heroHeading", {
              defaultValue: "Добро пожаловать в систему Университета",
            })}
          </h1>
          <p className="mt-4 text-lg leading-relaxed text-(--text-secondary)">
            {t("auth:login.heroDescription", {
              defaultValue:
                "Расписание, новости, мероприятия и мессенджер — всё в одном месте для студентов и преподавателей.",
            })}
          </p>

          <div className="mt-8 grid gap-4 sm:grid-cols-2">
            {heroHighlights.map(({ icon: Icon, title, description }) => (
              <div
                key={title}
                className="group relative overflow-hidden rounded-lg border border-glass-border/(--opacity-heavy) bg-(--bg-surface)/(--opacity-medium) px-5 py-6 shadow-premium transition-transform duration-300 hover:-translate-y-1"
              >
                <div className="relative z-(--z-base) flex items-center gap-3">
                  <span className="flex size-12 items-center justify-center rounded-md bg-brand-subtle-bg text-brand">
                    <Icon className="h-5 w-5" aria-hidden="true" />
                  </span>
                  <p className="text-base font-semibold">{title}</p>
                </div>
                <p className="mt-4 text-sm text-(--text-secondary)">{description}</p>
              </div>
            ))}
          </div>

          <div className="mt-10 flex flex-wrap gap-4">
            {statPills.map((pill, i) => (
              <div key={i} className={badgeClass.replace("items-baseline", "items-center")}>
                <pill.icon className="mr-1 h-4 w-4 text-brand" strokeWidth={3} />
                <span className="text-xs font-extrabold uppercase tracking-[0.2em]">
                  {pill.value}
                </span>
                {pill.label && (
                  <span className="text-xs font-extrabold uppercase tracking-[0.2em]">
                    {pill.label}
                  </span>
                )}
              </div>
            ))}
          </div>
        </motion.div>

        <motion.div
          initial={{ y: 200 }}
          animate={{ y: 0 }}
          transition={{ duration: 0.5, ease: "easeOut", delay: 0.2 }}
          className="flex w-full min-w-0 flex-col justify-center rounded-4xl border border-glass-border/(--opacity-hover) bg-(--bg-surface)/(--opacity-hover) p-6 shadow-glass backdrop-blur-2xl sm:p-10"
        >
          <form noValidate autoComplete="on" action={submitAction} className="flex flex-col gap-6">
            <div className="space-y-2 text-center">
              <h2 className="text-3xl font-extrabold">{t("auth:login.title")}</h2>
              <p className="text-sm text-(--text-secondary)">
                {t("auth:login.subtitle", {
                  defaultValue: "Войдите, чтобы продолжить путешествие по университету",
                })}
              </p>
            </div>

            <div className="space-y-2">
              <label htmlFor="username" className="text-sm font-semibold text-(--text-primary)">
                {t("auth:fields.email")}
              </label>
              <Input
                id="username"
                name="username"
                type="email"
                className={!emailValid ? "border-error-text focus:border-error-text" : ""}
                defaultValue={savedEmail}
                ref={emailRef}
                onChange={(event) => setEmailMirror(event.target.value)}
                onBlur={handleEmailBlur}
                autoComplete="username"
                autoFocus
                disabled={isPending || submitting}
                inputMode="email"
                required
              />
              <p className="text-xs text-(--text-secondary)/(--opacity-hover)">
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

            <label className="flex items-center gap-3 text-sm font-medium text-(--text-primary)">
              <input
                type="checkbox"
                className="size-5 rounded-lg border-brand/(--opacity-medium) bg-transparent accent-brand"
                checked={trustDevice}
                onChange={(e) => setTrustDevice(e.target.checked)}
                disabled={isPending || submitting}
              />
              {t("auth:actions.trustDevice", { defaultValue: "Доверять этому устройству" })}
            </label>

            <div className="flex flex-col gap-3">
              <button
                type="submit"
                className="inline-flex w-full items-center justify-center gap-2 rounded-md bg-linear-to-b from-brand to-brand-hover px-6 py-4 text-lg font-extrabold text-white shadow-premium transition hover:-translate-y-0.5 hover:shadow-glass-strong disabled:opacity-(--opacity-strong)"
                disabled={isPending || submitting}
              >
                {isPending || submitting ? (
                  <>
                    <Spinner />
                    {t("auth:login.processing", { defaultValue: "Входим..." })}
                  </>
                ) : (
                  t("auth:actions.signIn")
                )}
              </button>

              {webauthnSupported && (
                <button
                  type="button"
                  onClick={handlePasskeyLogin}
                  disabled={submitting}
                  className="inline-flex w-full items-center justify-center gap-2 rounded-md border border-brand/(--opacity-medium) bg-brand/(--opacity-subtle) px-6 py-4 text-lg font-extrabold text-brand shadow-surface transition hover:-translate-y-0.5 hover:bg-brand/(--opacity-dim) disabled:opacity-(--opacity-strong)"
                >
                  <Fingerprint className="h-6 w-6" />
                  {t("auth:login.signInWithPasskey", { defaultValue: "Войти с помощью Passkey" })}
                </button>
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
        </motion.div>
      </div>
    </div>
  )
}

export default Login
