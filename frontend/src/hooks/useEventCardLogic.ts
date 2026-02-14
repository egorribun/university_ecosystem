import { useState, useMemo, useEffect, useCallback } from "react"
import { useTranslation } from "react-i18next"
import { useNavigate } from "react-router-dom"
import dayjs from "dayjs"
import utc from "dayjs/plugin/utc"
import timezone from "dayjs/plugin/timezone"
import relativeTime from "dayjs/plugin/relativeTime"

import api from "../api/client"
import { useAuth } from "../contexts/AuthContext"
import { useEventRegistration } from "@/hooks/useEventRegistration"
import { useSpotlight } from "@/components/ui/Spotlight"
import type { Event, EventEditDraft } from "@/types/Event"

dayjs.extend(utc)
dayjs.extend(timezone)
dayjs.extend(relativeTime)

const normalizeDate = (d?: string) => (d ? d.replace("T", " ").replace("Z", "") : "")

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
    initialParticipantCount: participant_count ?? 0,
    initialQrToken: my_qr_token ?? undefined,
    onNotify: setSnackbar,
  })

  // -- Computed Properties --
  const timeStatus = useMemo(() => {
    const now = dayjs()
    const start = dayjs(normalizeDate(starts_at).replace(" ", "T"))
    const end = dayjs(normalizeDate(ends_at).replace(" ", "T"))

    if (now.isAfter(start) && now.isBefore(end)) return { status: "live" as const }
    if (now.isBefore(start) && start.diff(now, "hour") < 24) {
      return { status: "soon" as const, timeText: start.fromNow(true) }
    }
    return { status: "none" as const }
  }, [starts_at, ends_at])

  const eventEnded = useMemo(() => {
    const end = dayjs(normalizeDate(ends_at).replace(" ", "T"))
    return end.isValid() && end.isBefore(dayjs())
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
    setLoading(true)
    try {
      let imgUrl = editData.image_url
      if (newImage) {
        setImageLoading(true)
        const data = new FormData()
        data.append("file", newImage)
        const uploadRes = await api.post<{ url: string }>(`/events/upload_image`, data, {
          headers: { "Content-Type": "multipart/form-data" },
        })
        imgUrl = uploadRes.data.url
        setImageLoading(false)
      }
      const payload = {
        ...editData,
        starts_at: normalizeDate(editData.starts_at),
        ends_at: normalizeDate(editData.ends_at),
        image_url: imgUrl,
      }
      await api.patch(`/events/${id}`, payload)
      setEditOpen(false)
      onChange?.()
      setSnackbar(t("events:card.messages.saveSuccess"))
    } catch {
      setSnackbar(t("events:card.messages.saveFailure"))
    } finally {
      setLoading(false)
    }
  }

  const handleDelete = async () => {
    setLoading(true)
    try {
      await api.delete(`/events/${id}`)
      setConfirmDeleteOpen(false)
      onChange?.()
      setSnackbar(t("events:card.messages.deleteSuccess"))
    } catch {
      setSnackbar(t("events:card.messages.deleteFailure"))
    } finally {
      setLoading(false)
    }
  }

  const navigateToDetails = useCallback(() => navigate(`/events/${id}`), [id, navigate])

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
