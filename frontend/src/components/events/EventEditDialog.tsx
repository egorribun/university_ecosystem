import { useRef, useMemo, useId, type ChangeEvent } from "react"
import { useTranslation } from "react-i18next"
import { Pencil as EditIcon, X as CloseIcon } from "lucide-react"
import { Button } from "@/components/ui/Button"
import { Dialog } from "@/components/ui/Dialog"
import SmartImage from "@/components/media/SmartImage"
import { cn } from "@/utils/cn"
import { useCampusTimezone } from "@/contexts/CampusTimezoneContext"
import {
  eventDateErrorTranslationKey,
  formatEventDateInput,
  resolveCampusEventDateRange,
  type EventDateFieldError,
} from "@/utils/eventDateTime"

import type { EventEditDraft } from "@/types/Event"

type EventEditDialogProps = {
  open: boolean
  onClose: () => void
  draft: EventEditDraft
  setDraft: (draft: EventEditDraft) => void
  onSave: () => void
  loading: boolean
  imageLoading: boolean
  dateError: boolean
  startDateError?: EventDateFieldError | null
  endDateError?: EventDateFieldError | null
  normalizedTitle: string
  normalizedLocation: string
  newImage: File | null
  setNewImage: (file: File | null) => void
  previewUrl: string | null
}

export function normalizeDatetimeLocal(value: string | null | undefined): string {
  if (value === undefined || value === null) return ""
  return value.slice(0, 16)
}

export function EventEditDialog({
  open,
  onClose,
  draft,
  setDraft,
  onSave,
  loading,
  imageLoading,
  dateError,
  startDateError = null,
  endDateError = null,
  normalizedTitle,
  normalizedLocation,
  setNewImage,
  previewUrl,
}: EventEditDialogProps) {
  const { t, i18n } = useTranslation(["events", "common"])
  const campusTimezone = useCampusTimezone()
  const dateRange = resolveCampusEventDateRange(
    draft.starts_at ?? "",
    draft.ends_at ?? "",
    campusTimezone
  )
  const resolvedStartDateError = startDateError ?? dateRange.startError
  const resolvedEndDateError = endDateError ?? dateRange.endError
  const resolvedDateError = dateError || !dateRange.valid
  const language = i18n.language
  const imageInputRef = useRef<HTMLInputElement>(null)
  const baseId = useId()

  const inputClass =
    "w-full rounded-lg bg-(--input-bg) border border-(--input-border) px-3 py-2 text-sm text-text-primary placeholder:text-(--input-placeholder) focus:border-brand focus:outline-none focus:ring-1 focus:ring-brand transition-colors duration-fast"

  const getLocalizedEditValue = (field: "title" | "description" | "event_type" | "location") => {
    if (language === "en") {
      return draft[`${field}_en` as keyof EventEditDraft] as string
    }
    return draft[field]
  }

  const updateLocalizedEditValue = (
    field: "title" | "description" | "event_type" | "location",
    value: string
  ) => {
    if (language === "en") {
      setDraft({ ...draft, [`${field}_en`]: value })
    } else {
      setDraft({ ...draft, [field]: value })
    }
  }

  const handleImageChange = (e: ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files
    const fileCollection = files ? files : []
    const file = fileCollection[0]
    if (file) setNewImage(file)
  }

  const cardImageUrl = useMemo(
    () => (previewUrl ? previewUrl : draft.image_url || undefined),
    [draft.image_url, previewUrl]
  )
  const startDateErrorText = resolvedStartDateError
    ? t(eventDateErrorTranslationKey(resolvedStartDateError, "start"))
    : undefined
  const endDateErrorText = resolvedEndDateError
    ? t(eventDateErrorTranslationKey(resolvedEndDateError, "end"))
    : undefined
  const endDateOrderErrorText =
    resolvedDateError && !resolvedEndDateError && !resolvedStartDateError
      ? t("events:form.errors.endsBeforeStarts")
      : undefined
  const endDateErrorMessage = endDateErrorText ?? endDateOrderErrorText

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={
        <div className="flex items-center gap-2">
          <EditIcon size={20} />
          {t("events:card.dialogs.edit.title")}
        </div>
      }
      size="lg"
      footer={
        <>
          <Button
            variant="outline"
            onClick={onClose}
            leadingIcon={<CloseIcon size={18} />}
            className="w-full sm:w-auto"
          >
            {t("common:buttons.cancel")}
          </Button>
          <Button
            variant="solid"
            onClick={onSave}
            disabled={
              loading ||
              imageLoading ||
              resolvedDateError ||
              !normalizedTitle ||
              !normalizedLocation
            }
            className="w-full sm:w-auto"
          >
            {t("common:buttons.save")}
          </Button>
        </>
      }
      footerClassName="flex-col-reverse gap-3 sm:flex-row"
    >
      <div className="space-y-4">
        <div>
          <label
            htmlFor={`${baseId}-title`}
            className="mb-2 block text-sm font-semibold tracking-wide text-(--text-secondary) opacity-heavy"
          >
            {language === "en" ? t("events:form.title_en") : t("events:form.title")}
          </label>
          <input
            id={`${baseId}-title`}
            type="text"
            value={getLocalizedEditValue("title") || ""}
            onChange={(e) => updateLocalizedEditValue("title", e.target.value)}
            className={inputClass}
          />
        </div>
        <div>
          <label
            htmlFor={`${baseId}-desc`}
            className="mb-2 block text-sm font-semibold tracking-wide text-(--text-secondary) opacity-heavy"
          >
            {language === "en" ? t("events:form.description_en") : t("events:form.description")}
          </label>
          <textarea
            id={`${baseId}-desc`}
            value={getLocalizedEditValue("description") || ""}
            onChange={(e) => updateLocalizedEditValue("description", e.target.value)}
            rows={2}
            className={cn(inputClass, "min-h-(--min-h-textarea) resize-y")}
          />
        </div>
        <div>
          <label
            htmlFor={`${baseId}-type`}
            className="mb-2 block text-sm font-semibold tracking-wide text-(--text-secondary) opacity-heavy"
          >
            {language === "en" ? t("events:form.type_en") : t("events:form.type")}
          </label>
          <input
            id={`${baseId}-type`}
            type="text"
            value={getLocalizedEditValue("event_type") || ""}
            onChange={(e) => updateLocalizedEditValue("event_type", e.target.value)}
            className={inputClass}
          />
        </div>
        <div>
          <label
            htmlFor={`${baseId}-loc`}
            className="mb-2 block text-sm font-semibold tracking-wide text-(--text-secondary) opacity-heavy"
          >
            {language === "en" ? t("events:form.location_en") : t("events:form.location")}
          </label>
          <input
            id={`${baseId}-loc`}
            type="text"
            value={getLocalizedEditValue("location") || ""}
            onChange={(e) => updateLocalizedEditValue("location", e.target.value)}
            className={inputClass}
          />
        </div>
        <div>
          <label
            htmlFor={`${baseId}-start`}
            className="mb-2 block text-sm font-semibold tracking-wide text-(--text-secondary) opacity-heavy"
          >
            {t("events:form.start")}
          </label>
          <input
            id={`${baseId}-start`}
            type="datetime-local"
            value={formatEventDateInput(draft.starts_at, campusTimezone)}
            onChange={(e) => setDraft({ ...draft, starts_at: e.target.value })}
            className={cn(inputClass, startDateErrorText && "border-error-border")}
            aria-invalid={Boolean(startDateErrorText) || undefined}
            aria-describedby={startDateErrorText ? `${baseId}-start-error` : undefined}
          />
          {startDateErrorText && (
            <p id={`${baseId}-start-error`} role="alert" className="mt-1 text-sm text-error-text">
              {startDateErrorText}
            </p>
          )}
        </div>
        <div>
          <label
            htmlFor={`${baseId}-end`}
            className="mb-2 block text-sm font-semibold tracking-wide text-(--text-secondary) opacity-heavy"
          >
            {t("events:form.end")}
          </label>
          <input
            id={`${baseId}-end`}
            type="datetime-local"
            value={formatEventDateInput(draft.ends_at, campusTimezone)}
            onChange={(e) => setDraft({ ...draft, ends_at: e.target.value })}
            className={cn(
              inputClass,
              (resolvedDateError || endDateErrorMessage) && "border-error-border"
            )}
            aria-invalid={Boolean(endDateErrorMessage) || undefined}
            aria-describedby={endDateErrorMessage ? `${baseId}-end-error` : undefined}
          />
          {endDateErrorMessage && (
            <p id={`${baseId}-end-error`} role="alert" className="mt-1 text-sm text-error-text">
              {endDateErrorMessage}
            </p>
          )}
        </div>
        <div>
          <label
            htmlFor={`${baseId}-speaker`}
            className="mb-2 block text-sm font-semibold tracking-wide text-(--text-secondary) opacity-heavy"
          >
            {t("events:form.speaker")}
          </label>
          <input
            id={`${baseId}-speaker`}
            type="text"
            value={draft.speaker || ""}
            onChange={(e) => setDraft({ ...draft, speaker: e.target.value })}
            className={inputClass}
          />
        </div>
        <div>
          <Button as="label" variant="solid" disabled={imageLoading} className="w-full sm:w-auto">
            {imageLoading ? t("common:statuses.uploading") : t("common:buttons.changePhoto")}
            <input
              type="file"
              accept="image/*"
              hidden
              ref={imageInputRef}
              onChange={handleImageChange}
              onClick={(e) => e.stopPropagation()}
            />
          </Button>
          {cardImageUrl && (
            <div className="mt-3">
              <SmartImage
                srcRaw={cardImageUrl}
                alt={t("events:alt.preview")}
                className="h-36 w-56 rounded-xl border border-(--glass-border) object-cover shadow-surface"
              />
            </div>
          )}
        </div>
      </div>
    </Dialog>
  )
}
