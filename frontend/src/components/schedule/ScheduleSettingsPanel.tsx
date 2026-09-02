import { useCallback } from "react"
import useFocusTrap from "@/hooks/useFocusTrap"
import { useTranslation } from "react-i18next"
import { AnimatePresence, m } from "framer-motion"
import useMediaQuery from "@/hooks/useMediaQuery"
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
  const prefersReduced = useMediaQuery("(prefers-reduced-motion: reduce)")

  const weekOffset = useWeekOffset()
  const hiddenWeekdays = useHiddenWeekdays()
  const { showPastLessons, compactMode } = useScheduleDisplayPreferences()
  const {
    toggleWeekday,
    togglePastLessons,
    toggleCompactMode,
    nextWeek,
    previousWeek,
    goToCurrentWeek,
  } = useScheduleUIActions()

  const handleClose = useCallback(() => onClose(), [onClose])

  const dialogRef = useFocusTrap<HTMLDivElement>({
    active: open,
    onDeactivate: handleClose,
  })

  return (
    <AnimatePresence>
      {open && (
        <m.div
          className="fixed inset-0 z-modal flex items-center justify-center p-4"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.2 }}
        >
          {/* Backdrop */}
          <div
            className="absolute inset-0 bg-[var(--sched-modal-overlay-bg)] backdrop-blur-md"
            onClick={handleClose}
            aria-hidden="true"
          />

          {/* Dialog */}
          <m.div
            ref={dialogRef}
            role="dialog"
            aria-modal="true"
            aria-labelledby="settings-panel-title"
            className="sched-settings-dialog relative flex w-full max-w-[28rem] md:max-w-[32rem] max-h-[min(85vh,52rem)] flex-col overflow-hidden rounded-2xl"
            initial={prefersReduced ? false : { scale: 0.95, y: 8, opacity: 0 }}
            animate={{ scale: 1, y: 0, opacity: 1 }}
            exit={prefersReduced ? { opacity: 0 } : { scale: 0.95, y: 8, opacity: 0 }}
            transition={
              prefersReduced ? { duration: 0 } : { type: "spring", stiffness: 400, damping: 30 }
            }
          >
            {/* ── Header ──────────────────────────────────── */}
            <div className="relative z-surface px-6 pt-5 pb-4">
              <div className="flex items-center justify-between">
                <h2
                  id="settings-panel-title"
                  className="text-lg md:text-xl font-bold text-text-primary tracking-tight"
                >
                  {t("schedule:settings.title")}
                </h2>
                <button
                  type="button"
                  onClick={handleClose}
                  aria-label={t("common:buttons.close")}
                  className="flex h-8 w-8 min-h-[44px] min-w-[44px] items-center justify-center rounded-lg text-text-secondary transition-colors hover:bg-surface-elevated/(--opacity-dim) hover:text-text-primary focus-visible:ring-2 focus-visible:ring-brand"
                >
                  <CloseIcon size={16} aria-hidden="true" />
                </button>
              </div>
              <div className="sched-settings-divider mt-4" aria-hidden="true" />
            </div>

            {/* ── Content ─────────────────────────────────── */}
            <div className="relative z-surface flex-1 min-h-0 overflow-y-auto px-6 pb-6 space-y-6">
              {/* ── Week navigation ── */}
              <section>
                <h3 className="mb-3 text-sm font-bold uppercase tracking-wider text-text-secondary">
                  {t("schedule:toolbar.weekNavLabel")}
                </h3>
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={previousWeek}
                    aria-label={t("schedule:toolbar.prevWeek")}
                    className="sched-settings-btn flex h-10 w-10 items-center justify-center rounded-xl text-text-secondary hover:text-text-primary focus-visible:ring-2 focus-visible:ring-brand"
                  >
                    <ChevronLeft size={16} aria-hidden="true" />
                  </button>
                  <button
                    type="button"
                    onClick={goToCurrentWeek}
                    className={cn(
                      "relative flex-1 rounded-xl px-4 py-2.5 text-center text-sm font-semibold",
                      weekOffset === 0
                        ? "bg-brand text-[var(--sched-on-accent)] shadow-glow-primary"
                        : "sched-settings-btn text-text-primary"
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
                    className="sched-settings-btn flex h-10 w-10 items-center justify-center rounded-xl text-text-secondary hover:text-text-primary focus-visible:ring-2 focus-visible:ring-brand"
                  >
                    <ChevronRight size={16} aria-hidden="true" />
                  </button>
                  {weekOffset !== 0 && (
                    <button
                      type="button"
                      onClick={goToCurrentWeek}
                      aria-label={t("schedule:toolbar.goToToday")}
                      className="sched-settings-btn flex h-10 w-10 items-center justify-center rounded-xl text-brand focus-visible:ring-2 focus-visible:ring-brand"
                    >
                      <RotateCcw size={14} aria-hidden="true" />
                    </button>
                  )}
                </div>
              </section>

              <div className="sched-settings-divider" aria-hidden="true" />

              {/* ── Parity selector ── */}
              <section>
                <h3 className="mb-3 text-sm font-bold uppercase tracking-wider text-text-secondary">
                  {t("schedule:parity.label")}
                </h3>
                <div className="flex gap-2">
                  {(["odd", "even"] as const).map((p) => (
                    <button
                      key={p}
                      type="button"
                      onClick={() => setCurrentParity(p)}
                      className={cn(
                        "relative flex-1 rounded-xl px-4 py-2.5 text-sm font-semibold transition-all duration-fast overflow-hidden",
                        currentParity === p
                          ? "text-[var(--sched-on-accent)]"
                          : "sched-settings-btn text-text-secondary hover:text-text-primary"
                      )}
                    >
                      {currentParity === p && (
                        <m.span
                          layoutId="settings-parity-pill"
                          className="absolute inset-0 rounded-xl bg-brand shadow-glow-primary"
                          transition={
                            prefersReduced
                              ? { duration: 0 }
                              : { type: "spring", stiffness: 400, damping: 30 }
                          }
                        />
                      )}
                      <span className="relative z-surface">{t(`schedule:parity.${p}`)}</span>
                    </button>
                  ))}
                </div>
              </section>

              <div className="sched-settings-divider" aria-hidden="true" />

              {/* ── Export ── */}
              <section>
                <h3 className="mb-3 text-sm font-bold uppercase tracking-wider text-text-secondary">
                  {t("schedule:toolbar.export")}
                </h3>
                <ExportDropdown gridRef={gridRef} className="w-full" />
              </section>

              <div className="sched-settings-divider" aria-hidden="true" />

              {/* ── Visible days ── */}
              <section>
                <h3 className="mb-3 text-sm font-bold uppercase tracking-wider text-text-secondary">
                  {t("schedule:settings.hiddenDays")}
                </h3>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                  {weekdayLabels.map((label, idx) => {
                    const isHidden = hiddenWeekdays.includes(idx)
                    return (
                      <button
                        key={idx}
                        type="button"
                        onClick={() => toggleWeekday(idx)}
                        className={cn(
                          "flex w-full items-center gap-3 rounded-xl px-4 py-3 text-left text-sm font-medium transition-all duration-fast",
                          isHidden
                            ? "opacity-50 text-text-secondary bg-surface/(--opacity-dim)"
                            : "sched-settings-btn text-text-primary"
                        )}
                        aria-pressed={!isHidden}
                      >
                        {isHidden ? (
                          <HiddenIcon
                            size={16}
                            className="text-text-muted-subtle"
                            aria-hidden="true"
                          />
                        ) : (
                          <VisibleIcon size={16} className="text-brand" aria-hidden="true" />
                        )}
                        {label}
                      </button>
                    )
                  })}
                </div>
              </section>

              <div className="sched-settings-divider" aria-hidden="true" />

              {/* ── Toggle options ── */}
              <section>
                <h3 className="mb-3 text-sm font-bold uppercase tracking-wider text-text-secondary">
                  {t("schedule:toolbar.settings")}
                </h3>
                <div className="sched-settings-group overflow-hidden rounded-xl">
                  {/* Compact mode */}
                  <label className="flex cursor-pointer items-center justify-between px-4 py-3.5 transition-colors hover:bg-surface-elevated/(--opacity-dim)">
                    <span className="text-sm font-medium text-text-primary">
                      {t("schedule:settings.compactMode")}
                    </span>
                    <input
                      type="checkbox"
                      checked={compactMode}
                      onChange={toggleCompactMode}
                      className="sched-toggle-input h-5 w-10 appearance-none rounded-full bg-surface-elevated transition-colors checked:bg-brand focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-1 cursor-pointer"
                    />
                  </label>
                  {/* Show past lessons */}
                  <label className="flex cursor-pointer items-center justify-between px-4 py-3.5 transition-colors hover:bg-surface-elevated/(--opacity-dim)">
                    <span className="text-sm font-medium text-text-primary">
                      {t("schedule:settings.showPast")}
                    </span>
                    <input
                      type="checkbox"
                      checked={showPastLessons}
                      onChange={togglePastLessons}
                      className="sched-toggle-input h-5 w-10 appearance-none rounded-full bg-surface-elevated transition-colors checked:bg-brand focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-1 cursor-pointer"
                    />
                  </label>
                </div>
              </section>
            </div>
          </m.div>
        </m.div>
      )}
    </AnimatePresence>
  )
}
