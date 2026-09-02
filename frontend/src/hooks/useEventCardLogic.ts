import { useState, useMemo, useEffect, useCallback } from "react"
import { useTranslation } from "react-i18next"
import { useNavigate } from "@tanstack/react-router"
import { formatRelativeTime } from "@/utils/date"

import api from "@/api/client"
import { useAuth } from "@/contexts/AuthContext"
import { useEventRegistration } from "@/hooks/useEventRegistration"
import { useSpotlight } from "@/components/ui/Spotlight"
import type { Event, EventEditDraft } from "@/types/Event"
import { captureActiveTelemetryContext } from "@/utils/telemetryContext"

// dayjs extensions removed

const parseDate = (d?: string | null) => {
  if (!d) return new Date(NaN)
  return new Date(d.includes(" ") && !d.includes("T") ? d.replace(" ", "T") : d)
}

interface UseEventCardLogicProps extends Partial<Event> {
  id: string
  // Optional callbacks or initial states if needed
  onChange?: () => void
}

export function useEventCardLogic({
  id,
  title = "",
  title_en = "",
  description = "",
  description_en = "",
  event_type = "",
  event_type_en = "",
  location = "",
  location_en = "",
  starts_at = "",
  ends_at = "",
  participant_count = 0,
  is_registered = false,
  my_qr_token,
  speaker = "",
  image_url = "",
  onChange,
}: UseEventCardLogicProps) {
  const { user } = useAuth()
  const navigate = useNavigate()
  const { t } = useTranslation(["events", "common"])
  const spotlight = useSpotlight()

  // -- UI State --
  const [snackbar, setSnackbar] = useState<string>("")
  const [loading, setLoading] = useState(false)
  const [menuAnchor, setMenuAnchor] = useState<null | HTMLElement>(null)
  const [editOpen, setEditOpen] = useState(false)
  const [confirmDeleteOpen, setConfirmDeleteOpen] = useState(false)

  // -- Image Upload State --
  const [newImage, setNewImage] = useState<File | null>(null)
  const [imageLoading, setImageLoading] = useState(false)
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)
  const [cardImageReady, setCardImageReady] = useState(() => !image_url)

  // -- Edit Form State --
  const [editData, setEditData] = useState<EventEditDraft>({
    title: title || "",
    title_en: title_en || "",
    description: description || "",
    description_en: description_en || "",
    event_type: event_type || "",
    event_type_en: event_type_en || "",
    location: location || "",
    location_en: location_en || "",
    starts_at: starts_at || "",
    ends_at: ends_at || "",
    speaker: speaker || "",
    image_url: image_url || "",
  })

  const menuId = useMemo(() => `event-card-menu-${id}`, [id])

  // -- Event Registration Hook --
  const registration = useEventRegistration({
    eventId: id,
    user,
    initialRegistered: is_registered ?? false,
    initialParticipantCount: participant_count,
    initialQrToken: my_qr_token ?? undefined,
    onNotify: setSnackbar,
  })

  // -- Computed Properties --
  const timeStatus = useMemo(() => {
    const now = new Date()
    const start = parseDate(starts_at)
    const end = parseDate(ends_at)

    if (now > start && now < end) return { status: "live" as const }

    const diffMs = start.getTime() - now.getTime()
    if (diffMs > 0 && diffMs < 24 * 60 * 60 * 1000) {
      return { status: "soon" as const, timeText: formatRelativeTime(start, "en-US") }
    }
    return { status: "none" as const }
  }, [starts_at, ends_at])

  const eventEnded = useMemo(() => {
    const end = parseDate(ends_at)
    return !isNaN(end.getTime()) && end < new Date()
  }, [ends_at])

  const cardImageUrl = useMemo(() => previewUrl || image_url || undefined, [image_url, previewUrl])

  // -- Side Effects --
  useEffect(() => {
    if (newImage) {
      const url = URL.createObjectURL(newImage)
      setPreviewUrl(url)
      return () => URL.revokeObjectURL(url)
    }
    setPreviewUrl(null)
  }, [newImage])

  // -- Handlers --
  const handleEdit = async () => {
    const telemetryContext = captureActiveTelemetryContext()
    setLoading(true)
    try {
      let imgUrl = editData.image_url
      const image = newImage
      if (image) {
        setImageLoading(true)
        const data = new FormData()
        data.append("file", image)
        const uploadRes = await telemetryContext.run(() =>
          api.post<{ url: string }>(`/events/upload_image`, data)
        )
        imgUrl = uploadRes.data.url
        setImageLoading(false)
      }
      const payload = {
        ...editData,
        starts_at: parseDate(editData.starts_at).toISOString(),
        ends_at: parseDate(editData.ends_at).toISOString(),
        image_url: imgUrl,
      }
      await telemetryContext.run(() => api.patch(`/events/${id}`, payload))
      setEditOpen(false)
      telemetryContext.run(() => onChange?.())
      setSnackbar(t("events:card.messages.saveSuccess"))
    } catch {
      setSnackbar(t("events:card.messages.saveFailure"))
    } finally {
      setLoading(false)
    }
  }

  const handleDelete = async () => {
    const telemetryContext = captureActiveTelemetryContext()
    setLoading(true)
    try {
      await telemetryContext.run(() => api.delete(`/events/${id}`))
      setConfirmDeleteOpen(false)
      telemetryContext.run(() => onChange?.())
      setSnackbar(t("events:card.messages.deleteSuccess"))
    } catch {
      setSnackbar(t("events:card.messages.deleteFailure"))
    } finally {
      setLoading(false)
    }
  }

  const navigateToDetails = useCallback(
    () => navigate({ to: "/events/$id", params: { id: String(id) } }),
    [id, navigate]
  )

  const handleCardClick = (e: React.MouseEvent) => {
    if (editOpen) return
    const target = e.target as HTMLElement
    // Prevent navigation if clicking interactive elements
    if (target.closest("button") || target.closest("a") || target.closest('[role="menu"]')) return
    navigateToDetails()
  }

  return {
    // Objects/Values
    user,
    t,
    spotlight,
    menuId,
    timeStatus,
    eventEnded,
    cardImageUrl,

    // State
    snackbar,
    setSnackbar,
    loading,
    menuAnchor,
    setMenuAnchor,
    editOpen,
    setEditOpen,
    confirmDeleteOpen,
    setConfirmDeleteOpen,
    editData,
    setEditData,
    newImage,
    setNewImage,
    imageLoading,
    cardImageReady,
    setCardImageReady,
    previewUrl,

    // Registration
    registration,

    // Methods
    handleEdit,
    handleDelete,
    navigate: navigateToDetails,
    onCardClick: handleCardClick,
  }
}
