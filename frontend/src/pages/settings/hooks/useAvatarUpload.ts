import { useState, useCallback, useRef, useMemo } from "react"
import { useQueryClient } from "@tanstack/react-query"
import { useTranslation } from "react-i18next"

import api from "@/api/client"
import { useAuth } from "@/contexts/AuthContext"
import { currentUserQueryKey, fetchCurrentUser } from "@/hooks/auth/useProfileSync"
import { resolveMediaUrl, addVersionParam } from "@/utils/media"
import type { User } from "@/types/User"
import type { SetSnackbar } from "@/pages/settings/types"
import { useObjectUrlPreview } from "./useObjectUrlPreview"

const DEFAULT_AVATAR = "https://www.gravatar.com/avatar/00000000000000000000000000000000?d=mp&f=y"
const MAX_FILE_SIZE_MB = 12

const isImage = (file: File) => /^image\/(png|jpe?g|webp|gif|avif)$/i.test(file.type)
const withinSize = (file: File, maxMB = MAX_FILE_SIZE_MB) => file.size / (1024 * 1024) <= maxMB

export function useAvatarUpload(setSnackbar: SetSnackbar) {
  const { t } = useTranslation(["settings"])
  const { user, setUser } = useAuth()
  const queryClient = useQueryClient()

  const inputRef = useRef<HTMLInputElement | null>(null)
  const [busy, setBusy] = useState(false)
  const [version, setVersion] = useState(Date.now())
  const { previewUrl, beginPreview, clearPreview } = useObjectUrlPreview()

  const avatarUrl = user?.avatar_url ?? undefined

  const avatarSrc = useMemo(() => {
    const resolved = resolveMediaUrl(avatarUrl)
    return previewUrl ?? (resolved ? addVersionParam(resolved, version) : DEFAULT_AVATAR)
  }, [avatarUrl, previewUrl, version])

  const refreshUser = useCallback(async () => {
    const fresh = await queryClient.fetchQuery<User>({
      queryKey: currentUserQueryKey,
      queryFn: ({ signal }) => fetchCurrentUser({ signal }),
      staleTime: 0,
    })
    setUser(fresh)
    return fresh
  }, [queryClient, setUser])

  const triggerPick = useCallback(() => {
    inputRef.current?.click()
  }, [])

  const upload = useCallback(
    async (file: File) => {
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
        await refreshUser()
        setVersion(Date.now())
        setSnackbar({
          text: t("settings:media.avatar.updated"),
          severity: "success",
        })
      } catch {
        setSnackbar({
          text: t("settings:media.avatar.uploadFailed"),
          severity: "error",
        })
      } finally {
        clearPreview()
        setBusy(false)
      }
    },
    [beginPreview, clearPreview, refreshUser, setSnackbar, t]
  )

  const remove = useCallback(async () => {
    setBusy(true)
    try {
      await api.delete("/users/me/avatar")
      await refreshUser()
      setVersion(Date.now())
      setSnackbar({
        text: t("settings:media.avatar.deleted"),
        severity: "success",
      })
    } catch {
      setSnackbar({
        text: t("settings:media.avatar.deleteFailed"),
        severity: "error",
      })
    } finally {
      setBusy(false)
    }
  }, [refreshUser, setSnackbar, t])

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
