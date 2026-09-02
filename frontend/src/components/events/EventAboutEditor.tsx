import { useState, useRef, useMemo } from "react"
import { useTranslation } from "react-i18next"
import { Pencil as EditIcon, Save as SaveIcon, X as CloseIcon } from "lucide-react"
import { Button } from "@/components/ui"
import { cn } from "@/utils/cn"
import api from "@/api/client"
import { logError } from "@/app/logger"
import { captureActiveTelemetryContext } from "@/utils/telemetryContext"
import type { Event } from "@/types/Event"

interface EventAboutEditorProps {
  event: Event
  language: "en" | "ru"
  canEdit: boolean
  onUpdate: () => Promise<void>
  onError: (msg: string) => void
  onSuccess: (msg: string) => void
}

const inputClass =
  "w-full rounded-sm border border-glass-border bg-surface/(--opacity-medium) px-4 py-3 text-input font-medium text-text-primary shadow-sm transition-all duration-fast focus:border-brand focus:outline-none focus:ring-1 focus:ring-brand/(--opacity-faint) placeholder:text-text-secondary/(--opacity-medium)"

export function EventAboutEditor({
  event,
  language,
  canEdit,
  onUpdate,
  onError,
  onSuccess,
}: EventAboutEditorProps) {
  const { t } = useTranslation(["events", "common"])
  const baseline = useMemo(
    () => (language === "en" ? (event.about_en ?? "") : (event.about ?? "")),
    [language, event.about_en, event.about]
  )
  const [editing, setEditing] = useState(false)
  // Initialise the draft from the current localized value.  Editing still
  // refreshes it from `baseline`, but deriving the initial value avoids an
  // unreachable magic placeholder and keeps state safe for the first render.
  const [draft, setDraft] = useState(baseline)
  const [saving, setSaving] = useState(false)
  const sectionRef = useRef<HTMLHeadingElement | null>(null)

  const handleEdit = () => {
    setDraft(baseline)
    setEditing(true)
  }

  const handleCancel = () => {
    setEditing(false)
    setDraft(baseline)
  }

  const handleSave = async () => {
    const telemetryContext = captureActiveTelemetryContext()
    setSaving(true)
    try {
      const payloadKey = language === "en" ? "about_en" : "about"
      await telemetryContext.run(() =>
        api.patch(`/events/${event.id}`, { [payloadKey]: draft.trim() })
      )
      setEditing(false)
      onSuccess(t("events:detail.messages.aboutUpdated"))
      await telemetryContext.run(onUpdate)
      setTimeout(() => {
        const heading = sectionRef.current
        if (heading === null) return
        heading.focus()
      }, 0)
    } catch (err) {
      logError("[EventAboutEditor] Save failed:", err)
      onError(t("events:detail.messages.aboutUpdateFailed"))
    } finally {
      setSaving(false)
    }
  }

  return (
    <div>
      <div className="mb-2 flex items-center gap-2">
        <h2
          id="event-about-heading"
          ref={sectionRef}
          tabIndex={-1}
          className="text-fluid-h2 font-bold text-text-primary"
        >
          {t("events:detail.sections.about.title")}
        </h2>
        {canEdit && !editing && (
          <button
            type="button"
            aria-label={t("events:detail.sections.about.editAria")}
            className="rounded-full p-1 text-(--text-secondary) transition-colors hover:text-(--primary-main)"
            onClick={handleEdit}
          >
            <EditIcon size={20} />
          </button>
        )}
      </div>

      {editing ? (
        <div className="space-y-3">
          <textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            disabled={saving}
            rows={3}
            className={cn(inputClass, "min-h-(--min-h-textarea) resize-y")}
            placeholder={
              language === "en"
                ? t("events:detail.sections.about.fieldLabel_en")
                : t("events:detail.sections.about.fieldLabel")
            }
          />
          <div className="flex flex-wrap gap-2">
            <Button
              variant="solid"
              size="sm"
              leadingIcon={<SaveIcon size={18} />}
              onClick={handleSave}
              disabled={saving || draft.trim() === baseline.trim()}
            >
              {saving ? t("events:detail.sections.about.savePending") : t("common:buttons.save")}
            </Button>
            <Button
              variant="outline"
              size="sm"
              leadingIcon={<CloseIcon size={18} />}
              onClick={handleCancel}
              disabled={saving}
            >
              {t("common:buttons.cancel")}
            </Button>
          </div>
        </div>
      ) : (
        <p
          className={cn(
            "whitespace-pre-line text-lg leading-relaxed",
            baseline ? "text-text-primary" : "text-(--text-secondary)"
          )}
        >
          {baseline || t("events:detail.sections.about.empty")}
        </p>
      )}
    </div>
  )
}
