import { useProfileSessionGuard } from "@/hooks/useProfileSessionGuard"
import { useSessionProfileRefresh } from "./useSessionProfileRefresh"
import { useCallback, useState, useEffect } from "react"
import { useTranslation } from "react-i18next"

import {
  disableEmailMfa,
  resendEmailMfaChallenge,
  startEmailMfaEnablement,
  startEmailVerification,
  verifyMfaChallenge,
} from "@/api/mfa"
import { useAuth } from "@/contexts/AuthContext"
import type { MfaMethodChallenge } from "@/types/Mfa"
import { extractApiError } from "@/utils/error"
import type { SetSnackbar } from "@/pages/settings/types"

interface UseEmailMfaOptions {
  setSnackbar: SetSnackbar
  openStepUpFor: (action: () => Promise<void>) => void
}

type EmailMfaMode = "verification" | "enablement"

export function useEmailMfa({ setSnackbar, openStepUpFor }: UseEmailMfaOptions) {
  const { t } = useTranslation(["settings", "common"])
  const { user } = useAuth()
  const captureOperation = useProfileSessionGuard()
  const refreshUser = useSessionProfileRefresh()
  const [emailChallenge, setEmailChallenge] = useState<MfaMethodChallenge | null>(null)
  const [emailMode, setEmailMode] = useState<EmailMfaMode | null>(null)
  const [emailMfaBusy, setEmailMfaBusy] = useState(false)
  const [emailMfaError, setEmailMfaError] = useState<string | null>(null)

  useEffect(() => {
    setEmailChallenge(null)
    setEmailMode(null)
    setEmailMfaBusy(false)
    setEmailMfaError(null)
  }, [captureOperation])

  const resolveMessage = useCallback(
    (error: unknown, fallbackKey: string) => {
      const apiError = extractApiError(error)
      return apiError.status ? apiError.message : t(fallbackKey)
    },
    [t]
  )

  const handleStartEmailMfa = useCallback(
    async (options?: { skipStepUp?: boolean }) => {
      const isCurrent = captureOperation()
      if (emailMfaBusy || !isCurrent()) return
      setEmailMfaBusy(true)
      setEmailMfaError(null)
      try {
        const mode: EmailMfaMode = user?.email_verified_at ? "enablement" : "verification"
        const challenge =
          mode === "enablement" ? await startEmailMfaEnablement() : await startEmailVerification()
        if (!isCurrent()) return
        setEmailMode(mode)
        setEmailChallenge(challenge)
      } catch (error) {
        if (!isCurrent()) return
        const apiError = extractApiError(error)
        if (!options?.skipStepUp && apiError.status === 428) {
          openStepUpFor(async () => {
            if (isCurrent()) await handleStartEmailMfa({ skipStepUp: true })
          })
          return
        }
        const message = resolveMessage(error, "settings:security.snackbar.emailMfaStartFailed")
        setEmailMfaError(message)
        setSnackbar({ text: message, severity: "error" })
      } finally {
        if (isCurrent()) setEmailMfaBusy(false)
      }
    },
    [
      captureOperation,
      emailMfaBusy,
      openStepUpFor,
      resolveMessage,
      setSnackbar,
      user?.email_verified_at,
    ]
  )

  const handleConfirmEmailMfa = useCallback(
    async (code: string) => {
      const isCurrent = captureOperation()
      if (!emailChallenge || emailMfaBusy || !isCurrent()) return
      setEmailMfaBusy(true)
      setEmailMfaError(null)
      try {
        await verifyMfaChallenge({
          method: "email_otp",
          code,
          challenge_token: emailChallenge.challenge_token,
        })
        if (!(await refreshUser(isCurrent)) || !isCurrent()) return
        setEmailChallenge(null)
        setSnackbar({
          text: t(
            emailMode === "verification"
              ? "settings:security.snackbar.emailVerified"
              : "settings:security.snackbar.emailMfaEnabled"
          ),
          severity: "success",
        })
      } catch (error) {
        if (!isCurrent()) return
        setEmailMfaError(resolveMessage(error, "settings:security.snackbar.emailMfaConfirmFailed"))
      } finally {
        if (isCurrent()) setEmailMfaBusy(false)
      }
    },
    [
      captureOperation,
      emailChallenge,
      emailMfaBusy,
      emailMode,
      refreshUser,
      resolveMessage,
      setSnackbar,
      t,
    ]
  )

  const handleResendEmailMfa = useCallback(async () => {
    const isCurrent = captureOperation()
    if (!emailChallenge || emailMfaBusy || !isCurrent()) return
    setEmailMfaBusy(true)
    setEmailMfaError(null)
    try {
      const rotated = await resendEmailMfaChallenge(emailChallenge.challenge_token)
      if (!isCurrent()) return
      setEmailChallenge(rotated)
      setSnackbar({ text: t("settings:security.snackbar.emailMfaResent"), severity: "success" })
    } catch (error) {
      if (!isCurrent()) return
      const message = resolveMessage(error, "settings:security.snackbar.emailMfaResendFailed")
      setEmailMfaError(message)
      setSnackbar({ text: message, severity: "error" })
    } finally {
      if (isCurrent()) setEmailMfaBusy(false)
    }
  }, [captureOperation, emailChallenge, emailMfaBusy, resolveMessage, setSnackbar, t])

  const handleCancelEmailMfa = useCallback(() => {
    setEmailChallenge(null)
    setEmailMode(null)
    setEmailMfaError(null)
  }, [])

  const handleDisableEmailMfa = useCallback(() => {
    const isCurrent = captureOperation()
    if (!isCurrent()) return
    openStepUpFor(async () => {
      if (!isCurrent()) return
      try {
        await disableEmailMfa()
        if (!(await refreshUser(isCurrent)) || !isCurrent()) return
        setSnackbar({
          text: t("settings:security.snackbar.emailMfaDisabled"),
          severity: "success",
        })
      } catch (error) {
        if (!isCurrent()) return
        setSnackbar({
          text: resolveMessage(error, "settings:security.snackbar.emailMfaDisableFailed"),
          severity: "error",
        })
      }
    })
  }, [captureOperation, openStepUpFor, refreshUser, resolveMessage, setSnackbar, t])

  return {
    emailChallenge,
    emailMfaBusy,
    emailMfaError,
    emailMfaEnabled: Boolean(user?.email_mfa_enabled_at),
    emailVerified: Boolean(user?.email_verified_at),
    handleStartEmailMfa,
    handleConfirmEmailMfa,
    handleResendEmailMfa,
    handleCancelEmailMfa,
    handleDisableEmailMfa,
  } as const
}
