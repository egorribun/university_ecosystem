import { useCallback, useEffect, useMemo, useState } from "react"
import { useNavigate, useLocation } from "react-router-dom"
import { useTranslation } from "react-i18next"
import { isAxiosError } from "axios"
import { useForm } from "react-hook-form"
import { valibotResolver } from "@hookform/resolvers/valibot"

import { ChallengeLockedError, useAuth } from "@/contexts/AuthContext"
import type { PendingMfaState } from "@/types/Auth"
import { startAuthentication, browserSupportsWebAuthn } from "@simplewebauthn/browser"
import { useLocalStorage } from "@/hooks/useLocalStorage"
import { suggestEmailDomain } from "@/utils/authUtils"
import { loginSchema, type LoginValues } from "@/features/auth/schemas"

type ChallengeMethod = PendingMfaState["methods"][number]
export type ChallengeWithAttempts = ChallengeMethod &
  Partial<{ attempt_limit: number | null; remaining_attempts: number | null }>

export function useLoginForm() {
  const { t } = useTranslation(["auth"])
  const navigate = useNavigate()
  const location = useLocation()
  const { login, pendingMfa, loginWithPasskey } = useAuth()

  const state = location.state as { from?: { pathname: string } } | null
  const redirectPath = state?.from?.pathname || "/dashboard"

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

      navigate(redirectPath, { replace: true })
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
      navigate(redirectPath, { replace: true })
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

export function useMfaFlow() {
  const { t } = useTranslation(["auth"])
  const navigate = useNavigate()
  const location = useLocation()
  const { pendingMfa, submitMfaChallenge } = useAuth()

  const state = location.state as { from?: { pathname: string } } | null
  const redirectPath = state?.from?.pathname || "/dashboard"

  const [mfaBusy, setMfaBusy] = useState(false)
  const [mfaError, setMfaError] = useState<string | null>(null)
  const [mfaErrorSource, setMfaErrorSource] = useState<"totp" | "general" | null>(null)

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
    [loginChallenge, otpChallenge, navigate, submitMfaChallenge, t]
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
    },
    [loginChallenge, webauthnChallenge, navigate, submitMfaChallenge, t]
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
  } as const
}
