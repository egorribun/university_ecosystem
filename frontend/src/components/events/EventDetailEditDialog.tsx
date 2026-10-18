/**
 * EventDetailEditDialog — edit dialog for event detail page.
 * Wraps EventEditDialog with detail-page-specific state management.
 * Handles PATCH /events/{id} and image upload.
 */

import { useState, useCallback, useMemo, useEffect } from "react"
import { useTranslation } from "react-i18next"
import { useQueryClient } from "@tanstack/react-query"
import { EventEditDialog } from "./EventEditDialog"
import { uploadEventImage } from "@/api/events"
import api from "@/api/client"
import { logError } from "@/app/logger"
import type { Event, EventEditDraft } from "@/types/Event"
import { useCampusTimezone } from "@/contexts/CampusTimezoneContext"
import { resolveCampusEventDateRange } from "@/utils/eventDateTime"

interface EventDetailEditDialogProps {
  open: boolean
  onClose: () => void
  event: Event
  onSuccess: (msg: string) => void
  onError: (msg: string) => void
}

const EMPTY_EDIT_VALUE = ""
const EVENT_DIALOG_NAMESPACES = ["events", "common"] as const

/** Normalize required localized fields before handing them to the edit form. */
export function normalizeLocalizedEditValue(primary: string, fallback: string): string {
  const normalizedPrimary = primary.trim()
  return normalizedPrimary || fallback.trim()
}

export function EventDetailEditDialog({
  open,
  onClose,
  event,
  onSuccess,
  onError,
}: EventDetailEditDialogProps) {
  const { t, i18n } = useTranslation(EVENT_DIALOG_NAMESPACES)
  const queryClient = useQueryClient()
  const campusTimezone = useCampusTimezone()

  const initialDraft: EventEditDraft = useMemo(
    () => ({
      id: event.id,
      title: event.title ?? EMPTY_EDIT_VALUE,
      title_en: event.title_en ?? EMPTY_EDIT_VALUE,
      description: event.description ?? EMPTY_EDIT_VALUE,
      description_en: event.description_en ?? EMPTY_EDIT_VALUE,
      event_type: event.event_type ?? EMPTY_EDIT_VALUE,
      event_type_en: event.event_type_en ?? EMPTY_EDIT_VALUE,
      location: event.location ?? EMPTY_EDIT_VALUE,
      location_en: event.location_en ?? EMPTY_EDIT_VALUE,
      starts_at: event.starts_at ?? EMPTY_EDIT_VALUE,
      ends_at: event.ends_at ?? EMPTY_EDIT_VALUE,
      speaker: event.speaker ?? EMPTY_EDIT_VALUE,
      image_url: event.image_url ?? EMPTY_EDIT_VALUE,
      about: event.about ?? EMPTY_EDIT_VALUE,
      about_en: event.about_en ?? EMPTY_EDIT_VALUE,
    }),
    [event]
  )

  const [draft, setDraft] = useState<EventEditDraft>(initialDraft)
  const [loading, setLoading] = useState(false)
  const [imageLoading, setImageLoading] = useState(false)
  const [newImage, setNewImage] = useState<File | null>(null)
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)
  const dateRange = resolveCampusEventDateRange(draft.starts_at, draft.ends_at, campusTimezone, {
    startsAt: event.starts_at,
    endsAt: event.ends_at,
  })

  // Create/revoke ObjectURL preview when user picks a new image
  useEffect(() => {
    if (newImage) {
      const url = URL.createObjectURL(newImage)
      setPreviewUrl(url)
      return () => URL.revokeObjectURL(url)
    }
    setPreviewUrl(null)
  }, [newImage])

  const handleSave = useCallback(async () => {
    const dateRange = resolveCampusEventDateRange(draft.starts_at, draft.ends_at, campusTimezone, {
      startsAt: event.starts_at,
      endsAt: event.ends_at,
    })
    if (!dateRange.valid || !dateRange.startsAt || !dateRange.endsAt) return

    setLoading(true)
    try {
      // Upload image if changed
      let imageUrl = draft.image_url
      if (newImage) {
        setImageLoading(true)
        imageUrl = await uploadEventImage(newImage, event.id)
        setImageLoading(false)
      }

      const update = {
        ...draft,
        starts_at: dateRange.startsAt,
        ends_at: dateRange.endsAt,
        image_url: imageUrl,
      }
      delete update.id
      if (i18n.language === "en") {
        // The event response's source fields are localized by Accept-Language.
        // This dialog edits only the active locale; omit stale English values
        // from the Russian source fields on English saves.
        delete update.title
        delete update.description
        delete update.event_type
        delete update.location
        delete update.about
      }
      await api.patch(`/events/${event.id}`, update)
      await queryClient.invalidateQueries({ queryKey: ["events", "detail", event.id] })
      await queryClient.invalidateQueries({ queryKey: ["events", "list"] })

      onSuccess(t("events:card.messages.saveSuccess"))
      onClose()
    } catch (err) {
      logError("[EventDetailEditDialog] Save failed:", err)
      onError(t("events:card.messages.saveFailure"))
    } finally {
      setLoading(false)
      setImageLoading(false)
    }
  }, [
    campusTimezone,
    draft,
    newImage,
    event.id,
    event.starts_at,
    event.ends_at,
    i18n.language,
    queryClient,
    onSuccess,
    onError,
    onClose,
    t,
  ])

  // Reset state when dialog closes
  const handleClose = useCallback(() => {
    setDraft(initialDraft)
    setNewImage(null) // triggers useEffect → revokes ObjectURL + clears previewUrl
    onClose()
  }, [initialDraft, onClose])

  // initialDraft normalizes all editable fields to strings, and the controlled
  // inputs in EventEditDialog preserve that invariant on every update.
  const normalizedTitle = normalizeLocalizedEditValue(draft.title!, draft.title_en!)
  const normalizedLocation = normalizeLocalizedEditValue(draft.location!, draft.location_en!)

  return (
    <EventEditDialog
      open={open}
      onClose={handleClose}
      draft={draft}
      setDraft={setDraft}
      onSave={() => void handleSave()}
      loading={loading}
      imageLoading={imageLoading}
      dateError={!dateRange.valid}
      startDateError={dateRange.startError}
      endDateError={dateRange.endError}
      normalizedTitle={normalizedTitle}
      normalizedLocation={normalizedLocation}
      newImage={newImage}
      setNewImage={setNewImage}
      previewUrl={previewUrl}
    />
  )
}
