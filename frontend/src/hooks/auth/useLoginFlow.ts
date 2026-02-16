import { useCallback, useEffect, useMemo, useRef, useState, useActionState } from "react"
import { useNavigate, useLocation } from "react-router-dom"
import { useTranslation } from "react-i18next"
import { isAxiosError } from "axios"

import { ChallengeLockedError, useAuth } from "@/contexts/AuthContext"
import type { PendingMfaState } from "@/types/Auth"
import { startAuthentication, browserSupportsWebAuthn } from "@simplewebauthn/browser"
import { useLocalStorage } from "@/hooks/useLocalStorage"
import { suggestEmailDomain } from "@/utils/authUtils"

type ChallengeMethod = PendingMfaState["methods"][number]
export type ChallengeWithAttempts = ChallengeMethod &
  Partial<{ attempt_limit: number | null; remaining_attempts: number | null }>

const emailRe = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

export function useLoginForm() {
  const { t } = useTranslation(["auth"])
  const navigate = useNavigate()
  const location = useLocation()
  const { login, pendingMfa, loginWithPasskey } = useAuth()

  const state = location.state as { from?: { pathname: string } } | null
  const redirectPath = state?.from?.pathname || "/dashboard"

  const [savedEmail, setSavedEmail] = useLocalStorage<string>("auth:lastEmail", "")
  const savedEmailRef = useRef(savedEmail)
  useEffect(() => {
    savedEmailRef.current = savedEmail
  }, [savedEmail])

  const [trustDeviceStored, setTrustDeviceStored] = useLocalStorage<string>("auth:trustDevice", "0")
  const [trustDevice, setTrustDevice] = useState<boolean>(trustDeviceStored === "1")
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
  const [submitting, setSubmitting] = useState(false)
  const [passkeyError, setPasskeyError] = useState<string | null>(null)

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

  const activeEmail = pendingEmail || currentEmail || savedEmail || ""
  const webauthnSupported = useMemo(() => browserSupportsWebAuthn(), [])

  return {
    // Refs
    emailRef,
    passwordRef,
    // State
    savedEmail,
    trustDevice,
    setTrustDevice,
    caps,
    setCaps,
    showPassword,
    setShowPassword,
    emailSuggestion,
    emailMirror,
    setEmailMirror,
    emailValid,
    activeEmail,
    submitting,
    isPending,
    submitError,
    passkeyError,
    webauthnSupported,
    // Auth context
    pendingMfa,
    // Handlers
    submitAction,
    handleEmailBlur,
    applySuggestion,
    handlePasskeyLogin,
  } as const
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
