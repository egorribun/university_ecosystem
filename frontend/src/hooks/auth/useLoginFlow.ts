/**
 * @fileoverview Login + MFA challenge state machines.
 *
 * Two top-level hooks live here:
 *
 *   1. ``useLoginForm()`` — react-hook-form-driven email/password
 *      login path. Owns:
 *        * caps-lock + show/hide-password UI state;
 *        * email-suggestion debounce (Levenshtein-fuzzy via
 *          ``suggestEmailDomain``) + apply;
 *        * email-only persistence via ``useLocalStorage``
 *          (key: ``auth:lastEmail``); trusted-device consent is never persisted;
 *        * ``onSubmit`` that delegates to ``AuthContext.login`` and
 *          either redirects to ``redirectPath`` or hands off to
 *          ``useMfaFlow`` when a challenge is returned;
 *
 *   2. ``useMfaFlow()`` — drives the MFA challenge views (TOTP, email OTP,
 *      and recovery codes). Splits errors into per-input vs
 *      ``general`` (banner) sources so the MfaChallengeView can render
 *      them in distinct slots. Locks recover via the
 *      ``ChallengeLockedError`` instance check.
 *
 * The flow as a whole is best verified end-to-end (Track D / Playwright
 * specs) — the unit-level kernel is the deterministic email-suggestion
 * utility (covered by ``utils/authUtils.test.ts``).
 */
import { useCallback, useEffect, useMemo, useState, type BaseSyntheticEvent } from "react"
import { useNavigate, useRouterState } from "@tanstack/react-router"
import { useTranslation } from "react-i18next"
import { isAxiosError } from "axios"
import { useForm } from "react-hook-form"
import { valibotResolver } from "@hookform/resolvers/valibot"

import { ChallengeLockedError, useAuth } from "@/contexts/AuthContext"
import type { PendingMfaState } from "@/types/Auth"
import { resendEmailMfaChallenge } from "@/api/mfa"
import { useLocalStorage } from "@/hooks/useLocalStorage"
import { suggestEmailDomain } from "@/utils/authUtils"
import { resolveRedirectPath } from "@/utils/redirect"
import { loginSchema, type LoginValues } from "@/features/auth/schemas"
import {
  captureActiveTelemetryContext,
  type CapturedTelemetryContext,
} from "@/utils/telemetryContext"

type ChallengeMethod = PendingMfaState["methods"][number]
export type ChallengeWithAttempts = ChallengeMethod &
  Partial<{ attempt_limit: number | null; remaining_attempts: number | null }>

/**
 * State machine for the email/password login screen. Composes
 * ``react-hook-form`` (validated via
 * Valibot ``loginSchema``) with the project's ``AuthContext.login``,
 * the local ``auth:lastEmail`` key, and a
 * fuzzy email-domain suggestion (``suggestEmailDomain``).
 *
 * State transitions of interest:
 *  - submit → ``AuthContext.login`` → either redirect to
 *    ``redirectPath`` or surface a ``pendingMfa`` (which
 *    ``useMfaFlow`` then drives).
 *  - email blur → ``trigger("email")`` then debounced suggestion
 *    population; ``applySuggestion()`` writes the suggested address
 *    back into the form and clears the suggestion banner.
 *    ``navigator.credentials`` then redirect.
 *
 * @returns Surface consumed by ``LoginCredentialForm`` —
 *   form instance + caps/showPassword UI flags + suggestion handles
 *   + activeEmail/submitting/error fields + ``onSubmit`` already
 *   wrapped by ``handleSubmit``.
 */
export function useLoginForm() {
  const { t } = useTranslation(["auth"])
  const navigate = useNavigate()
  // W179 SW4 — read TanStack canonical `search.redirect` (matches _auth.tsx:47
  // writer) instead of legacy `location.state.from.pathname` (React Router
  // pattern that writer never sets, so pre-W179 redirectPath was always the
  // fallback /dashboard regardless of unauth deep-link origin). Closes W177
  // §Honesty #3 race condition. See frontend/src/utils/redirect.ts for the
  // shared helper used by Login.tsx + _public.tsx + here (3-place dedup).
  const search = useRouterState({ select: (s) => s.location.search })
  const redirectPath = resolveRedirectPath((search as { redirect?: unknown } | null)?.redirect)
  const { login, pendingMfa } = useAuth()

  // Persistence for user convenience
  const [savedEmail, setSavedEmail] = useLocalStorage<string>("auth:lastEmail", "")

  // Local UI state
  const [caps, setCaps] = useState(false)
  const [showPassword, setShowPassword] = useState(false)
  const [emailSuggestion, setEmailSuggestion] = useState<string | null>(null)

  // React Hook Form Setup
  const form = useForm<LoginValues>({
    resolver: valibotResolver(loginSchema),
    defaultValues: {
      email: savedEmail,
      password: "",
      rememberEmail: Boolean(savedEmail),
      trustDevice: false,
    },
    mode: "onBlur", // Validate on blur for better UX
  })

  const {
    handleSubmit,
    setValue,
    watch,
    setError,
    formState: { errors, isSubmitting },
    trigger,
  } = form

  // Watch values for UI logic
  const currentEmail = watch("email")

  const onSubmit = async (data: LoginValues, telemetryContext: CapturedTelemetryContext) => {
    try {
      const challenge = await telemetryContext.run(() =>
        login(data.email, data.password, !!data.trustDevice)
      )

      if (data.rememberEmail) {
        setSavedEmail(data.email)
      } else {
        setSavedEmail("")
      }

      if (challenge) {
        return // Handled by MFA flow
      }

      navigate({ to: redirectPath, replace: true })
    } catch (error) {
      let message = t("auth:login.error")
      if (error instanceof Error && error.message) {
        message = error.message
      }
      if (isAxiosError(error) && error.response?.data?.detail) {
        message = error.response.data.detail
      }
      // Set root error
      setError("root", { type: "server", message })
    }
  }

  const handleTelemetrySubmit = (event?: BaseSyntheticEvent) => {
    const telemetryContext = captureActiveTelemetryContext()
    return handleSubmit((data) => onSubmit(data, telemetryContext))(event)
  }

  const handleEmailBlur = async () => {
    // Trigger validation first
    await trigger("email")
    const raw = currentEmail?.trim()
    if (!raw) return
    const suggestion = suggestEmailDomain(raw)
    setEmailSuggestion(suggestion && suggestion !== raw ? suggestion : null)
  }

  const applySuggestion = () => {
    if (!emailSuggestion) return
    setValue("email", emailSuggestion, { shouldValidate: true })
    setEmailSuggestion(null)
  }

  const activeEmail = currentEmail || savedEmail || ""
  const submitting = isSubmitting

  return {
    // Form instance
    form,
    savedEmail, // Exposed for default value logic if needed elsewhere
    // State
    caps,
    setCaps,
    showPassword,
    setShowPassword,
    emailSuggestion,
    applySuggestion,
    handleEmailBlur,
    // Computed
    activeEmail,
    submitting,
    submitError: errors.root?.message,
    // Actions
    onSubmit: handleTelemetrySubmit,
    // Auth context
    pendingMfa,
  }
}

/**
 * State machine for the post-login MFA challenge screen. Drives TOTP,
 * email OTP, and recovery-code paths, sharing a
 * single ``mfaBusy`` flag and a split error model:
 *  - ``mfaError`` + ``mfaErrorSource: "totp"`` — render under the
 *    OTP digit row (per-input feedback);
 *  - ``mfaError`` + ``mfaErrorSource: "general"`` — render in the
 *    page-level banner (e.g. challenge expired, account locked).
 *
 * ``ChallengeLockedError`` is the only error class that always
 * routes to the general banner regardless of which method triggered
 * it — anything else from the TOTP path stays in the per-input
 * source so the user can correct + retry without losing context.
 *
 * @returns Handles consumed by ``MfaChallengeView``: split challenge
 *   pointers (``otpChallenge`` / ``emailChallenge``), busy +
 *   error state, the two verify callbacks, and error setters for
 *   the optimistic-clear path on subsequent input.
 */
export function useMfaFlow() {
  const { t } = useTranslation(["auth"])
  const navigate = useNavigate()
  const locationState = useRouterState({ select: (s) => s.location.state })
  const { pendingMfa, submitMfaChallenge } = useAuth()

  const state = locationState as { from?: { pathname: string } } | null
  const redirectPath = state?.from?.pathname || "/dashboard"

  const [mfaBusy, setMfaBusy] = useState(false)
  const [mfaError, setMfaError] = useState<string | null>(null)
  const [mfaErrorSource, setMfaErrorSource] = useState<"totp" | "email_otp" | "general" | null>(
    null
  )

  const loginChallenge = useMemo(
    () => (pendingMfa?.reason === "login" ? pendingMfa : null),
    [pendingMfa]
  )

  const otpChallenge = useMemo(
    () => loginChallenge?.methods?.find((c) => c.method === "totp"),
    [loginChallenge]
  ) as ChallengeWithAttempts | undefined

  const initialEmailChallenge = useMemo(
    () => loginChallenge?.methods?.find((challenge) => challenge.method === "email_otp"),
    [loginChallenge]
  )
  const [emailChallenge, setEmailChallenge] = useState(initialEmailChallenge)
  const [resendNow, setResendNow] = useState(() => Date.now())

  useEffect(() => {
    setEmailChallenge(initialEmailChallenge)
  }, [initialEmailChallenge])

  const resendAvailableAt = emailChallenge?.resend_available_at
    ? Date.parse(emailChallenge.resend_available_at)
    : Number.NaN
  const resendSeconds = Number.isFinite(resendAvailableAt)
    ? Math.max(0, Math.ceil((resendAvailableAt - resendNow) / 1000))
    : 0

  useEffect(() => {
    if (!emailChallenge || resendSeconds <= 0) return
    const timer = window.setTimeout(() => setResendNow(Date.now()), 1000)
    return () => window.clearTimeout(timer)
  }, [emailChallenge, resendSeconds])

  const generalMfaError = mfaErrorSource === "general" ? mfaError : null

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
        })
        navigate({ to: redirectPath, replace: true })
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
    [loginChallenge, otpChallenge, navigate, submitMfaChallenge, t, redirectPath]
  )

  const handleEmailOtpVerify = useCallback(
    async (code: string) => {
      if (!loginChallenge || !emailChallenge) {
        setMfaError(t("auth:mfa.errors.expired"))
        setMfaErrorSource("general")
        return
      }

      setMfaBusy(true)
      setMfaError(null)
      setMfaErrorSource(null)

      try {
        await submitMfaChallenge({
          method: "email_otp",
          code,
          challengeToken: emailChallenge.challenge_token,
        })
        navigate({ to: redirectPath, replace: true })
      } catch (error) {
        let message = t("auth:mfa.errors.generic")
        if (error instanceof Error && error.message) {
          message = error.message
        }
        if (isAxiosError(error) && error.response?.data?.detail) {
          message = error.response.data.detail
        }
        setMfaError(message)
        setMfaErrorSource(error instanceof ChallengeLockedError ? "general" : "email_otp")
      } finally {
        setMfaBusy(false)
      }
    },
    [emailChallenge, loginChallenge, navigate, redirectPath, submitMfaChallenge, t]
  )

  const handleResendEmailOtp = useCallback(async () => {
    if (!emailChallenge || resendSeconds > 0) return
    setMfaBusy(true)
    setMfaError(null)
    setMfaErrorSource(null)
    try {
      const rotated = await resendEmailMfaChallenge(emailChallenge.challenge_token)
      setEmailChallenge(rotated)
      setResendNow(Date.now())
    } catch (error) {
      let message = t("auth:mfa.errors.generic")
      if (error instanceof Error && error.message) message = error.message
      if (isAxiosError(error) && error.response?.data?.detail) {
        message = error.response.data.detail
      }
      setMfaError(message)
      setMfaErrorSource("general")
    } finally {
      setMfaBusy(false)
    }
  }, [emailChallenge, resendSeconds, t])

  const [showRecoveryInput, setShowRecoveryInput] = useState(false)

  const handleRecoveryVerify = useCallback(
    async (code: string) => {
      const challengeToken = loginChallenge?.methods?.[0]?.challenge_token
      if (!loginChallenge || !challengeToken) {
        setMfaError(t("auth:mfa.errors.expired"))
        setMfaErrorSource("general")
        return
      }

      setMfaBusy(true)
      setMfaError(null)
      setMfaErrorSource(null)

      try {
        await submitMfaChallenge({
          method: "recovery_code",
          code,
          challengeToken,
        })
        navigate({ to: redirectPath, replace: true })
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
          setMfaErrorSource("general")
        }
      } finally {
        setMfaBusy(false)
      }
    },
    [loginChallenge, navigate, submitMfaChallenge, t, redirectPath]
  )

  return {
    loginChallenge,
    otpChallenge,
    emailChallenge,
    resendSeconds,
    mfaBusy,
    mfaError,
    mfaErrorSource,
    generalMfaError,
    setMfaError,
    setMfaErrorSource,
    handleOtpVerify,
    handleEmailOtpVerify,
    handleResendEmailOtp,
    showRecoveryInput,
    setShowRecoveryInput,
    handleRecoveryVerify,
  } as const
}
