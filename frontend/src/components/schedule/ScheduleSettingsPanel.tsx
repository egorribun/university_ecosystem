import { useCallback, useState } from "react"
import useFocusTrap from "@/hooks/useFocusTrap"
import { useTranslation } from "react-i18next"
import { X as CloseIcon, Eye as VisibleIcon, EyeOff as HiddenIcon } from "lucide-react"
import { cn } from "@/utils/cn"
import {
  useHiddenWeekdays,
  useScheduleDisplayPreferences,
  useScheduleUIActions,
} from "@/stores/scheduleUIStore"

interface ScheduleSettingsPanelProps {
  open: boolean
  onClose: () => void
  weekdayLabels: string[]
}

export function ScheduleSettingsPanel({
  open,
  onClose,
  weekdayLabels,
}: ScheduleSettingsPanelProps) {
  const { t } = useTranslation(["schedule", "common"])
  const [isClosing, setIsClosing] = useState(false)

  const hiddenWeekdays = useHiddenWeekdays()
  const { showPastLessons, compactMode } = useScheduleDisplayPreferences()
  const { toggleWeekday, togglePastLessons, toggleCompactMode } = useScheduleUIActions()

  const handleClose = useCallback(() => {
    setIsClosing(true)
    setTimeout(() => {
      setIsClosing(false)
      onClose()
    }, 250)
  }, [onClose])

  const panelRef = useFocusTrap<HTMLDivElement>({
    active: open,
    onDeactivate: handleClose,
  })

  // FIX-65-03: match LessonSlideOver pattern — allow exit animation to play
  if (!open && !isClosing) return null

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 z-overlay bg-black/30 dark:bg-black/50 backdrop-blur-sm"
        onClick={handleClose}
        aria-hidden="true"
      />

      {/* Panel */}
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="settings-panel-title"
        data-closing={isClosing || undefined}
        className="sched-slideover flex flex-col border-l border-glass-border bg-surface/(--opacity-heavy) shadow-glass-strong backdrop-blur-xl glass-noise"
      >
        {/* ── Header ──────────────────────────────────── */}
        <div className="flex items-center justify-between border-b border-glass-border px-6 py-4">
          <h2
            id="settings-panel-title"
            className="text-lg font-bold text-text-primary tracking-tight"
          >
            {t("schedule:settings.title")}
          </h2>
          <button
            onClick={handleClose}
            aria-label={t("common:buttons.close", { defaultValue: "Close" })}
            className="flex h-8 w-8 items-center justify-center rounded-lg text-text-secondary transition-colors hover:bg-surface-elevated/(--opacity-dim) hover:text-text-primary focus-visible:ring-2 focus-visible:ring-brand"
          >
            <CloseIcon size={16} aria-hidden="true" />
          </button>
        </div>

        {/* ── Content ─────────────────────────────────── */}
        <div className="flex-1 min-h-0 overflow-y-auto px-6 py-6 space-y-8">
          {/* Visible days */}
          <section>
            <h3 className="mb-3 text-sm font-bold uppercase tracking-wider text-text-secondary">
              {t("schedule:settings.hiddenDays")}
            </h3>
            <div className="space-y-2">
              {weekdayLabels.map((label, idx) => {
                const isHidden = hiddenWeekdays.includes(idx)
                return (
                  <button
                    key={idx}
                    type="button"
                    onClick={() => toggleWeekday(idx)}
                    className={cn(
                      "flex w-full items-center gap-3 rounded-xl border px-4 py-3 text-left text-sm font-medium transition-all duration-fast",
                      isHidden
                        ? "border-glass-border/(--opacity-soft) bg-surface/(--opacity-dim) text-text-secondary opacity-60"
                        : "border-glass-border bg-surface/(--opacity-medium) text-text-primary hover:border-brand/(--opacity-dim)"
                    )}
                    aria-pressed={!isHidden}
                  >
                    {isHidden ? (
                      <HiddenIcon size={16} className="text-text-muted-subtle" aria-hidden="true" />
                    ) : (
                      <VisibleIcon size={16} className="text-brand" aria-hidden="true" />
                    )}
                    {label}
                  </button>
                )
              })}
            </div>
          </section>

          {/* Toggle options */}
          <section className="space-y-3">
            <h3 className="mb-3 text-sm font-bold uppercase tracking-wider text-text-secondary">
              {t("schedule:toolbar.settings")}
            </h3>

            {/* Compact mode */}
            <label className="flex cursor-pointer items-center justify-between rounded-xl border border-glass-border bg-surface/(--opacity-medium) px-4 py-3 transition-colors hover:border-brand/(--opacity-dim)">
              <span className="text-sm font-medium text-text-primary">
                {t("schedule:settings.compactMode")}
              </span>
              <input
                type="checkbox"
                checked={compactMode}
                onChange={toggleCompactMode}
                className="h-5 w-5 rounded border-glass-border text-brand accent-brand focus:ring-2 focus:ring-brand focus:ring-offset-1"
              />
            </label>

            {/* Show past lessons */}
            <label className="flex cursor-pointer items-center justify-between rounded-xl border border-glass-border bg-surface/(--opacity-medium) px-4 py-3 transition-colors hover:border-brand/(--opacity-dim)">
              <span className="text-sm font-medium text-text-primary">
                {t("schedule:settings.showPast")}
              </span>
              <input
                type="checkbox"
                checked={showPastLessons}
                onChange={togglePastLessons}
                className="h-5 w-5 rounded border-glass-border text-brand accent-brand focus:ring-2 focus:ring-brand focus:ring-offset-1"
              />
            </label>
          </section>
        </div>
      </div>
    </>
  )
}
