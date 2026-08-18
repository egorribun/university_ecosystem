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

const INITIAL_DRAFT: EventDraft = {
  title: "",
  title_en: "",
  description: "",
  description_en: "",
  event_type: "",
  event_type_en: "",
  location: "",
  location_en: "",
  starts_at: "",
  ends_at: "",
  speaker: "",
  image_url: "",
  about: "",
  about_en: "",
}

type EventCreateDialogProps = {
  open: boolean
  onClose: () => void
  onCreated: (data: EventDraft) => void
  language: "ru" | "en"
}

export function EventCreateDialog({ open, onClose, onCreated, language }: EventCreateDialogProps) {
  const { t } = useTranslation(["events", "common"])

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
      uploadGenerationRef.current += 1
    }
  }, [])

  const handleClose = () => {
    uploadGenerationRef.current += 1
    setDraft(INITIAL_DRAFT)
    setImageUploading(false)
    setPreview(null)
    onClose()
  }

  const handleSubmit = () => {
    onCreated(draft)
    handleClose()
  }

  const normalizedTitle = draft.title.trim() || draft.title_en.trim()
  const normalizedLocation = draft.location.trim() || draft.location_en.trim()
  const starts = new Date(draft.starts_at).getTime()
  const ends = new Date(draft.ends_at).getTime()
  const dateError = !!(draft.starts_at && draft.ends_at && ends <= starts)

  const canSubmit =
    !!normalizedTitle &&
    !!draft.starts_at &&
    !!draft.ends_at &&
    !!normalizedLocation &&
    !imageUploading &&
    !dateError

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
                    const file = event.target.files?.[0]
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
