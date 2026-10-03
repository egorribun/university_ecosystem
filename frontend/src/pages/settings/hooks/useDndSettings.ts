import { useEffect, useState, type ChangeEvent, type FocusEvent } from "react"
import { useTranslation } from "react-i18next"
import { isAxiosError } from "axios"

import { useProfileSessionGuard } from "@/hooks/useProfileSessionGuard"
import api from "@/api/client"
import { useAuth } from "@/contexts/AuthContext"
import type { User } from "@/types/User"
import type { SetSnackbar } from "@/pages/settings/types"

const DEFAULT_DND_START = "22:00"
const DEFAULT_DND_END = "07:00"

/**
 * Converts a stored time value to the HH:MM format of input elements
 */
const toInputTime = (value: unknown): string => String(value).match(/^(\d{2}:\d{2})/)?.[1] ?? ""

/**
 * Converts HH:MM to the server format with seconds; other values are sent as-is
 */
const toServerTime = (value: string): string =>
  /^\d{2}:\d{2}$/.test(value) ? `${value}:00` : value

interface DndDraft {
  enabled: boolean
  start: string
  end: string
}

/**
 * The locally edited copy of the account's DND range. An enabled range that
 * the server stores without times is shown with the default times.
 */
const draftFromUser = (value: User | null): DndDraft => {
  const preferences = value?.preferences
  const enabled = Boolean(preferences?.dnd_enabled)
  return {
    enabled,
    start: toInputTime(preferences?.dnd_start) || (enabled ? DEFAULT_DND_START : ""),
    end: toInputTime(preferences?.dnd_end) || (enabled ? DEFAULT_DND_END : ""),
  }
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

// The handlers are plain functions: React Compiler memoizes this hook, and
// none of them is an effect dependency.
export function useDndSettings(setSnackbar: SetSnackbar): UseDndSettingsReturn {
  const { t } = useTranslation(["settings"])
  const { user, setUser } = useAuth()
  const captureOperation = useProfileSessionGuard()

  const [draft, setDraft] = useState(() => draftFromUser(null))
  const [dndSaving, setDndSaving] = useState(false)

  const persistDnd = async (nextEnabled: boolean, nextStart: string, nextEnd: string) => {
    const isCurrent = captureOperation()
    if (!isCurrent()) return
    const normalizedStart = nextStart.trim()
    const normalizedEnd = nextEnd.trim()
    const previous = user?.preferences
    const previousEnabled = Boolean(previous?.dnd_enabled)
    const previousStart = toInputTime(previous?.dnd_start)
    const previousEnd = toInputTime(previous?.dnd_end)

    // Validate range when enabling
    if (nextEnabled && (!normalizedStart || !normalizedEnd)) {
      setSnackbar({ text: t("settings:dnd.validation.missingRange"), severity: "warning" })
      setDraft(draftFromUser(user))
      return
    }

    // Skip if no changes
    if (
      nextEnabled === previousEnabled &&
      (!nextEnabled || (normalizedStart === previousStart && normalizedEnd === previousEnd))
    ) {
      return
    }

    setDndSaving(true)
    try {
      const response = await api.put<User>("/users/me", {
        preferences: nextEnabled
          ? {
              dnd_enabled: true,
              dnd_start: toServerTime(normalizedStart),
              dnd_end: toServerTime(normalizedEnd),
            }
          : { dnd_enabled: false, dnd_start: null, dnd_end: null },
      })
      if (!isCurrent() || response.data.id !== user?.id) return
      setUser(response.data)
      setDraft(draftFromUser(response.data))

      let message: string
      if (nextEnabled === previousEnabled) message = t("settings:dnd.snackbar.updated")
      else if (nextEnabled) message = t("settings:dnd.snackbar.enabled")
      else message = t("settings:dnd.snackbar.disabled")

      setSnackbar({ text: message, severity: "success" })
    } catch (error: unknown) {
      if (!isCurrent()) return
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
          message = collected || message
        }
      }

      setSnackbar({ text: message, severity: "error" })
      setDraft(draftFromUser(user))
    } finally {
      if (isCurrent()) setDndSaving(false)
    }
  }

  const handleDndToggle = (_: ChangeEvent<HTMLInputElement>, checked: boolean) => {
    if (dndSaving || !captureOperation()()) return

    if (checked) {
      const start = draft.start || DEFAULT_DND_START
      const end = draft.end || DEFAULT_DND_END
      setDraft({ enabled: true, start, end })
      void persistDnd(true, start, end)
    } else {
      setDraft((current) => ({ ...current, enabled: false }))
      void persistDnd(false, draft.start, draft.end)
    }
  }

  const handleDndStartChange = (event: ChangeEvent<HTMLInputElement>) => {
    setDraft((current) => ({ ...current, start: event.target.value }))
  }

  const handleDndStartBlur = (event: FocusEvent<HTMLInputElement>) => {
    if (!draft.enabled || dndSaving || !captureOperation()()) return
    const value = event.currentTarget.value.trim()
    setDraft((current) => ({ ...current, start: value }))
    void persistDnd(true, value, draft.end)
  }

  const handleDndEndChange = (event: ChangeEvent<HTMLInputElement>) => {
    setDraft((current) => ({ ...current, end: event.target.value }))
  }

  const handleDndEndBlur = (event: FocusEvent<HTMLInputElement>) => {
    if (!draft.enabled || dndSaving || !captureOperation()()) return
    const value = event.currentTarget.value.trim()
    setDraft((current) => ({ ...current, end: value }))
    void persistDnd(true, draft.start, value)
  }

  useEffect(() => {
    setDndSaving(false)
  }, [captureOperation])

  // Sync local state with user on mount and when user changes
  useEffect(() => {
    setDraft(draftFromUser(user))
  }, [user])

  return {
    dndEnabled: draft.enabled,
    dndStart: draft.start,
    dndEnd: draft.end,
    dndSaving,
    handleDndToggle,
    handleDndStartChange,
    handleDndStartBlur,
    handleDndEndChange,
    handleDndEndBlur,
  }
}
