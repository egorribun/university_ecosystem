import { useState, useCallback, useEffect } from "react"
import { useQueryClient } from "@tanstack/react-query"
import { useTranslation } from "react-i18next"
import { isAxiosError } from "axios"

import api from "@/api/client"
import { useAuth } from "@/contexts/AuthContext"
import { currentUserQueryKey, fetchCurrentUser } from "@/hooks/auth/useProfileSync"
import type { User } from "@/types/User"
import type { SetSnackbar } from "@/pages/settings/types"

export interface UseEmailChangeOptions {
  setSnackbar: SetSnackbar
  openStepUpFor?: (action: () => Promise<void>) => void
}

export interface UseEmailChangeReturn {
  emailValue: string
  emailPassword: string
  emailBusy: boolean
  emailError: string | null
  emailPasswordError: string | null
  pendingEmail: string | null
  setEmailValue: (value: string) => void
  setEmailPassword: (value: string) => void
  handleEmailSubmit: (options?: { skipStepUp?: boolean }) => Promise<void>
}

const isStepUpError = (error: unknown): boolean =>
  isAxiosError(error) && error.response?.status === 428

export function useEmailChange({
  setSnackbar,
  openStepUpFor,
}: UseEmailChangeOptions): UseEmailChangeReturn {
  const { t } = useTranslation(["settings"])
  const { user, setUser } = useAuth()
  const queryClient = useQueryClient()

  const [emailValue, setEmailValue] = useState(user?.email ?? "")
  const [emailPassword, setEmailPassword] = useState("")
  const [emailBusy, setEmailBusy] = useState(false)
  const [emailError, setEmailError] = useState<string | null>(null)
  const [emailPasswordError, setEmailPasswordError] = useState<string | null>(null)
  const [pendingEmail, setPendingEmail] = useState<string | null>(user?.pending_email ?? null)

  // Sync email from user context
  useEffect(() => {
    setEmailValue(user?.email ?? "")
  }, [user?.email])

  useEffect(() => {
    setPendingEmail(user?.pending_email ?? null)
  }, [user?.pending_email])

  const refreshUser = useCallback(async () => {
    const fresh = await queryClient.fetchQuery<User>({
      queryKey: currentUserQueryKey,
      queryFn: fetchCurrentUser,
      staleTime: 0,
    })
    setUser(fresh)
    return fresh
  }, [queryClient, setUser])

  const resolveDetailMessage = useCallback((error: unknown, fallback: string) => {
    if (isAxiosError(error)) {
      const detail = (error.response?.data as { detail?: unknown } | undefined)?.detail
      if (Array.isArray(detail)) {
        const combined = detail
          .map((item) =>
            item && typeof item === "object" && "msg" in item
              ? String((item as { msg?: unknown }).msg)
              : ""
          )
          .filter(Boolean)
          .join("; ")
        if (combined) return combined
      }
    }
    return fallback
  }, [])

  const handleEmailSubmit = useCallback(
    async (options?: { skipStepUp?: boolean }) => {
      if (emailBusy) return

      let hasError = false
      const trimmedEmail = emailValue.trim()
      setEmailError(null)
      setEmailPasswordError(null)

      // Validation
      if (!trimmedEmail) {
        setEmailError(t("settings:security.email.errors.required"))
        hasError = true
      } else if (user?.email && trimmedEmail.toLowerCase() === user.email.toLowerCase()) {
        setEmailError(t("settings:security.email.noChange"))
        hasError = true
      } else if (pendingEmail && trimmedEmail.toLowerCase() === pendingEmail.toLowerCase()) {
        setEmailError(t("settings:security.email.pendingSame", { email: pendingEmail }))
        hasError = true
      }

      if (!emailPassword) {
        setEmailPasswordError(t("settings:security.email.errors.passwordRequired"))
        hasError = true
      }

      if (hasError) return

      setEmailBusy(true)
      try {
        await api.post<User>("/users/me/email", {
          email: trimmedEmail,
          password: emailPassword,
        })
        setPendingEmail(trimmedEmail.toLowerCase())
        await refreshUser()
        setEmailPassword("")
        setSnackbar({
          text: t("settings:security.email.confirmationSent", { email: trimmedEmail }),
          severity: "success",
        })
      } catch (error) {
        if (!options?.skipStepUp && isStepUpError(error) && openStepUpFor) {
          openStepUpFor(async () => {
            await handleEmailSubmit({ skipStepUp: true })
          })
          return
        }

        let handled = false
        if (isAxiosError(error)) {
          const detail = (error.response?.data as { detail?: unknown } | undefined)?.detail
          if (typeof detail === "string") {
            if (detail === t("settings:security.email.errors.invalidPassword")) {
              setEmailPasswordError(detail)
              handled = true
            } else {
              setEmailError(detail)
              handled = true
            }
          }
        }

        if (!handled) {
          const message = resolveDetailMessage(error, t("settings:security.email.failed"))
          setEmailError(message)
          setSnackbar({ text: message, severity: "error" })
        }
      } finally {
        setEmailBusy(false)
      }
    },
    [
      emailBusy,
      emailPassword,
      emailValue,
      openStepUpFor,
      refreshUser,
      resolveDetailMessage,
      pendingEmail,
      setSnackbar,
      t,
      user?.email,
    ]
  )

  return {
    emailValue,
    emailPassword,
    emailBusy,
    emailError,
    emailPasswordError,
    pendingEmail,
    setEmailValue,
    setEmailPassword,
    handleEmailSubmit,
  }
}
