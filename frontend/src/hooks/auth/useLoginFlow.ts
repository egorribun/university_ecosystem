/**
 * @fileoverview Login + MFA challenge state machines.
 *
 * Two top-level hooks live here:
 *
 *   1. ``useLoginForm()`` — react-hook-form-driven email/password
 *      login + WebAuthn passkey path. Owns:
 *        * caps-lock + show/hide-password UI state;
 *        * email-suggestion debounce (Levenshtein-fuzzy via
 *          ``suggestEmailDomain``) + apply;
 *        * "remember device" persistence via ``useLocalStorage``
 *          (key: ``auth:trustDevice``);
 *        * ``onSubmit`` that delegates to ``AuthContext.login`` and
 *          either redirects to ``redirectPath`` or hands off to
 *          ``useMfaFlow`` when a challenge is returned;
 *        * ``handlePasskeyLogin`` for WebAuthn navigator.credentials.
 *
 *   2. ``useMfaFlow()`` — drives the MFA challenge views (TOTP code +
 *      WebAuthn). Splits errors into ``totp`` (per-input) vs
 *      ``general`` (banner) sources so the MfaChallengeView can render
 *      them in distinct slots. Locks recover via the
 *      ``ChallengeLockedError`` instance check.
 *
 * The flow as a whole is best verified end-to-end (Track D / Playwright
 * specs) — the unit-level kernel is the deterministic email-suggestion
 * utility (covered by ``utils/authUtils.test.ts``).
 */
import { useCallback, useEffect, useMemo, useState } from "react"
import { useNavigate, useRouterState } from "@tanstack/react-router"
import { useTranslation } from "react-i18next"
import { isAxiosError } from "axios"
import { useForm } from "react-hook-form"
import { valibotResolver } from "@hookform/resolvers/valibot"

import { ChallengeLockedError, useAuth } from "@/contexts/AuthContext"
import type { PendingMfaState } from "@/types/Auth"
import { startAuthentication, browserSupportsWebAuthn } from "@simplewebauthn/browser"
import { useLocalStorage } from "@/hooks/useLocalStorage"
import { suggestEmailDomain } from "@/utils/authUtils"
import { resolveRedirectPath } from "@/utils/redirect"
import { loginSchema, type LoginValues } from "@/features/auth/schemas"

type ChallengeMethod = PendingMfaState["methods"][number]
export type ChallengeWithAttempts = ChallengeMethod &
  Partial<{ attempt_limit: number | null; remaining_attempts: number | null }>

/**
 * State machine for the email/password login screen including the
 * passkey side path. Composes ``react-hook-form`` (validated via
 * Valibot ``loginSchema``) with the project's ``AuthContext.login``,
 * the local ``auth:lastEmail`` / ``auth:trustDevice`` keys, and a
 * fuzzy email-domain suggestion (``suggestEmailDomain``).
 *
 * State transitions of interest:
 *  - submit → ``AuthContext.login`` → either redirect to
 *    ``redirectPath`` or surface a ``pendingMfa`` (which
 *    ``useMfaFlow`` then drives).
 *  - email blur → ``trigger("email")`` then debounced suggestion
 *    population; ``applySuggestion()`` writes the suggested address
 *    back into the form and clears the suggestion banner.
 *  - passkey button → ``loginWithPasskey`` over WebAuthn
 *    ``navigator.credentials`` then redirect.
 *
 * @returns Surface consumed by ``LoginCredentialForm`` —
 *   form instance + caps/showPassword UI flags + suggestion handles
 *   + activeEmail/submitting/error fields + passkey + trustDevice
 *   wires + ``onSubmit`` already wrapped by ``handleSubmit``.
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
  const { login, pendingMfa, loginWithPasskey } = useAuth()

  // Persistence for user convenience
  const [savedEmail, setSavedEmail] = useLocalStorage<string>("auth:lastEmail", "")
  const [trustDeviceStored, setTrustDeviceStored] = useLocalStorage<string>("auth:trustDevice", "0")

  // Local UI state
  const [caps, setCaps] = useState(false)
  const [showPassword, setShowPassword] = useState(false)
  const [emailSuggestion, setEmailSuggestion] = useState<string | null>(null)
  const [passkeyError, setPasskeyError] = useState<string | null>(null)

  // React Hook Form Setup
  const form = useForm<LoginValues>({
    resolver: valibotResolver(loginSchema),
    defaultValues: {
      email: savedEmail,
      password: "",
      trustDevice: trustDeviceStored === "1",
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
  const trustDevice = watch("trustDevice")

  // Update persistence when trustDevice changes
  useEffect(() => {
    setTrustDeviceStored(trustDevice ? "1" : "0")
  }, [trustDevice, setTrustDeviceStored])

  const onSubmit = async (data: LoginValues) => {
    setPasskeyError(null)
    try {
      const challenge = await login(data.email, data.password, !!data.trustDevice)

      if (data.trustDevice) {
        setSavedEmail(data.email)
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

  const handlePasskeyLogin = async () => {
    // We can use the current email from form
    if (!currentEmail || errors.email) {
      await trigger("email")
      if (errors.email) return
    }

    setPasskeyError(null)
    try {
      await loginWithPasskey(currentEmail || "", trustDevice)
      navigate({ to: redirectPath, replace: true })
    } catch (error) {
      let message = t("auth:login.error")
      if (error instanceof Error) message = error.message
      if (isAxiosError(error) && error.response?.data?.detail) {
        message = error.response.data.detail
      }
      setPasskeyError(message)
    }
  }

  const activeEmail = currentEmail || savedEmail || ""
  const webauthnSupported = useMemo(() => browserSupportsWebAuthn(), [])
  const submitting = isSubmitting

  const setTrustDevice = (value: boolean) => {
    setValue("trustDevice", value)
  }

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
    passkeyError,
    webauthnSupported,
    trustDevice, // Exposed for MfaChallengeView
    setTrustDevice, // Exposed for MfaChallengeView
    // Actions
    handlePasskeyLogin,
    onSubmit: handleSubmit(onSubmit),
    // Auth context
    pendingMfa,
  }
}

/**
 * State machine for the post-login MFA challenge screen. Drives both
 * the TOTP code-input and the WebAuthn security-key paths, sharing a
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
 *   pointers (``otpChallenge`` / ``webauthnChallenge``), busy +
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
  const [mfaErrorSource, setMfaErrorSource] = useState<"totp" | "general" | null>(null)

  const loginChallenge = useMemo(
    () => (pendingMfa?.reason === "login" ? pendingMfa : null),
    [pendingMfa]
  )

  const otpChallenge = useMemo(
    () => loginChallenge?.methods?.find((c) => c.method === "totp"),
    [loginChallenge]
  ) as ChallengeWithAttempts | undefined

  const webauthnChallenge = useMemo(
    () => loginChallenge?.methods?.find((c) => c.method === "webauthn"),
    [loginChallenge]
  )

  const generalMfaError = mfaErrorSource === "general" ? mfaError : null

  const handleOtpVerify = useCallback(
    async (code: string, trustDevice: boolean) => {
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

  const handleWebAuthnVerify = useCallback(
    async (trustDevice: boolean) => {
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
        setMfaErrorSource("general")
      } finally {
        setMfaBusy(false)
      }
    },
    [loginChallenge, webauthnChallenge, navigate, submitMfaChallenge, t, redirectPath]
  )

  const [showRecoveryInput, setShowRecoveryInput] = useState(false)

  const handleRecoveryVerify = useCallback(
    async (code: string, trustDevice: boolean) => {
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
          trustDevice,
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
    webauthnChallenge,
    mfaBusy,
    mfaError,
    mfaErrorSource,
    generalMfaError,
    setMfaError,
    setMfaErrorSource,
    handleOtpVerify,
    handleWebAuthnVerify,
    showRecoveryInput,
    setShowRecoveryInput,
    handleRecoveryVerify,
  } as const
}
