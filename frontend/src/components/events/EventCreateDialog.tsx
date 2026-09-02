import { useState, useEffect, useRef } from "react"
import { useTranslation } from "react-i18next"
import { Search as SearchIcon } from "lucide-react"

import SmartImage from "@/components/media/SmartImage"
import { Button } from "@/components/ui"
import { TextField } from "@/components/ui/TextField"
import { Dialog, DialogActions, DialogContent, DialogTitle } from "@/components/settings"
import { uploadEventImage } from "@/api/events"

type EventDraft = {
  title: string
  title_en: string
  description: string
  description_en: string
  event_type: string
  event_type_en: string
  location: string
  location_en: string
  starts_at: string
  ends_at: string
  speaker: string
  image_url: string
  about: string
  about_en: string
}

const EMPTY_DRAFT_VALUE = ""
const TRANSLATION_NAMESPACES = ["events", "common"] as const

/** Resolve a localized required value without accepting whitespace-only input. */
export function normalizeLocalizedValue(primary: string, fallback: string): string {
  const normalizedPrimary = primary.trim()
  return normalizedPrimary || fallback.trim()
}

/** Date validation is only applicable once both endpoints have been supplied. */
export function hasInvalidEventDates(startsAt: string, endsAt: string): boolean {
  if (!startsAt || !endsAt) return false
  return new Date(endsAt).getTime() <= new Date(startsAt).getTime()
}

export type EventSubmitState = {
  normalizedTitle: string
  startsAt: string
  endsAt: string
  normalizedLocation: string
  imageUploading: boolean
  dateError: boolean
}

export function canSubmitEventDraft(state: EventSubmitState): boolean {
  return (
    Boolean(state.normalizedTitle) &&
    Boolean(state.startsAt) &&
    Boolean(state.endsAt) &&
    Boolean(state.normalizedLocation) &&
    !state.imageUploading &&
    !state.dateError
  )
}

/** File inputs can emit null/empty FileLists; never manufacture a file. */
export function firstSelectedFile(files: FileList | null | undefined): File | undefined {
  if (!files || files.length === 0) return undefined
  return files[0]
}

export function invalidateUploadGeneration(ref: { current: number }): void {
  ref.current += 1
}

const INITIAL_DRAFT: EventDraft = {
  title: EMPTY_DRAFT_VALUE,
  title_en: EMPTY_DRAFT_VALUE,
  description: EMPTY_DRAFT_VALUE,
  description_en: EMPTY_DRAFT_VALUE,
  event_type: EMPTY_DRAFT_VALUE,
  event_type_en: EMPTY_DRAFT_VALUE,
  location: EMPTY_DRAFT_VALUE,
  location_en: EMPTY_DRAFT_VALUE,
  starts_at: EMPTY_DRAFT_VALUE,
  ends_at: EMPTY_DRAFT_VALUE,
  speaker: EMPTY_DRAFT_VALUE,
  image_url: EMPTY_DRAFT_VALUE,
  about: EMPTY_DRAFT_VALUE,
  about_en: EMPTY_DRAFT_VALUE,
}

type EventCreateDialogProps = {
  open: boolean
  onClose: () => void
  onCreated: (data: EventDraft) => void
  language: "ru" | "en"
}

export function EventCreateDialog({ open, onClose, onCreated, language }: EventCreateDialogProps) {
  const { t } = useTranslation(TRANSLATION_NAMESPACES)

  const [draft, setDraft] = useState<EventDraft>(INITIAL_DRAFT)
  const [imageUploading, setImageUploading] = useState(false)
  const [preview, setPreview] = useState<string | null>(null)
  const uploadGenerationRef = useRef(0)

  const getLocalizedValue = (
    field: "title" | "description" | "event_type" | "location" | "about"
  ) => {
    const key = (language === "en" ? `${field}_en` : field) as keyof EventDraft
    return draft[key]
  }

  const updateLocalizedValue = (
    field: "title" | "description" | "event_type" | "location" | "about",
    value: string
  ) => {
    const key = (language === "en" ? `${field}_en` : field) as keyof EventDraft
    setDraft((previous) => ({ ...previous, [key]: value }))
  }

  const handleImageUpload = async (file: File) => {
    const uploadGeneration = ++uploadGenerationRef.current
    setImageUploading(true)
    const localUrl = URL.createObjectURL(file)
    setPreview(localUrl)
    try {
      const imageUrl = await uploadEventImage(file)
      if (uploadGeneration !== uploadGenerationRef.current) return

      setDraft((previous) => ({ ...previous, image_url: imageUrl }))
      // The server URL is canonical after upload; releasing the temporary Blob
      // also keeps the rendered preview aligned with the value that is submitted.
      setPreview(null)
    } finally {
      if (uploadGeneration === uploadGenerationRef.current) {
        setImageUploading(false)
      }
    }
  }

  // Cleanup preview Blob URL on unmount or preview update
  useEffect(() => {
    return () => {
      if (preview) URL.revokeObjectURL(preview)
    }
  }, [preview])

  useEffect(() => {
    return () => {
      invalidateUploadGeneration(uploadGenerationRef)
    }
  }, [])

  const handleClose = () => {
    invalidateUploadGeneration(uploadGenerationRef)
    setDraft(INITIAL_DRAFT)
    setImageUploading(false)
    setPreview(null)
    onClose()
  }

  const handleSubmit = () => {
    onCreated(draft)
    handleClose()
  }

  const normalizedTitle = normalizeLocalizedValue(draft.title, draft.title_en)
  const normalizedLocation = normalizeLocalizedValue(draft.location, draft.location_en)
  const dateError = hasInvalidEventDates(draft.starts_at, draft.ends_at)

  const canSubmit = canSubmitEventDraft({
    normalizedTitle,
    startsAt: draft.starts_at,
    endsAt: draft.ends_at,
    normalizedLocation,
    imageUploading,
    dateError,
  })

  return (
    <Dialog open={open} onClose={handleClose} maxWidth="lg" fullWidth>
      <DialogTitle>{t("events:dialogs.create.title")}</DialogTitle>
      <DialogContent className="space-y-6 pt-4">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* Left column — localized fields */}
          <div className="space-y-4">
            <TextField
              label={language === "en" ? t("events:form.title_en") : t("events:form.title")}
              value={getLocalizedValue("title")}
              onChange={(event) => updateLocalizedValue("title", event.target.value)}
              fullWidth
            />
            <TextField
              label={
                language === "en" ? t("events:form.description_en") : t("events:form.description")
              }
              value={getLocalizedValue("description")}
              onChange={(event) => updateLocalizedValue("description", event.target.value)}
              multiline
              rows={3}
              fullWidth
            />
            <TextField
              label={language === "en" ? t("events:form.type_en") : t("events:form.type")}
              value={getLocalizedValue("event_type")}
              onChange={(event) => updateLocalizedValue("event_type", event.target.value)}
              fullWidth
            />
            <TextField
              label={language === "en" ? t("events:form.location_en") : t("events:form.location")}
              value={getLocalizedValue("location")}
              onChange={(event) => updateLocalizedValue("location", event.target.value)}
              fullWidth
            />
          </div>

          {/* Right column — speaker, image, dates */}
          <div className="space-y-4">
            <TextField
              label={t("events:form.speaker")}
              value={draft.speaker}
              onChange={(event) => setDraft({ ...draft, speaker: event.target.value })}
              fullWidth
            />
            <div className="space-y-3">
              <label className="mb-0.5 block px-1 text-xs font-bold uppercase tracking-widest text-(--text-secondary)">
                {t("events:form.image")}
              </label>
              <Button
                as="label"
                variant="outline"
                disabled={imageUploading}
                className="w-full justify-start gap-2 bg-(--bg-surface)/(--opacity-dim)"
              >
                {imageUploading ? (
                  t("common:statuses.uploading")
                ) : (
                  <>
                    <SearchIcon className="h-4 w-4" />
                    {draft.image_url
                      ? t("events:form.imageSelected")
                      : t("events:form.uploadImage")}
                  </>
                )}
                <input
                  type="file"
                  hidden
                  accept="image/*"
                  onChange={(event) => {
                    const file = firstSelectedFile(event.currentTarget.files)
                    if (file) void handleImageUpload(file)
                  }}
                />
              </Button>
              {(preview || draft.image_url) && (
                <div className="mt-3 overflow-hidden rounded-md border border-glass-border shadow-glass">
                  <SmartImage
                    srcRaw={preview || draft.image_url}
                    alt={t("events:alt.preview")}
                    className="aspect-video w-full object-cover"
                  />
                </div>
              )}
            </div>
            <div className="grid grid-cols-2 gap-4">
              <TextField
                label={t("events:form.start")}
                type="datetime-local"
                value={draft.starts_at}
                onChange={(event) => setDraft({ ...draft, starts_at: event.target.value })}
                fullWidth
              />
              <TextField
                label={t("events:form.end")}
                type="datetime-local"
                value={draft.ends_at}
                onChange={(event) => setDraft({ ...draft, ends_at: event.target.value })}
                error={dateError}
                helperText={dateError ? t("events:form.errors.endsBeforeStarts") : undefined}
                fullWidth
              />
            </div>
          </div>
        </div>
      </DialogContent>
      <DialogActions className="flex-col-reverse gap-3 sm:flex-row p-6">
        <Button variant="ghost" onClick={handleClose} className="w-full sm:w-auto">
          {t("common:buttons.cancel")}
        </Button>
        <Button
          variant="solid"
          onClick={handleSubmit}
          disabled={!canSubmit}
          className="w-full sm:w-auto min-w-(--min-w-btn)"
        >
          {t("common:buttons.create")}
        </Button>
      </DialogActions>
    </Dialog>
  )
}
