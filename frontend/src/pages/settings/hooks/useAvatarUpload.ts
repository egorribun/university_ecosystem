import { useProfileSessionGuard } from "@/hooks/useProfileSessionGuard"
import { useSessionProfileRefresh } from "./useSessionProfileRefresh"
import { useState, useCallback, useRef, useMemo, useEffect } from "react"
import { useTranslation } from "react-i18next"

import api from "@/api/client"
import { useAuth } from "@/contexts/AuthContext"
import { resolveMediaUrl, addVersionParam } from "@/utils/media"
import type { SetSnackbar } from "@/pages/settings/types"
import { useObjectUrlPreview } from "./useObjectUrlPreview"
import { MAX_IMAGE_UPLOAD_BYTES } from "@/constants/uploads"

const DEFAULT_AVATAR = "https://www.gravatar.com/avatar/00000000000000000000000000000000?d=mp&f=y"
const ALLOWED_IMAGE_TYPES = new Set(["image/png", "image/jpeg", "image/webp"])

const isImage = (file: File) => ALLOWED_IMAGE_TYPES.has(file.type.toLowerCase())
const withinSize = (file: File) => file.size <= MAX_IMAGE_UPLOAD_BYTES

export function useAvatarUpload(setSnackbar: SetSnackbar) {
  const { t } = useTranslation(["settings"])
  const { user } = useAuth()
  const captureOperation = useProfileSessionGuard()
  const refreshUser = useSessionProfileRefresh()

  const inputRef = useRef<HTMLInputElement | null>(null)
  const [busy, setBusy] = useState(false)
  const [version, setVersion] = useState(Date.now())
  const { previewUrl, beginPreview, clearPreview } = useObjectUrlPreview()

  useEffect(() => {
    clearPreview()
    setBusy(false)
  }, [captureOperation, clearPreview])

  const avatarUrl = user?.avatar_url ?? undefined

  const avatarSrc = useMemo(() => {
    const resolved = resolveMediaUrl(avatarUrl)
    return previewUrl ?? (resolved ? addVersionParam(resolved, version) : DEFAULT_AVATAR)
  }, [avatarUrl, previewUrl, version])

  const triggerPick = useCallback(() => {
    inputRef.current?.click()
  }, [])

  const upload = useCallback(
    async (file: File) => {
      const isCurrent = captureOperation()
      if (!isCurrent()) return
      if (!isImage(file)) {
        setSnackbar({
          text: t("settings:media.validation.supportedFormats"),
          severity: "error",
        })
        return
      }
      if (!withinSize(file)) {
        setSnackbar({
          text: t("settings:media.validation.fileTooLarge"),
          severity: "error",
        })
        return
      }

      beginPreview(file)
      setBusy(true)
      try {
        const formData = new FormData()
        formData.append("file", file)
        await api.post("/users/me/avatar", formData, {
          headers: { "Content-Type": "multipart/form-data" },
        })
        if (!(await refreshUser(isCurrent)) || !isCurrent()) return
        // Keep cache-busting monotonic even when an upload and the initial
        // render happen within the same clock tick.  A repeated timestamp
        // would leave the browser serving the stale avatar URL.
        setVersion((current) => Math.max(Date.now(), current + 1))
        setSnackbar({
          text: t("settings:media.avatar.updated"),
          severity: "success",
        })
      } catch {
        if (!isCurrent()) return
        setSnackbar({
          text: t("settings:media.avatar.uploadFailed"),
          severity: "error",
        })
      } finally {
        if (isCurrent()) {
          clearPreview()
          setBusy(false)
        }
      }
    },
    [beginPreview, captureOperation, clearPreview, refreshUser, setSnackbar, t]
  )

  const remove = useCallback(async () => {
    const isCurrent = captureOperation()
    if (!isCurrent()) return
    setBusy(true)
    try {
      await api.delete("/users/me/avatar")
      if (!(await refreshUser(isCurrent)) || !isCurrent()) return
      setVersion((current) => Math.max(Date.now(), current + 1))
      setSnackbar({
        text: t("settings:media.avatar.deleted"),
        severity: "success",
      })
    } catch {
      if (!isCurrent()) return
      setSnackbar({
        text: t("settings:media.avatar.deleteFailed"),
        severity: "error",
      })
    } finally {
      if (isCurrent()) setBusy(false)
    }
  }, [captureOperation, refreshUser, setSnackbar, t])

  const handleError = useCallback((event: React.SyntheticEvent<HTMLImageElement>) => {
    const img = event.currentTarget
    img.onerror = null
    img.src = DEFAULT_AVATAR
  }, [])

  return {
    inputRef,
    busy,
    avatarSrc,
    triggerPick,
    upload,
    remove,
    handleError,
  }
}
