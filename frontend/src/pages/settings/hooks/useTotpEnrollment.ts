import { useState, useCallback, useEffect, useMemo } from "react"
import { useQueryClient } from "@tanstack/react-query"
import { useTranslation } from "react-i18next"
import { extractApiError } from "@/utils/error"
import { formatDate } from "@/utils/date"

import { useAuth } from "@/contexts/AuthContext"
import { currentUserQueryKey, fetchCurrentUser } from "@/hooks/auth/useProfileSync"
import {
  startTotpEnrollment,
  confirmTotpEnrollment,
  deleteTotpEnrollment,
  deletePendingTotpEnrollment,
} from "@/api/mfa"
import type {
  MfaTotpEnrollment,
  TotpEnrollmentStart,
  TotpEnrollmentStartPayload,
} from "@/types/Mfa"
import type { User } from "@/types/User"
import type { SetSnackbar } from "@/pages/settings/types"

export interface UseTotpEnrollmentOptions {
  setSnackbar: SetSnackbar
  openStepUpFor: (action: () => Promise<void>) => void
}

export interface UseTotpEnrollmentReturn {
  // State
  totpDraft: TotpEnrollmentStart | null
  totpBusy: boolean
  totpError: string | null
  // Computed
  activeTotp: MfaTotpEnrollment[]
  pendingTotpEnrollment: MfaTotpEnrollment | null
  hasInteractiveMfa: boolean
  totpLimitReached: boolean
  mfaDisabledMessage: string | null
  defaultMethodText: string
  lastVerifiedText: string
  // Handlers
  handleStartTotp: (options?: {
    skipStepUp?: boolean
    payload?: TotpEnrollmentStartPayload
  }) => Promise<void>
  handleConfirmTotp: (code: string) => Promise<void>
  handleCancelTotp: () => Promise<void>
  handleDisableTotp: (enrollmentId: string) => void
  formatDateTime: (value: string | null) => string | null
}

const isStepUpError = (error: unknown): boolean => {
  const apiError = extractApiError(error)
  return apiError.status === 428
}

export function useTotpEnrollment({
  setSnackbar,
  openStepUpFor,
}: UseTotpEnrollmentOptions): UseTotpEnrollmentReturn {
  const { t } = useTranslation(["settings", "common"])
  const { user, setUser } = useAuth()
  const queryClient = useQueryClient()

  const [totpDraft, setTotpDraft] = useState<TotpEnrollmentStart | null>(null)
  const [totpBusy, setTotpBusy] = useState(false)
  const [totpError, setTotpError] = useState<string | null>(null)

  const resolveDetailMessage = useCallback((error: unknown, fallback: string) => {
    const apiError = extractApiError(error)
    if (apiError.status) {
      return apiError.message
    }
    return fallback
  }, [])

  const formatDateTime = useCallback((value: string | null) => {
    if (!value) return null
    return formatDate(value, {
      day: "2-digit",
      month: "short",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    })
  }, [])

  const refreshUser = useCallback(async () => {
    const fresh = await queryClient.fetchQuery<User>({
      queryKey: currentUserQueryKey,
      queryFn: fetchCurrentUser,
      staleTime: 0,
    })
    setUser(fresh)
    return fresh
  }, [queryClient, setUser])

  // Computed values
  const activeTotp = useMemo(
    () =>
      (user?.totp_enrollments ?? []).filter(
        (entry) => Boolean(entry.confirmed_at) && !entry.revoked_at
      ),
    [user?.totp_enrollments]
  )

  const pendingTotpEnrollment = useMemo(
    () =>
      (user?.totp_enrollments ?? []).find((entry) => !entry.confirmed_at && !entry.revoked_at) ??
      null,
    [user?.totp_enrollments]
  )

  const pendingTotpId = pendingTotpEnrollment?.id ?? null
  const hasInteractiveMfa = activeTotp.length > 0
  const totpLimitReached = hasInteractiveMfa

  const mfaDisabledMessage = useMemo(() => {
    if (hasInteractiveMfa) return null
    if (user?.mfa_required) {
      return t("settings:security.status.mfaDisabledWasRequired")
    }
    return t("settings:security.status.mfaDisabled")
  }, [hasInteractiveMfa, t, user?.mfa_required])

  const defaultMethodText = useMemo(() => {
    if (!user?.mfa_default_method) {
      return t("settings:security.status.noDefault")
    }
    return t("settings:security.status.defaultTotp")
  }, [t, user?.mfa_default_method])

  const lastVerifiedText = useMemo(() => {
    if (!user?.mfa_last_verified_at) {
      return t("settings:security.status.notVerified")
    }
    const formatted = formatDateTime(user.mfa_last_verified_at)
    return formatted
      ? t("settings:security.status.lastVerified", { value: formatted })
      : t("settings:security.status.notVerified")
  }, [formatDateTime, t, user?.mfa_last_verified_at])

  // Handlers
  const handleStartTotp = useCallback(
    async (options?: { skipStepUp?: boolean; payload?: TotpEnrollmentStartPayload }) => {
      if (totpBusy || totpLimitReached) return
      setTotpBusy(true)
      setTotpError(null)
      try {
        const data = await startTotpEnrollment(options?.payload)
        setTotpDraft(data)
      } catch (error) {
        if (!options?.skipStepUp && isStepUpError(error)) {
          openStepUpFor(async () => {
            await handleStartTotp({ skipStepUp: true, payload: options?.payload })
          })
          return
        }
        const message = resolveDetailMessage(error, t("settings:security.snackbar.totpStartFailed"))
        setTotpError(message)
        setSnackbar({ text: message, severity: "error" })
      } finally {
        setTotpBusy(false)
      }
    },
    [openStepUpFor, resolveDetailMessage, setSnackbar, t, totpBusy, totpLimitReached]
  )

  // Auto-resume pending enrollment
  useEffect(() => {
    if (!pendingTotpEnrollment || totpDraft) return
    void handleStartTotp({ payload: { reuse_existing: true } })
  }, [handleStartTotp, pendingTotpEnrollment, totpDraft])

  const handleConfirmTotp = useCallback(
    async (code: string) => {
      const enrollmentId = totpDraft?.enrollment.id ?? pendingTotpId
      if (!enrollmentId) return
      setTotpBusy(true)
      setTotpError(null)
      try {
        await confirmTotpEnrollment({ enrollment_id: enrollmentId, code })
        setTotpDraft(null)
        await refreshUser()
        setSnackbar({ text: t("settings:security.snackbar.totpEnabled"), severity: "success" })
      } catch (error) {
        setTotpError(resolveDetailMessage(error, t("settings:security.snackbar.totpConfirmFailed")))
      } finally {
        setTotpBusy(false)
      }
    },
    [pendingTotpId, refreshUser, resolveDetailMessage, setSnackbar, t, totpDraft]
  )

  const handleCancelTotp = useCallback(async () => {
    const enrollmentId = totpDraft?.enrollment.id ?? pendingTotpId
    if (!enrollmentId || totpBusy) return
    setTotpBusy(true)
    setTotpError(null)
    try {
      await deletePendingTotpEnrollment(enrollmentId)
      setTotpDraft(null)
      await refreshUser()
    } catch (error) {
      const message = resolveDetailMessage(error, t("settings:security.snackbar.totpCancelFailed"))
      setTotpError(message)
      setSnackbar({ text: message, severity: "error" })
    } finally {
      setTotpBusy(false)
    }
  }, [pendingTotpId, refreshUser, resolveDetailMessage, setSnackbar, t, totpBusy, totpDraft])

  const handleDisableTotp = useCallback(
    (enrollmentId: string) => {
      const action = async () => {
        try {
          const data = await deleteTotpEnrollment(enrollmentId)
          if (data) {
            setUser((previous) =>
              previous
                ? {
                    ...previous,
                    mfa_default_method: data.mfa_default_method,
                    mfa_required: data.mfa_required,
                  }
                : previous
            )
          }
          await refreshUser()
          setSnackbar({ text: t("settings:security.snackbar.totpDisabled"), severity: "success" })
        } catch (error) {
          setSnackbar({
            text: resolveDetailMessage(error, t("settings:security.snackbar.totpDisableFailed")),
            severity: "error",
          })
        }
      }
      openStepUpFor(action)
    },
    [openStepUpFor, refreshUser, resolveDetailMessage, setSnackbar, setUser, t]
  )

  return {
    totpDraft,
    totpBusy,
    totpError,
    activeTotp,
    pendingTotpEnrollment,
    hasInteractiveMfa,
    totpLimitReached,
    mfaDisabledMessage,
    defaultMethodText,
    lastVerifiedText,
    handleStartTotp,
    handleConfirmTotp,
    handleCancelTotp,
    handleDisableTotp,
    formatDateTime,
  }
}
