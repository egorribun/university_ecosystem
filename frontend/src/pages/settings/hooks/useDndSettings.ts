import { useState, useCallback, useEffect, type ChangeEvent, type FocusEvent } from "react"
import { useTranslation } from "react-i18next"
import { isAxiosError } from "axios"

import api from "@/api/client"
import { useAuth } from "@/contexts/AuthContext"
import type { User } from "@/types/User"
import type { SetSnackbar } from "@/pages/settings/types"

const DEFAULT_DND_START = "22:00"
const DEFAULT_DND_END = "07:00"

/**
 * Converts time value to HH:MM format for input elements
 */
const toInputTime = (value: unknown): string => {
  if (!value) return ""
  const str = String(value)
  const match = str.match(/^(\d{2}:\d{2})/)
  return match?.[1] ?? ""
}

/**
 * Converts HH:MM to server format with seconds
 */
const toServerTime = (value: string): string => {
  const trimmed = value.trim()
  if (/^\d{2}:\d{2}$/.test(trimmed)) return `${trimmed}:00`
  if (/^\d{2}:\d{2}:\d{2}$/.test(trimmed)) return trimmed
  return trimmed
}

export interface UseDndSettingsReturn {
  dndEnabled: boolean
  dndStart: string
  dndEnd: string
  dndSaving: boolean
  handleDndToggle: (event: ChangeEvent<HTMLInputElement>, checked: boolean) => void
  handleDndStartChange: (event: ChangeEvent<HTMLInputElement>) => void
  handleDndStartBlur: (event: FocusEvent<HTMLInputElement>) => void
  handleDndEndChange: (event: ChangeEvent<HTMLInputElement>) => void
  handleDndEndBlur: (event: FocusEvent<HTMLInputElement>) => void
}

export function useDndSettings(setSnackbar: SetSnackbar): UseDndSettingsReturn {
  const { t } = useTranslation(["settings"])
  const { user, setUser } = useAuth()

  const [dndEnabled, setDndEnabled] = useState(false)
  const [dndStart, setDndStart] = useState("")
  const [dndEnd, setDndEnd] = useState("")
  const [dndSaving, setDndSaving] = useState(false)

  const syncDndFromUser = useCallback((value: User | null) => {
    const enabled = Boolean(value?.preferences?.dnd_enabled)
    const start = toInputTime(value?.preferences?.dnd_start)
    const end = toInputTime(value?.preferences?.dnd_end)

    setDndEnabled((previous) => (previous === enabled ? previous : enabled))
    setDndStart((previous) => {
      const next = start || (enabled ? DEFAULT_DND_START : "")
      return previous === next ? previous : next
    })
    setDndEnd((previous) => {
      const next = end || (enabled ? DEFAULT_DND_END : "")
      return previous === next ? previous : next
    })
  }, [])

  const persistDnd = useCallback(
    async (nextEnabled: boolean, nextStart: string | null, nextEnd: string | null) => {
      const normalizedStart = nextStart?.trim() ?? ""
      const normalizedEnd = nextEnd?.trim() ?? ""
      const previousEnabled = Boolean(user?.preferences?.dnd_enabled)
      const previousStart = toInputTime(user?.preferences?.dnd_start)
      const previousEnd = toInputTime(user?.preferences?.dnd_end)

      // Skip if no changes
      if (
        nextEnabled === previousEnabled &&
        (!nextEnabled ||
          (normalizedStart &&
            normalizedEnd &&
            normalizedStart === previousStart &&
            normalizedEnd === previousEnd))
      ) {
        return
      }

      // Validate range when enabling
      if (nextEnabled && (!normalizedStart || !normalizedEnd)) {
        setSnackbar({ text: t("settings:dnd.validation.missingRange"), severity: "warning" })
        syncDndFromUser(user)
        return
      }

      setDndSaving(true)
      try {
        const payload: Record<string, unknown> = {
          preferences: { dnd_enabled: nextEnabled } as Record<string, unknown>,
        }
        if (nextEnabled) {
          ;(payload.preferences as Record<string, unknown>).dnd_start =
            toServerTime(normalizedStart)
          ;(payload.preferences as Record<string, unknown>).dnd_end = toServerTime(normalizedEnd)
        } else {
          ;(payload.preferences as Record<string, unknown>).dnd_start = null
          ;(payload.preferences as Record<string, unknown>).dnd_end = null
        }

        const response = await api.put<User>("/users/me", payload)
        setUser(response.data)
        syncDndFromUser(response.data)

        const wasEnabled = previousEnabled
        let message: string
        if (nextEnabled && !wasEnabled) message = t("settings:dnd.snackbar.enabled")
        else if (!nextEnabled && wasEnabled) message = t("settings:dnd.snackbar.disabled")
        else message = t("settings:dnd.snackbar.updated")

        setSnackbar({ text: message, severity: "success" })
      } catch (error: unknown) {
        let message = t("settings:dnd.snackbar.updateFailed")

        if (isAxiosError(error)) {
          const detail = (error.response?.data as { detail?: unknown } | undefined)?.detail
          if (typeof detail === "string") {
            message = detail
          } else if (Array.isArray(detail)) {
            const collected = detail
              .map((item: unknown) =>
                item && typeof item === "object" && "msg" in item
                  ? String((item as { msg?: unknown }).msg)
                  : ""
              )
              .filter(Boolean)
              .join("; ")
            if (collected) message = collected
          }
        }

        setSnackbar({ text: message, severity: "error" })
        syncDndFromUser(user)
      } finally {
        setDndSaving(false)
      }
    },
    [setUser, setSnackbar, syncDndFromUser, t, user]
  )

  const handleDndToggle = useCallback(
    (_: ChangeEvent<HTMLInputElement>, checked: boolean) => {
      if (dndSaving) return

      const nextStart = checked ? dndStart || DEFAULT_DND_START : dndStart
      const nextEnd = checked ? dndEnd || DEFAULT_DND_END : dndEnd

      if (checked) {
        setDndStart(nextStart)
        setDndEnd(nextEnd)
      }

      setDndEnabled(checked)
      void persistDnd(checked, checked ? nextStart : null, checked ? nextEnd : null)
    },
    [dndSaving, dndEnd, dndStart, persistDnd]
  )

  const handleDndStartChange = useCallback((event: ChangeEvent<HTMLInputElement>) => {
    setDndStart(event.target.value)
  }, [])

  const handleDndStartBlur = useCallback(
    (event: FocusEvent<HTMLInputElement>) => {
      if (!dndEnabled || dndSaving) return
      const value = (event.currentTarget.value || "").trim()
      setDndStart(value)
      void persistDnd(true, value || null, dndEnd || null)
    },
    [dndEnabled, dndEnd, dndSaving, persistDnd]
  )

  const handleDndEndChange = useCallback((event: ChangeEvent<HTMLInputElement>) => {
    setDndEnd(event.target.value)
  }, [])

  const handleDndEndBlur = useCallback(
    (event: FocusEvent<HTMLInputElement>) => {
      if (!dndEnabled || dndSaving) return
      const value = (event.currentTarget.value || "").trim()
      setDndEnd(value)
      void persistDnd(true, dndStart || null, value || null)
    },
    [dndEnabled, dndSaving, dndStart, persistDnd]
  )

  // Sync local state with user on mount and when user changes
  useEffect(() => {
    syncDndFromUser(user)
  }, [syncDndFromUser, user])

  return {
    dndEnabled,
    dndStart,
    dndEnd,
    dndSaving,
    handleDndToggle,
    handleDndStartChange,
    handleDndStartBlur,
    handleDndEndChange,
    handleDndEndBlur,
  }
}
