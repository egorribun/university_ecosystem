import { useState, useCallback, useMemo } from "react"
import { useQueryClient } from "@tanstack/react-query"
import { useTranslation } from "react-i18next"
import { isAxiosError } from "axios"

import api from "@/api/client"
import type { SetSnackbar } from "@/pages/settings/types"

export interface UsePasswordChangeOptions {
  setSnackbar: SetSnackbar
  sessionsQueryKey: readonly unknown[]
  openStepUpFor?: (action: () => Promise<void>) => void
}

export interface UsePasswordChangeReturn {
  currentPasswordValue: string
  newPasswordValue: string
  confirmPasswordValue: string
  passwordBusy: boolean
  passwordError: string | null
  currentPasswordError: string | null
  isNewPasswordError: boolean
  confirmPasswordMessage: string | null
  setCurrentPasswordValue: (value: string) => void
  setNewPasswordValue: (value: string) => void
  setConfirmPasswordValue: (value: string) => void
  handlePasswordSubmit: (options?: { skipStepUp?: boolean }) => Promise<void>
}

const isStepUpError = (error: unknown): boolean =>
  isAxiosError(error) && error.response?.status === 428

export function usePasswordChange({
  setSnackbar,
  sessionsQueryKey,
  openStepUpFor,
}: UsePasswordChangeOptions): UsePasswordChangeReturn {
  const { t } = useTranslation(["settings"])
  const queryClient = useQueryClient()

  const [currentPasswordValue, setCurrentPasswordValue] = useState("")
  const [newPasswordValue, setNewPasswordValue] = useState("")
  const [confirmPasswordValue, setConfirmPasswordValue] = useState("")
  const [passwordBusy, setPasswordBusy] = useState(false)
  const [passwordError, setPasswordError] = useState<string | null>(null)
  const [currentPasswordError, setCurrentPasswordError] = useState<string | null>(null)

  const resolveDetailMessage = useCallback((error: unknown, fallback: string) => {
    if (isAxiosError(error)) {
      const detail = (error.response?.data as { detail?: unknown } | undefined)?.detail
      if (typeof detail === "string") return detail
      if (Array.isArray(detail)) {
        const combined = detail
          .map((item) =>
            item && typeof item === "object" && "msg" in item
              ? String((item as { msg?: unknown }).msg)
              : ""
          )
          .filter(Boolean)
          .join("; ")
        return combined || fallback
      }
    }
    return fallback
  }, [])

  const isNewPasswordError = useMemo(() => {
    if (!passwordError) return false
    return [
      t("settings:security.password.errors.newRequired"),
      t("settings:security.password.errors.same"),
    ].includes(passwordError)
  }, [passwordError, t])

  const confirmPasswordMessage = useMemo(() => {
    if (!passwordError) return null
    if (
      [
        t("settings:security.password.errors.newRequired"),
        t("settings:security.password.errors.same"),
      ].includes(passwordError)
    ) {
      return null
    }
    return passwordError
  }, [passwordError, t])

  const handlePasswordSubmit = useCallback(
    async (options?: { skipStepUp?: boolean }) => {
      if (passwordBusy) return

      setCurrentPasswordError(null)
      setPasswordError(null)
      let hasError = false

      // Validate current password
      if (!currentPasswordValue) {
        setCurrentPasswordError(t("settings:security.password.errors.currentRequired"))
        hasError = true
      }

      // Validate new password
      let derivedError: string | null = null
      if (!newPasswordValue) {
        derivedError = t("settings:security.password.errors.newRequired")
      } else if (!confirmPasswordValue) {
        derivedError = t("settings:security.password.errors.confirmRequired")
      } else if (newPasswordValue !== confirmPasswordValue) {
        derivedError = t("settings:security.password.errors.mismatch")
      }

      if (derivedError) {
        setPasswordError(derivedError)
        hasError = true
      }

      if (hasError) return

      setPasswordBusy(true)
      try {
        const { data } = await api.post<{
          ok: boolean
          revoked_sessions: number
        }>("/users/me/password", {
          current_password: currentPasswordValue,
          new_password: newPasswordValue,
        })

        if (data?.ok) {
          setSnackbar({
            text: t("settings:security.password.updated", {
              count: data.revoked_sessions ?? 0,
            }),
            severity: "success",
          })
        }

        // Clear form
        setCurrentPasswordValue("")
        setNewPasswordValue("")
        setConfirmPasswordValue("")

        // Refresh sessions since some may have been revoked
        await queryClient.invalidateQueries({ queryKey: sessionsQueryKey })
      } catch (error) {
        if (!options?.skipStepUp && isStepUpError(error) && openStepUpFor) {
          openStepUpFor(async () => {
            await handlePasswordSubmit({ skipStepUp: true })
          })
          return
        }

        const message = resolveDetailMessage(error, t("settings:security.password.failed"))
        let handled = false

        if (isAxiosError(error)) {
          const detail = (error.response?.data as { detail?: unknown } | undefined)?.detail
          if (typeof detail === "string") {
            if (detail === t("settings:security.password.errors.currentInvalid")) {
              setCurrentPasswordError(detail)
              handled = true
            } else if (detail === t("settings:security.password.errors.same")) {
              setPasswordError(detail)
              handled = true
            } else {
              setPasswordError(detail)
              handled = true
            }
          }
        }

        if (!handled) {
          setPasswordError(message)
          setSnackbar({ text: message, severity: "error" })
        }
      } finally {
        setPasswordBusy(false)
      }
    },
    [
      confirmPasswordValue,
      currentPasswordValue,
      newPasswordValue,
      openStepUpFor,
      passwordBusy,
      queryClient,
      resolveDetailMessage,
      sessionsQueryKey,
      setSnackbar,
      t,
    ]
  )

  return {
    currentPasswordValue,
    newPasswordValue,
    confirmPasswordValue,
    passwordBusy,
    passwordError,
    currentPasswordError,
    isNewPasswordError,
    confirmPasswordMessage,
    setCurrentPasswordValue,
    setNewPasswordValue,
    setConfirmPasswordValue,
    handlePasswordSubmit,
  }
}
