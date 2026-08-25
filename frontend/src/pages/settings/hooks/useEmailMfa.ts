import { useCallback, useState } from "react"
import { useQueryClient } from "@tanstack/react-query"
import { useTranslation } from "react-i18next"

import {
  disableEmailMfa,
  resendEmailMfaChallenge,
  startEmailMfaEnablement,
  startEmailVerification,
  verifyMfaChallenge,
} from "@/api/mfa"
import { useAuth } from "@/contexts/AuthContext"
import { currentUserQueryKey, fetchCurrentUser } from "@/hooks/auth/useProfileSync"
import type { MfaMethodChallenge } from "@/types/Mfa"
import type { User } from "@/types/User"
import { extractApiError } from "@/utils/error"
import type { SetSnackbar } from "@/pages/settings/types"

interface UseEmailMfaOptions {
  setSnackbar: SetSnackbar
  openStepUpFor: (action: () => Promise<void>) => void
}

type EmailMfaMode = "verification" | "enablement"

export function useEmailMfa({ setSnackbar, openStepUpFor }: UseEmailMfaOptions) {
  const { t } = useTranslation(["settings", "common"])
  const { user, setUser } = useAuth()
  const queryClient = useQueryClient()
  const [emailChallenge, setEmailChallenge] = useState<MfaMethodChallenge | null>(null)
  const [emailMode, setEmailMode] = useState<EmailMfaMode | null>(null)
  const [emailMfaBusy, setEmailMfaBusy] = useState(false)
  const [emailMfaError, setEmailMfaError] = useState<string | null>(null)

  const refreshUser = useCallback(async () => {
    const fresh = await queryClient.fetchQuery<User>({
      queryKey: currentUserQueryKey,
      queryFn: fetchCurrentUser,
      staleTime: 0,
    })
    setUser(fresh)
    return fresh
  }, [queryClient, setUser])

  const resolveMessage = useCallback(
    (error: unknown, fallbackKey: string) => {
      const apiError = extractApiError(error)
      return apiError.status ? apiError.message : t(fallbackKey)
    },
    [t]
  )

  const handleStartEmailMfa = useCallback(
    async (options?: { skipStepUp?: boolean }) => {
      if (emailMfaBusy) return
      setEmailMfaBusy(true)
      setEmailMfaError(null)
      try {
        const mode: EmailMfaMode = user?.email_verified_at ? "enablement" : "verification"
        const challenge =
          mode === "enablement" ? await startEmailMfaEnablement() : await startEmailVerification()
        setEmailMode(mode)
        setEmailChallenge(challenge)
      } catch (error) {
        const apiError = extractApiError(error)
        if (!options?.skipStepUp && apiError.status === 428) {
          openStepUpFor(() => handleStartEmailMfa({ skipStepUp: true }))
          return
        }
        const message = resolveMessage(error, "settings:security.snackbar.emailMfaStartFailed")
        setEmailMfaError(message)
        setSnackbar({ text: message, severity: "error" })
      } finally {
        setEmailMfaBusy(false)
      }
    },
    [emailMfaBusy, openStepUpFor, resolveMessage, setSnackbar, user?.email_verified_at]
  )

  const handleConfirmEmailMfa = useCallback(
    async (code: string) => {
      if (!emailChallenge || emailMfaBusy) return
      setEmailMfaBusy(true)
      setEmailMfaError(null)
      try {
        await verifyMfaChallenge({
          method: "email_otp",
          code,
          challenge_token: emailChallenge.challenge_token,
        })
        await refreshUser()
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
        setEmailMfaError(resolveMessage(error, "settings:security.snackbar.emailMfaConfirmFailed"))
      } finally {
        setEmailMfaBusy(false)
      }
    },
    [emailChallenge, emailMfaBusy, emailMode, refreshUser, resolveMessage, setSnackbar, t]
  )

  const handleResendEmailMfa = useCallback(async () => {
    if (!emailChallenge || emailMfaBusy) return
    setEmailMfaBusy(true)
    setEmailMfaError(null)
    try {
      const rotated = await resendEmailMfaChallenge(emailChallenge.challenge_token)
      setEmailChallenge(rotated)
      setSnackbar({ text: t("settings:security.snackbar.emailMfaResent"), severity: "success" })
    } catch (error) {
      const message = resolveMessage(error, "settings:security.snackbar.emailMfaResendFailed")
      setEmailMfaError(message)
      setSnackbar({ text: message, severity: "error" })
    } finally {
      setEmailMfaBusy(false)
    }
  }, [emailChallenge, emailMfaBusy, resolveMessage, setSnackbar, t])

  const handleCancelEmailMfa = useCallback(() => {
    setEmailChallenge(null)
    setEmailMode(null)
    setEmailMfaError(null)
  }, [])

  const handleDisableEmailMfa = useCallback(() => {
    openStepUpFor(async () => {
      try {
        await disableEmailMfa()
        await refreshUser()
        setSnackbar({
          text: t("settings:security.snackbar.emailMfaDisabled"),
          severity: "success",
        })
      } catch (error) {
        setSnackbar({
          text: resolveMessage(error, "settings:security.snackbar.emailMfaDisableFailed"),
          severity: "error",
        })
      }
    })
  }, [openStepUpFor, refreshUser, resolveMessage, setSnackbar, t])

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
