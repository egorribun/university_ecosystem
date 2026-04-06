import { useCallback, useState, useEffect, useRef } from "react"
import useFocusTrap from "@/hooks/useFocusTrap"
import { useTranslation } from "react-i18next"
import { motion, useReducedMotion } from "framer-motion"
import {
  X as CloseIcon,
  Eye as VisibleIcon,
  EyeOff as HiddenIcon,
  ChevronLeft,
  ChevronRight,
  RotateCcw,
} from "lucide-react"
import { ExportDropdown } from "@/components/schedule/ExportDropdown"
import { cn } from "@/utils/cn"
import {
  useWeekOffset,
  useHiddenWeekdays,
  useScheduleDisplayPreferences,
  useScheduleUIActions,
} from "@/stores/scheduleUIStore"

interface ScheduleSettingsPanelProps {
  open: boolean
  onClose: () => void
  weekdayLabels: string[]
  /** Parity selector */
  currentParity: "odd" | "even"
  setCurrentParity: (p: "odd" | "even") => void
  /** Export grid ref */
  gridRef?: React.RefObject<HTMLElement | null>
}

export function ScheduleSettingsPanel({
  open,
  onClose,
  weekdayLabels,
  currentParity,
  setCurrentParity,
  gridRef,
}: ScheduleSettingsPanelProps) {
  const { t } = useTranslation(["schedule", "common"])
  const [isClosing, setIsClosing] = useState(false)
  const prefersReduced = useReducedMotion()

  const weekOffset = useWeekOffset()
  const hiddenWeekdays = useHiddenWeekdays()
  const { showPastLessons, compactMode } = useScheduleDisplayPreferences()
  const { toggleWeekday, togglePastLessons, toggleCompactMode, nextWeek, previousWeek, goToCurrentWeek } = useScheduleUIActions()
  const closeTimerRef = useRef<ReturnType<typeof setTimeout>>(undefined)

  // Cleanup exit-animation timer on unmount (FIX-69-01)
  useEffect(() => () => clearTimeout(closeTimerRef.current), [])

  const handleClose = useCallback(() => {
    setIsClosing(true)
    closeTimerRef.current = setTimeout(() => {
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
        className="fixed inset-0 z-overlay bg-[var(--sched-overlay-bg)] backdrop-blur-sm"
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
            type="button"
            onClick={handleClose}
            aria-label={t("common:buttons.close", { defaultValue: "Close" })}
            className="flex h-8 w-8 items-center justify-center rounded-lg text-text-secondary transition-colors hover:bg-surface-elevated/(--opacity-dim) hover:text-text-primary focus-visible:ring-2 focus-visible:ring-brand"
          >
            <CloseIcon size={16} aria-hidden="true" />
          </button>
        </div>

        {/* ── Content ─────────────────────────────────── */}
        <div className="flex-1 min-h-0 overflow-y-auto px-6 py-6 space-y-8">
          {/* ── Week navigation ── */}
          <section>
            <h3 className="mb-3 text-sm font-bold uppercase tracking-wider text-text-secondary">
              {t("schedule:toolbar.weekNavLabel", { defaultValue: "Week" })}
            </h3>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={previousWeek}
                aria-label={t("schedule:toolbar.prevWeek")}
                className="flex h-10 w-10 items-center justify-center rounded-xl border border-glass-border bg-surface/(--opacity-medium) text-text-secondary transition-colors hover:bg-surface-elevated/(--opacity-dim) hover:text-text-primary focus-visible:ring-2 focus-visible:ring-brand"
              >
                <ChevronLeft size={16} aria-hidden="true" />
              </button>
              <button
                type="button"
                onClick={goToCurrentWeek}
                className={cn(
                  "relative flex-1 rounded-xl border px-4 py-2.5 text-center text-sm font-semibold transition-colors",
                  weekOffset === 0
                    ? "border-brand bg-brand text-[var(--sched-on-accent)] shadow-glow-primary"
                    : "border-glass-border bg-surface/(--opacity-medium) text-text-primary hover:border-brand/(--opacity-dim)"
                )}
              >
                {weekOffset === 0
                  ? t("schedule:toolbar.thisWeek")
                  : weekOffset > 0
                    ? t("schedule:toolbar.weekOffset", { offset: `+${weekOffset}` })
                    : t("schedule:toolbar.weekOffset", { offset: String(weekOffset) })}
              </button>
              <button
                type="button"
                onClick={nextWeek}
                aria-label={t("schedule:toolbar.nextWeek")}
                className="flex h-10 w-10 items-center justify-center rounded-xl border border-glass-border bg-surface/(--opacity-medium) text-text-secondary transition-colors hover:bg-surface-elevated/(--opacity-dim) hover:text-text-primary focus-visible:ring-2 focus-visible:ring-brand"
              >
                <ChevronRight size={16} aria-hidden="true" />
              </button>
              {weekOffset !== 0 && (
                <button
                  type="button"
                  onClick={goToCurrentWeek}
                  aria-label={t("schedule:toolbar.goToToday")}
                  className="flex h-10 w-10 items-center justify-center rounded-xl border border-brand/(--opacity-dim) text-brand transition-colors hover:bg-brand/(--opacity-subtle) focus-visible:ring-2 focus-visible:ring-brand"
                >
                  <RotateCcw size={14} aria-hidden="true" />
                </button>
              )}
            </div>
          </section>

          {/* ── Parity selector ── */}
          <section>
            <h3 className="mb-3 text-sm font-bold uppercase tracking-wider text-text-secondary">
              {t("schedule:parity.label", { defaultValue: "Week parity" })}
            </h3>
            <div className="flex gap-2">
              {(["odd", "even"] as const).map((p) => (
                <button
                  key={p}
                  type="button"
                  onClick={() => setCurrentParity(p)}
                  className={cn(
                    "relative flex-1 rounded-xl border px-4 py-2.5 text-sm font-semibold transition-all duration-fast overflow-hidden",
                    currentParity === p
                      ? "border-brand text-[var(--sched-on-accent)]"
                      : "border-glass-border bg-surface/(--opacity-medium) text-text-secondary hover:border-brand/(--opacity-dim) hover:text-text-primary"
                  )}
                >
                  {currentParity === p && (
                    <motion.span
                      layoutId="settings-parity-pill"
                      className="absolute inset-0 rounded-xl bg-brand shadow-glow-primary"
                      transition={prefersReduced ? { duration: 0 } : { type: "spring", stiffness: 400, damping: 30 }}
                    />
                  )}
                  <span className="relative z-surface">{t(`schedule:parity.${p}`)}</span>
                </button>
              ))}
            </div>
          </section>

          {/* ── Export ── */}
          <section>
            <h3 className="mb-3 text-sm font-bold uppercase tracking-wider text-text-secondary">
              {t("schedule:toolbar.export")}
            </h3>
            <ExportDropdown gridRef={gridRef} className="w-full" />
          </section>

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
                className="sched-toggle-input h-5 w-10 appearance-none rounded-full border border-glass-border bg-surface-elevated transition-colors checked:bg-brand checked:border-brand focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-1 cursor-pointer"
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
                className="sched-toggle-input h-5 w-10 appearance-none rounded-full border border-glass-border bg-surface-elevated transition-colors checked:bg-brand checked:border-brand focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-1 cursor-pointer"
              />
            </label>
          </section>
        </div>
      </div>
    </>
  )
}
